from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple, Optional

from app.config import settings
from app.models import AgentConfig, LLMOverride
from app.services.agent_frameworks.base import AgentFramework
from app.services.llm_service import LLMService
from app.services.tool_service import ToolService
from app.services.yaml_service import YAMLService


class OpenAIDirectAdapter(AgentFramework):
    name = "openai_direct"

    logger = logging.getLogger(__name__)

    async def execute(
        self,
        agent_config: AgentConfig,
        user_input: str,
        context: Dict[str, Any],
        llm_override: Optional[LLMOverride] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        try:
            import openai
        except ImportError as exc:
            raise ImportError(
                "openai package is required for openai_direct framework. Install with 'pip install openai'."
            ) from exc

        llm_config = LLMService.resolve_llm_config(agent_config.llm_config, llm_override)
        api_key = llm_config.api_key or settings.llm_api_key
        base_url = llm_config.base_url or settings.llm_base_url

        client = openai.OpenAI(api_key=api_key, base_url=base_url)

        reserved_keys = {
            "model",
            "api_key",
            "base_url",
            "temperature",
            "max_tokens",
            "extra_headers",
        }
        extra_params = {
            key: value
            for key, value in (llm_config.additional_params or {}).items()
            if key not in reserved_keys
        }
        request_params = {
            "temperature": llm_config.temperature,
            "max_tokens": llm_config.max_tokens,
            **extra_params,
        }
        request_params.pop("extra_headers", None)

        tool_schemas: List[Dict[str, Any]] = []
        tool_lookup: Dict[str, str] = {}
        for tool_name in agent_config.tools:
            tool_config = YAMLService.load_tool(tool_name)
            if not tool_config:
                continue
            tool_schemas.append(ToolService.get_tool_schema(tool_config))
            tool_lookup[tool_config.name] = tool_config.description

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": agent_config.system_prompt},
            {"role": "user", "content": user_input},
        ]

        steps: List[Dict[str, Any]] = []
        final_output = ""

        for iteration in range(agent_config.max_iterations):
            if settings.debug_trace:
                self.logger.debug(
                    "OpenAI Direct request: %s",
                    json.dumps(
                        {
                            "provider": llm_config.provider,
                            "model": llm_config.model,
                            "messages": messages,
                            "tool_names": list(tool_lookup.keys()),
                            "iteration": iteration,
                        },
                        default=str,
                    ),
                )

            response = client.chat.completions.create(
                model=llm_config.model,
                messages=messages,
                tools=tool_schemas or None,
                **request_params,
            )

            message = response.choices[0].message
            content = message.content or ""
            tool_calls = []
            if getattr(message, "tool_calls", None):
                for call in message.tool_calls:
                    tool_calls.append(
                        {
                            "id": call.id,
                            "type": call.type,
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                    )

            steps.append(
                {
                    "type": "reasoning",
                    "content": content,
                    "tool_calls": tool_calls,
                    "iteration": iteration,
                }
            )

            assistant_message: Dict[str, Any] = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            messages.append(assistant_message)

            final_output = content or final_output

            if not tool_calls:
                return final_output, steps

            for tool_call in tool_calls:
                tool_name = tool_call["function"]["name"]
                raw_args = tool_call["function"].get("arguments") or "{}"
                try:
                    parsed_args = json.loads(raw_args)
                    if not isinstance(parsed_args, dict):
                        parsed_args = {"value": parsed_args}
                except json.JSONDecodeError:
                    parsed_args = {"_raw": raw_args}

                tool_result = await ToolService.execute_tool(tool_name, parsed_args, llm_override, llm_config)
                if tool_result.success:
                    tool_content: Any = tool_result.result
                else:
                    tool_content = {"error": tool_result.error}

                tool_payload = tool_content if isinstance(tool_content, str) else json.dumps(tool_content, default=str)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": tool_payload,
                    }
                )

                steps.append(
                    {
                        "type": "tool",
                        "tool": tool_name,
                        "tool_call_id": tool_call["id"],
                        "result": tool_result.result if tool_result.success else None,
                        "error": None if tool_result.success else tool_result.error,
                    }
                )

        return final_output, steps
