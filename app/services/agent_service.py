import time
import json
import logging
from typing import Dict, Any, List, TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage, BaseMessage
from app.models import AgentConfig, AgentExecutionResponse
from app.services.yaml_service import YAMLService
from app.services.llm_service import LLMService
from app.services.tool_service import ToolService
from app.config import settings


class AgentState(TypedDict):
    """State for LangGraph agent with proper type annotations."""
    messages: Annotated[List[BaseMessage], operator.add]
    iteration: int
    last_response: Any
    context: Dict[str, Any]


class AgentService:

    logger = logging.getLogger(__name__)
    
    @staticmethod
    async def execute_agent(agent_name: str, user_input: str, context: Dict[str, Any] = None) -> AgentExecutionResponse:
        """Execute an agent by name with given input."""
        start_time = time.time()
        context = context or {}
        
        AgentService.logger.debug(f"Executing agent: {agent_name}")

        if settings.debug_trace:
            AgentService.logger.debug(
                "Agent request: %s",
                json.dumps(
                    {"agent_name": agent_name, "input": user_input, "context": context},
                    default=str,
                ),
            )
        
        agent_config = YAMLService.load_agent(agent_name)
        if not agent_config:
            AgentService.logger.warning(f"Agent not found: {agent_name}")
            return AgentExecutionResponse(
                agent_name=agent_name,
                success=False,
                output="",
                steps=[],
                error=f"Agent '{agent_name}' not found",
                execution_time=time.time() - start_time
            )
        
        try:
            AgentService.logger.debug(f"Agent framework: {agent_config.framework}, tools: {agent_config.tools}")
            if agent_config.framework == "langgraph":
                output, steps = await AgentService._execute_langgraph_agent(agent_config, user_input, context)
            else:
                raise ValueError(f"Unsupported framework: {agent_config.framework}")

            execution_time = time.time() - start_time
            AgentService.logger.debug(f"Agent executed successfully: {agent_name} (took {execution_time:.3f}s, {len(steps)} steps)")
            
            if settings.debug_trace:
                AgentService.logger.debug(
                    "Agent response: %s",
                    json.dumps(
                        {
                            "agent_name": agent_name,
                            "output": output,
                            "steps": steps,
                            "execution_time": execution_time,
                        },
                        default=str,
                    ),
                )
            
            return AgentExecutionResponse(
                agent_name=agent_name,
                success=True,
                output=output,
                steps=steps,
                error=None,
                execution_time=execution_time
            )
        except Exception as e:
            AgentService.logger.error(f"Agent execution failed: {agent_name} - {str(e)}")
            return AgentExecutionResponse(
                agent_name=agent_name,
                success=False,
                output="",
                steps=[],
                error=str(e),
                execution_time=time.time() - start_time
            )
    
    @staticmethod
    async def _execute_langgraph_agent(agent_config: AgentConfig, user_input: str, context: Dict[str, Any]) -> tuple[str, List[Dict[str, Any]]]:
        """Execute agent using LangGraph framework."""
        AgentService.logger.debug(f"Building LangGraph agent with {len(agent_config.tools)} tools")
        llm = LLMService.get_llm(agent_config.llm_config)
        
        tools = []
        tool_configs = {}
        for tool_name in agent_config.tools:
            tool_config = YAMLService.load_tool(tool_name)
            if tool_config:
                tool_configs[tool_name] = tool_config
                
                def create_tool_func(tn):
                    async def tool_func(**kwargs):
                        result = await ToolService.execute_tool(tn, kwargs)
                        if result.success:
                            return result.result
                        else:
                            return f"Error: {result.error}"
                    tool_func.__name__ = tn
                    tool_func.__doc__ = tool_config.description
                    return tool_func
                
                tool_func = create_tool_func(tool_name)
                decorated_tool = tool(tool_func)
                tools.append(decorated_tool)
        
        llm_with_tools = llm.bind_tools(tools) if tools else llm
        AgentService.logger.debug(f"LangGraph agent configured with {len(tools)} bound tools")
        
        steps = []
        
        def agent_node(state: AgentState) -> AgentState:
            """Agent reasoning node."""
            # Log incoming state
            messages_in_state = state.get("messages", [])
            AgentService.logger.debug(f"agent_node: ENTRY - messages in state: {len(messages_in_state)}, iteration: {state.get('iteration', 'NOT SET')}")
            AgentService.logger.debug(f"agent_node: ENTRY - state keys: {list(state.keys())}")
            
            # Check if this is the first call by looking at state directly
            is_first_call = "messages" not in state or len(messages_in_state) == 0
            
            if is_first_call:
                messages = [
                    SystemMessage(content=agent_config.system_prompt),
                    HumanMessage(content=user_input)
                ]
                state["iteration"] = 0
                AgentService.logger.debug("agent_node: first iteration, iteration=0")
            else:
                messages = list(messages_in_state)  # Create a copy
                state["iteration"] = state.get("iteration", 0) + 1
                AgentService.logger.debug(f"agent_node: incrementing iteration to {state['iteration']}")
            
            response = llm_with_tools.invoke(messages)
            messages.append(response)
            
            tool_calls_count = len(getattr(response, "tool_calls", []))
            AgentService.logger.debug(f"agent_node: LLM response has {tool_calls_count} tool calls")
            
            steps.append({
                "type": "reasoning",
                "content": response.content,
                "tool_calls": getattr(response, "tool_calls", [])
            })
            
            state["messages"] = messages
            state["last_response"] = response
            
            AgentService.logger.debug(f"agent_node: EXIT - messages in state: {len(state['messages'])}, iteration: {state['iteration']}")
            
            return state
        
        def should_continue(state: AgentState) -> str:
            """Determine if agent should continue or end."""
            last_response = state.get("last_response")
            iteration = state.get("iteration", 0)
            
            AgentService.logger.debug(f"should_continue: iteration={iteration}, max={agent_config.max_iterations}")
            
            if not last_response:
                AgentService.logger.debug("should_continue: no last_response, ending")
                return END
            
            # Check iteration limit first
            if iteration >= agent_config.max_iterations:
                AgentService.logger.debug(f"should_continue: max iterations reached ({iteration}/{agent_config.max_iterations}), ending")
                return END
            
            # Check if there are tool calls
            if hasattr(last_response, "tool_calls") and last_response.tool_calls:
                AgentService.logger.debug(f"should_continue: {len(last_response.tool_calls)} tool calls found, continuing to tools")
                return "tools"
            
            AgentService.logger.debug("should_continue: no tool calls, ending")
            return END
        
        async def tool_node(state: AgentState) -> AgentState:
            """Execute tools called by agent."""
            last_response = state.get("last_response")
            messages = state.get("messages", [])
            
            if hasattr(last_response, "tool_calls") and last_response.tool_calls:
                for tool_call in last_response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call.get("args", {})
                    
                    result = await ToolService.execute_tool(tool_name, tool_args)
                    
                    steps.append({
                        "type": "tool_execution",
                        "tool_name": tool_name,
                        "arguments": tool_args,
                        "result": result.result if result.success else result.error,
                        "success": result.success
                    })
                    
                    messages.append(
                        ToolMessage(
                            content=str(result.result if result.success else result.error),
                            tool_call_id=tool_call.get("id", "")
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
                END: END
            }
        )
        
        workflow.add_edge("tools", "agent")
        
        app = workflow.compile()
        
        initial_state = {
            "messages": [],
            "iteration": 0,
            "context": context
        }
        
        # Each iteration involves multiple graph steps (agent node, conditional edges, tool node, edges back)
        # Set a generous limit to account for all internal LangGraph operations
        recursion_limit = max(agent_config.max_iterations * 10, 50)
        AgentService.logger.debug(f"Setting recursion_limit to {recursion_limit} (max_iterations={agent_config.max_iterations})")
        
        final_state = await app.ainvoke(
            initial_state,
            config={"recursion_limit": recursion_limit}
        )
        
        messages = final_state.get("messages", [])
        final_output = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                final_output = msg.content
                break
        
        return final_output, steps
