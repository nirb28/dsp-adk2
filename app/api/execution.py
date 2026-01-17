from fastapi import APIRouter, HTTPException, status
from app.models import (
    ToolExecutionRequest,
    ToolExecutionResponse,
    AgentExecutionRequest,
    AgentExecutionResponse
)
from app.services.tool_service import ToolService
from app.services.agent_service import AgentService

router = APIRouter(prefix="/execute", tags=["Execution"])


@router.post("/tool", response_model=ToolExecutionResponse)
async def execute_tool(request: ToolExecutionRequest):
    """Execute a tool with given parameters."""
    result = await ToolService.execute_tool(request.tool_name, request.parameters)
    
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error
        )
    
    return result


@router.post("/agent", response_model=AgentExecutionResponse)
async def execute_agent(request: AgentExecutionRequest):
    """Execute an agent with given input."""
    result = await AgentService.execute_agent(
        request.agent_name,
        request.input,
        request.context
    )
    
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error
        )
    
    return result
