from fastapi import APIRouter, HTTPException, status
from typing import List
from app.models import ToolConfig, AgentConfig
from app.services.yaml_service import YAMLService
from app.services.tool_service import ToolService

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/tools", response_model=List[str])
async def list_tools():
    """List all available tools."""
    return YAMLService.list_tools()


@router.get("/tools/{tool_name}", response_model=ToolConfig)
async def get_tool(tool_name: str):
    """Get a specific tool configuration."""
    tool = YAMLService.load_tool(tool_name)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_name}' not found"
        )
    return tool


@router.post("/tools", response_model=ToolConfig, status_code=status.HTTP_201_CREATED)
async def create_tool(tool: ToolConfig):
    """Create a new tool."""
    existing = YAMLService.load_tool(tool.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tool '{tool.name}' already exists"
        )
    
    YAMLService.save_tool(tool)
    return tool


@router.put("/tools/{tool_name}", response_model=ToolConfig)
async def update_tool(tool_name: str, tool: ToolConfig):
    """Update an existing tool."""
    existing = YAMLService.load_tool(tool_name)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_name}' not found"
        )
    
    if tool.name != tool_name:
        YAMLService.delete_tool(tool_name)
    
    YAMLService.save_tool(tool)
    return tool


@router.delete("/tools/{tool_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(tool_name: str):
    """Delete a tool."""
    if not YAMLService.delete_tool(tool_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_name}' not found"
        )


@router.get("/tools/{tool_name}/schema")
async def get_tool_schema(tool_name: str):
    """Get OpenAI function calling schema for a tool."""
    tool = YAMLService.load_tool(tool_name)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_name}' not found"
        )
    
    return ToolService.get_tool_schema(tool)


@router.get("/agents", response_model=List[str])
async def list_agents():
    """List all available agents."""
    return YAMLService.list_agents()


@router.get("/agents/{agent_name}", response_model=AgentConfig)
async def get_agent(agent_name: str):
    """Get a specific agent configuration."""
    agent = YAMLService.load_agent(agent_name)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_name}' not found"
        )
    return agent


@router.post("/agents", response_model=AgentConfig, status_code=status.HTTP_201_CREATED)
async def create_agent(agent: AgentConfig):
    """Create a new agent."""
    existing = YAMLService.load_agent(agent.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent '{agent.name}' already exists"
        )
    
    for tool_name in agent.tools:
        if not YAMLService.load_tool(tool_name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tool '{tool_name}' not found"
            )
    
    YAMLService.save_agent(agent)
    return agent


@router.put("/agents/{agent_name}", response_model=AgentConfig)
async def update_agent(agent_name: str, agent: AgentConfig):
    """Update an existing agent."""
    existing = YAMLService.load_agent(agent_name)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_name}' not found"
        )
    
    for tool_name in agent.tools:
        if not YAMLService.load_tool(tool_name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tool '{tool_name}' not found"
            )
    
    if agent.name != agent_name:
        YAMLService.delete_agent(agent_name)
    
    YAMLService.save_agent(agent)
    return agent


@router.delete("/agents/{agent_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_name: str):
    """Delete an agent."""
    if not YAMLService.delete_agent(agent_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_name}' not found"
        )
