from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import admin, execution
from app.config import settings
import logging

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True
)

logger = logging.getLogger(__name__)
logger.info("ADK logging configured at level=%s", settings.log_level.upper())

app = FastAPI(
    title="Agent Development Kit (ADK)",
    description="Simple base agent development framework with YAML configs and REST APIs",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin.router)
app.include_router(execution.router)


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Agent Development Kit (ADK)",
        "version": "1.0.0",
        "description": "Simple base agent development framework",
        "endpoints": {
            "admin": {
                "tools": "/admin/tools",
                "agents": "/admin/agents"
            },
            "execution": {
                "tool": "/execute/tool",
                "agent": "/execute/agent"
            },
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}
