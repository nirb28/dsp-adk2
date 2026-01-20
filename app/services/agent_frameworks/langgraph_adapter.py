from __future__ import annotations

import logging
import operator
from typing import Any, Dict, List, TypedDict, Annotated, Tuple, Optional

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage, BaseMessage
from langchain_core.tools import tool

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

            def create_tool_func(tn: str, description: str):
                async def tool_func(**kwargs):
                    result = await ToolService.execute_tool(tn, kwargs, llm_override)
                    if result.success:
                        return result.result
                    return f"Error: {result.error}"

                tool_func.__name__ = tn
                tool_func.__doc__ = description
                return tool_func

            tool_func = create_tool_func(tool_name, tool_config.description)
            decorated_tool = tool(tool_func)
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

            if is_first_call:
                messages = [
                    SystemMessage(content=agent_config.system_prompt),
                    HumanMessage(content=user_input),
                ]
                state["iteration"] = 0
                self.logger.debug("agent_node: first iteration, iteration=0")
            else:
                messages = list(messages_in_state)
                state["iteration"] = state.get("iteration", 0) + 1
                self.logger.debug("agent_node: incrementing iteration to %s", state["iteration"])

            response = llm_with_tools.invoke(messages)
            messages.append(response)

            steps.append(
                {
                    "type": "reasoning",
                    "content": response.content,
                    "tool_calls": getattr(response, "tool_calls", []),
                }
            )

            state["messages"] = messages
            state["last_response"] = response

            self.logger.debug(
                "agent_node: EXIT - messages in state: %d, iteration: %s",
                len(state["messages"]),
                state["iteration"],
            )

            return state

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

        async def tool_node(state: AgentState) -> AgentState:
            last_response = state.get("last_response")
            messages = state.get("messages", [])

            if hasattr(last_response, "tool_calls") and last_response.tool_calls:
                for tool_call in last_response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call.get("args", {})

                    result = await ToolService.execute_tool(tool_name, tool_args, llm_override)

                    steps.append(
                        {
                            "type": "tool_execution",
                            "tool_name": tool_name,
                            "arguments": tool_args,
                            "result": result.result if result.success else result.error,
                            "success": result.success,
                        }
                    )

                    messages.append(
                        ToolMessage(
                            content=str(result.result if result.success else result.error),
                            tool_call_id=tool_call.get("id", ""),
                        )
                    )

            state["messages"] = messages

            return state

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
