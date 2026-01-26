from app.services.agent_frameworks.registry import framework_registry
from app.services.agent_frameworks.langgraph_adapter import LangGraphAdapter
from app.services.agent_frameworks.google_adk_adapter import GoogleADKAdapter
from app.services.agent_frameworks.openai_direct_adapter import OpenAIDirectAdapter

framework_registry.register(LangGraphAdapter())
framework_registry.register(GoogleADKAdapter())
framework_registry.register(OpenAIDirectAdapter())

__all__ = ["framework_registry", "LangGraphAdapter", "GoogleADKAdapter", "OpenAIDirectAdapter"]
