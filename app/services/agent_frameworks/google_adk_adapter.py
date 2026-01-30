from __future__ import annotations

import logging
import os
from typing import Dict, Any, List, Tuple, Optional

from app.models import AgentConfig, LLMOverride
from app.config import settings
from app.services.llm_service import LLMService
from app.services.agent_frameworks.base import AgentFramework
from app.services.tool_service import ToolService
from app.services.yaml_service import YAMLService


class GoogleADKAdapter(AgentFramework):
    name = "google_adk"

    logger = logging.getLogger(__name__)

    async def execute(
        self,
        agent_config: AgentConfig,
        user_input: str,
        context: Dict[str, Any],
        llm_override: Optional[LLMOverride] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        try:
            from google.adk.agents import LlmAgent
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
            from google.genai import types
        except ImportError as exc:
            raise ImportError(
                "google-adk is required for google_adk framework. Install with 'pip install google-adk'."
            ) from exc

        llm_config = LLMService.resolve_llm_config(agent_config.llm_config, llm_override)
        google_api_key = llm_config.api_key or settings.llm_api_key
        if google_api_key:
            os.environ["GOOGLE_API_KEY"] = google_api_key

        tools = []
        for tool_name in agent_config.tools:
            tool_config = YAMLService.load_tool(tool_name)
            if not tool_config:
                continue

            async def tool_func(tool_name_arg=tool_name, **kwargs):
                result = await ToolService.execute_tool(tool_name_arg, kwargs, llm_override, llm_config)
                if result.success:
                    return result.result
                return {"error": result.error}

            tool_func.__name__ = tool_name
            tool_func.__doc__ = tool_config.description
            tools.append(tool_func)

        adk_agent = LlmAgent(
            name=agent_config.name,
            model=llm_config.model,
            instruction=agent_config.system_prompt,
            description=agent_config.description,
            tools=tools,
        )

        app_name = agent_config.metadata.get("app_name", agent_config.name)
        user_id = agent_config.metadata.get("user_id", "local-user")
        session_id = agent_config.metadata.get("session_id", "local-session")

        session_service = InMemorySessionService()
        await session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )

        runner = Runner(agent=adk_agent, app_name=app_name, session_service=session_service)
        content = types.Content(role="user", parts=[types.Part(text=user_input)])
        events = runner.run_async(user_id=user_id, session_id=session_id, new_message=content)

        steps: List[Dict[str, Any]] = []
        final_output = ""

        async for event in events:
            step: Dict[str, Any] = {"type": "adk_event"}
            event_type = getattr(event, "type", None)
            if event_type is not None:
                step["event_type"] = event_type

            content_text = None
            if getattr(event, "content", None) is not None and getattr(event.content, "parts", None):
                part = event.content.parts[0]
                content_text = getattr(part, "text", None)

            if content_text:
                step["content"] = content_text

            steps.append(step)

            if hasattr(event, "is_final_response") and event.is_final_response():
                final_output = content_text or ""

        return final_output, steps
