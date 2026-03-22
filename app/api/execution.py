from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from app.models import (
    ToolExecutionRequest,
    ToolExecutionResponse,
    AgentExecutionRequest,
    AgentExecutionResponse,
    GraphExecutionRequest,
    GraphExecutionResponse,
    GraphExecutionNormalizedResponse
)
from app.config import settings
from app.services.tool_service import ToolService
from app.services.agent_service import AgentService
from app.services.graph_service import GraphService
from app.services.graph_response_normalizer import GraphResponseNormalizer

router = APIRouter(prefix="/execute", tags=["Execution"])


def _resolve_artifact_path(artifact_type: str, file_name: str) -> Path:
    base_dir = Path(settings.sb_saved_analyses_dir if artifact_type == "analysis" else settings.sb_visualizations_dir).resolve()
    candidate = (base_dir / file_name).resolve()
    if candidate != base_dir and base_dir not in candidate.parents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid artifact path")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return candidate


@router.post("/tool", response_model=ToolExecutionResponse)
async def execute_tool(request: ToolExecutionRequest):
    """Execute a tool with given parameters."""
    result = await ToolService.execute_tool(
        request.tool_name,
        request.parameters,
        request.llm_override,
    )
    
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error
        )
    
    return result


@router.get("/artifacts/{artifact_type}/{file_name:path}")
async def get_execution_artifact(artifact_type: str, file_name: str):
    """Serve saved Starburst analysis and visualization artifacts."""
    if artifact_type not in {"analysis", "visualization"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported artifact type")
    artifact_path = _resolve_artifact_path(artifact_type, file_name)
    media_type = None
    if artifact_path.suffix.lower() == ".html":
        media_type = "text/html"
    elif artifact_path.suffix.lower() == ".json":
        media_type = "application/json"
    if artifact_path.suffix.lower() == ".html":
        return FileResponse(
            artifact_path,
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{artifact_path.name}"'},
        )
    return FileResponse(artifact_path, media_type=media_type, filename=artifact_path.name)


@router.post("/graph/normalized", response_model=GraphExecutionNormalizedResponse)
async def execute_graph_normalized(request: GraphExecutionRequest):
    """Execute a graph and return a UI-friendly normalized payload."""
    result = await GraphService.execute_graph(
        request.graph_id,
        request.input,
        request.context,
        request.llm_override,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error
        )

    return GraphResponseNormalizer.normalize(result)


@router.post("/graph", response_model=GraphExecutionResponse)
async def execute_graph(request: GraphExecutionRequest):
    """Execute a graph with given input."""
    result = await GraphService.execute_graph(
        request.graph_id,
        request.input,
        request.context,
        request.llm_override,
    )

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
        request.context,
        request.llm_override,
        request.framework_override,
    )
    
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error
        )
    
    return result
