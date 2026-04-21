from __future__ import annotations

import json
import logging
import operator
from typing import Any, Dict, List, TypedDict, Annotated, Tuple, Optional

from pydantic import Field, create_model
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage, BaseMessage
from langchain_core.tools import StructuredTool

from app.config import settings
from app.models import AgentConfig, LLMOverride
from app.services.agent_frameworks.base import AgentFramework
from app.services.llm_service import LLMService
from app.services.tool_service import ToolService
from app.services.yaml_service import YAMLService


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    iteration: int
    last_response: Any
    context: Dict[str, Any]


class LangGraphAdapter(AgentFramework):
    name = "langgraph"

    logger = logging.getLogger(__name__)
    _max_tool_message_chars = 4000

    @staticmethod
    def _python_type_for_tool_param(param_type: str) -> Any:
        normalized = (param_type or "string").lower()
        if normalized == "string":
            return str
        if normalized in {"number", "float"}:
            return float
        if normalized in {"integer", "int"}:
            return int
        if normalized == "boolean":
            return bool
        if normalized == "array":
            return List[Any]
        if normalized == "object":
            return Dict[str, Any]
        return Any

    @classmethod
    def _build_args_schema(cls, tool_config) -> type:
        fields: Dict[str, tuple[Any, Any]] = {}
        for param in tool_config.parameters:
            annotation = cls._python_type_for_tool_param(param.type)
            default = ... if param.required and param.default is None else param.default
            fields[param.name] = (
                annotation,
                Field(default=default, description=param.description),
            )
        schema_name = f"{tool_config.name.title().replace('_', '')}Args"
        return create_model(schema_name, **fields)

    @classmethod
    def _tool_message_content(cls, payload: Any) -> str:
        content = payload if isinstance(payload, str) else json.dumps(payload, default=str)
        if len(content) <= cls._max_tool_message_chars:
            return content
        truncated_chars = len(content) - cls._max_tool_message_chars
        return f"{content[:cls._max_tool_message_chars]}\n... [truncated {truncated_chars} chars]"

    async def execute(
        self,
        agent_config: AgentConfig,
        user_input: str,
        context: Dict[str, Any],
        llm_override: Optional[LLMOverride] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        self.logger.debug("Building LangGraph agent with %d tools", len(agent_config.tools))
        llm_config = LLMService.resolve_llm_config(agent_config.llm_config, llm_override)
        llm = LLMService.get_llm(llm_config)

        tools = []
        for tool_name in agent_config.tools:
            tool_config = YAMLService.load_tool(tool_name)
            if not tool_config:
                continue

            args_schema = self._build_args_schema(tool_config)

            def create_tool_func(tn: str, description: str):
                async def tool_func(**kwargs):
                    result = await ToolService.execute_tool(tn, kwargs, llm_override, llm_config)
                    if result.success:
                        return result.result
                    return f"Error: {result.error}"

                tool_func.__name__ = tn
                tool_func.__doc__ = description
                return tool_func

            tool_func = create_tool_func(tool_name, tool_config.description)
            decorated_tool = StructuredTool.from_function(
                coroutine=tool_func,
                name=tool_name,
                description=tool_config.description,
                args_schema=args_schema,
                infer_schema=False,
            )
            tools.append(decorated_tool)

        llm_with_tools = llm.bind_tools(tools) if tools else llm
        self.logger.debug("LangGraph agent configured with %d bound tools", len(tools))

        steps: List[Dict[str, Any]] = []

        def agent_node(state: AgentState) -> AgentState:
            messages_in_state = state.get("messages", [])
            self.logger.debug(
                "agent_node: ENTRY - messages in state: %d, iteration: %s",
                len(messages_in_state),
                state.get("iteration", "NOT SET"),
            )

            is_first_call = "messages" not in state or len(messages_in_state) == 0
            iteration = state.get("iteration", 0)

            if is_first_call:
                seed_messages = [
                    SystemMessage(content=agent_config.system_prompt),
                    HumanMessage(content=user_input),
                ]
                llm_input = seed_messages
                iteration = 0
                self.logger.debug("agent_node: first iteration, iteration=0")
            else:
                seed_messages = []
                llm_input = list(messages_in_state)
                iteration += 1
                self.logger.debug("agent_node: incrementing iteration to %s", iteration)

            if settings.debug_trace:
                self.logger.debug(
                    "LangGraph LLM request: %s",
                    json.dumps(
                        {
                            "provider": llm_config.provider,
                            "model": llm_config.model,
                            "messages": [m.model_dump() for m in llm_input],
                            "tool_names": [t.name for t in tools],
                        },
                        default=str,
                    ),
                )

            response = llm_with_tools.invoke(llm_input)

            if settings.debug_trace:
                self.logger.debug(
                    "LangGraph LLM response: %s",
                    json.dumps(
                        {
                            "content": response.content,
                            "tool_calls": getattr(response, "tool_calls", []),
                            "additional": getattr(response, "additional_kwargs", {}),
                        },
                        default=str,
                    ),
                )

            steps.append(
                {
                    "type": "reasoning",
                    "content": response.content,
                    "tool_calls": getattr(response, "tool_calls", []),
                }
            )

            # Return only NEW messages; operator.add will append them to state
            new_messages = seed_messages + [response]

            self.logger.debug(
                "agent_node: EXIT - returning %d new messages, iteration: %s",
                len(new_messages),
                iteration,
            )

            return {"messages": new_messages, "last_response": response, "iteration": iteration}

        def should_continue(state: AgentState) -> str:
            last_response = state.get("last_response")
            iteration = state.get("iteration", 0)

            self.logger.debug("should_continue: iteration=%s, max=%s", iteration, agent_config.max_iterations)

            if not last_response:
                self.logger.debug("should_continue: no last_response, ending")
                return END

            if iteration >= agent_config.max_iterations:
                self.logger.debug(
                    "should_continue: max iterations reached (%s/%s), ending",
                    iteration,
                    agent_config.max_iterations,
                )
                return END

            if hasattr(last_response, "tool_calls") and last_response.tool_calls:
                self.logger.debug(
                    "should_continue: %d tool calls found, continuing to tools",
                    len(last_response.tool_calls),
                )
                return "tools"

            self.logger.debug("should_continue: no tool calls, ending")
            return END

        tool_names_set = {t.name for t in tools}

        def _sanitize_tool_name(raw_name: str) -> str:
            """Strip model-hallucinated suffixes from tool names."""
            if raw_name in tool_names_set:
                return raw_name
            for known in sorted(tool_names_set, key=len, reverse=True):
                if raw_name.startswith(known):
                    self.logger.warning(
                        "Sanitized tool name %r -> %r", raw_name, known
                    )
                    return known
            return raw_name

        async def tool_node(state: AgentState) -> AgentState:
            last_response = state.get("last_response")
            new_messages: List[ToolMessage] = []

            if hasattr(last_response, "tool_calls") and last_response.tool_calls:
                for tool_call in last_response.tool_calls:
                    tool_name = _sanitize_tool_name(tool_call["name"])
                    tool_args = tool_call.get("args", {})

                    result = await ToolService.execute_tool(tool_name, tool_args, llm_override, llm_config)

                    steps.append(
                        {
                            "type": "tool_execution",
                            "tool_name": tool_name,
                            "arguments": tool_args,
                            "result": result.result if result.success else result.error,
                            "success": result.success,
                        }
                    )

                    new_messages.append(
                        ToolMessage(
                            content=self._tool_message_content(
                                result.result if result.success else result.error
                            ),
                            tool_call_id=tool_call.get("id", ""),
                        )
                    )

            # Return only NEW messages; operator.add will append them to state
            return {"messages": new_messages}

        workflow = StateGraph(AgentState)

        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tool_node)

        workflow.set_entry_point("agent")

        workflow.add_conditional_edges(
            "agent",
            should_continue,
            {
                "tools": "tools",
                END: END,
            },
        )

        workflow.add_edge("tools", "agent")

        app = workflow.compile()

        initial_state = {
            "messages": [],
            "iteration": 0,
            "context": context,
        }

        recursion_limit = max(agent_config.max_iterations * 10, 50)
        self.logger.debug(
            "Setting recursion_limit to %s (max_iterations=%s)",
            recursion_limit,
            agent_config.max_iterations,
        )

        final_state = await app.ainvoke(initial_state, config={"recursion_limit": recursion_limit})

        messages = final_state.get("messages", [])
        final_output = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                final_output = msg.content
                break

        return final_output, steps
