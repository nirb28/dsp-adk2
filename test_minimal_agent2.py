"""Test to replicate the actual agent behavior."""
import asyncio
import logging
from typing import TypedDict
from langgraph.graph import StateGraph, END

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    messages: list
    iteration: int
    last_response: dict
    
async def test_actual_pattern():
    """Test the actual pattern used in agent_service.py."""
    
    call_count = {"agent": 0, "tools": 0, "should_continue": 0}
    
    def agent_node(state: AgentState) -> AgentState:
        call_count["agent"] += 1
        iteration = state.get("iteration", 0)
        
        logger.info(f"agent_node called (count={call_count['agent']}), iteration BEFORE={iteration}")
        
        # This is the ACTUAL pattern in the code
        if not state.get("messages"):
            state["iteration"] = 0
            logger.info("agent_node: first call, setting iteration=0")
        else:
            state["iteration"] = state.get("iteration", 0) + 1
            logger.info(f"agent_node: incrementing iteration to {state['iteration']}")
        
        # Simulate LLM response with tool calls on first 2 iterations
        if state["iteration"] < 2:
            response = {"tool_calls": [{"name": "test_tool"}]}
            logger.info(f"agent_node: simulating tool calls (iteration={state['iteration']})")
        else:
            response = {"tool_calls": []}
            logger.info(f"agent_node: no tool calls (iteration={state['iteration']})")
        
        state["last_response"] = response
        state["messages"] = state.get("messages", []) + ["msg"]
        
        return state
    
    def should_continue(state: AgentState) -> str:
        call_count["should_continue"] += 1
        last_response = state.get("last_response")
        iteration = state.get("iteration", 0)
        
        logger.info(f"should_continue called (count={call_count['should_continue']}), iteration={iteration}")
        
        if not last_response:
            logger.info("should_continue: no last_response, ending")
            return END
        
        # Check iteration limit first
        if iteration >= 3:
            logger.info(f"should_continue: max iterations reached ({iteration}/3), ending")
            return END
        
        # Check if there are tool calls
        if last_response.get("tool_calls"):
            logger.info(f"should_continue: {len(last_response['tool_calls'])} tool calls found, continuing to tools")
            return "tools"
        
        logger.info("should_continue: no tool calls, ending")
        return END
    
    def tool_node(state: AgentState) -> AgentState:
        call_count["tools"] += 1
        logger.info(f"tool_node called (count={call_count['tools']})")
        # Tools don't modify iteration anymore
        return state
    
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")
    
    app = workflow.compile()
    
    initial_state = {"messages": [], "iteration": 0}
    
    logger.info("=" * 80)
    logger.info("Starting graph execution with recursion_limit=50")
    logger.info("Expected: agent(0) -> tools -> agent(1) -> tools -> agent(2) -> END")
    logger.info("=" * 80)
    
    try:
        final_state = await app.ainvoke(initial_state, config={"recursion_limit": 50})
        logger.info("=" * 80)
        logger.info("SUCCESS!")
        logger.info(f"Final iteration: {final_state.get('iteration')}")
        logger.info(f"Call counts: {call_count}")
        logger.info("=" * 80)
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"FAILED: {e}")
        logger.error(f"Call counts at failure: {call_count}")
        logger.error("=" * 80)
        raise

if __name__ == "__main__":
    asyncio.run(test_actual_pattern())
