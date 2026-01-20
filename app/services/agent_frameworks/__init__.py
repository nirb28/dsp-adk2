from app.services.agent_frameworks.registry import framework_registry
from app.services.agent_frameworks.langgraph_adapter import LangGraphAdapter
from app.services.agent_frameworks.google_adk_adapter import GoogleADKAdapter

framework_registry.register(LangGraphAdapter())
framework_registry.register(GoogleADKAdapter())

__all__ = ["framework_registry", "LangGraphAdapter", "GoogleADKAdapter"]
