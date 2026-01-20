import json
import logging
import os
import re
from typing import Optional, Any
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from app.models import LLMConfig, LLMOverride
from app.config import settings


class LLMService:

    logger = logging.getLogger(__name__)

    @staticmethod
    def _expand_env_value(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if "${" not in value:
            return value
        pattern = r"\$\{([^}]+)\}"
        resolved = value
        for match in re.findall(pattern, value):
            env_value = os.getenv(match, "")
            resolved = resolved.replace(f"${{{match}}}", env_value)
        return resolved

    @staticmethod
    def _expand_env_in_additional_params(params: Optional[dict]) -> Optional[dict]:
        if not params:
            return params
        expanded: dict[str, Any] = {}
        for key, value in params.items():
            if isinstance(value, str):
                expanded[key] = LLMService._expand_env_value(value)
            else:
                expanded[key] = value
        return expanded

    @staticmethod
    def _default_config() -> LLMConfig:
        return LLMConfig(
            provider=settings.llm_provider,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )

    @staticmethod
    def resolve_llm_config(
        base_config: Optional[LLMConfig] = None,
        override: Optional[LLMOverride] = None,
    ) -> LLMConfig:
        config = base_config or LLMService._default_config()
        if not override:
            return config

        expanded_provider = LLMService._expand_env_value(override.provider)
        expanded_model = LLMService._expand_env_value(override.model)
        expanded_api_key = LLMService._expand_env_value(override.api_key)
        expanded_base_url = LLMService._expand_env_value(override.base_url)
        expanded_additional = LLMService._expand_env_in_additional_params(override.additional_params)

        resolved = config.model_copy(
            update={
                "provider": expanded_provider or config.provider,
                "model": expanded_model or config.model,
                "api_key": expanded_api_key if override.api_key is not None else config.api_key,
                "base_url": expanded_base_url if override.base_url is not None else config.base_url,
                "temperature": override.temperature if override.temperature is not None else config.temperature,
                "max_tokens": override.max_tokens if override.max_tokens is not None else config.max_tokens,
            }
        )

        if expanded_additional is not None:
            resolved.additional_params = {
                **(config.additional_params or {}),
                **expanded_additional,
            }

        return resolved
    
    @staticmethod
    def get_llm(llm_config: Optional[LLMConfig] = None):
        """Get LLM instance based on configuration."""
        LLMService.logger.debug("Initializing LLM instance")
        if llm_config is None:
            llm_config = LLMService._default_config()

        api_key = llm_config.api_key or settings.llm_api_key
        reserved_keys = {"model", "api_key", "base_url", "temperature", "max_tokens", "groq_api_key"}
        extra_params = {
            key: value
            for key, value in (llm_config.additional_params or {}).items()
            if key not in reserved_keys
        }

        if llm_config.provider.lower() == "groq":
            LLMService.logger.debug(f"Using Groq provider with model: {llm_config.model}")
            return ChatGroq(
                model=llm_config.model,
                groq_api_key=api_key,
                temperature=llm_config.temperature,
                max_tokens=llm_config.max_tokens,
                **extra_params,
            )
        elif llm_config.provider.lower() in ["openai", "nvidia", "openai_compatible"]:
            base_url = llm_config.base_url or settings.llm_base_url
            if llm_config.provider.lower() == "nvidia":
                base_url = base_url or "https://integrate.api.nvidia.com/v1"
            
            LLMService.logger.debug(f"Using {llm_config.provider} provider with model: {llm_config.model}, base_url: {base_url}")
            return ChatOpenAI(
                model=llm_config.model,
                api_key=api_key,
                base_url=base_url,
                temperature=llm_config.temperature,
                max_tokens=llm_config.max_tokens,
                **extra_params,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {llm_config.provider}")
    
    @staticmethod
    def invoke(llm_config: LLMConfig, system_prompt: str, user_message: str) -> str:
        """Invoke LLM with system and user messages."""
        LLMService.logger.debug(f"Invoking LLM: {llm_config.provider}/{llm_config.model}")
        llm = LLMService.get_llm(llm_config)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ]

        if settings.debug_trace:
            LLMService.logger.debug(
                "LLM request: %s",
                json.dumps(
                    {
                        "provider": llm_config.provider,
                        "model": llm_config.model,
                        "messages": [m.model_dump() for m in messages],
                    },
                    default=str,
                ),
            )

        response = llm.invoke(messages)
        LLMService.logger.debug(f"LLM response received (length: {len(response.content)} chars)")

        if settings.debug_trace:
            LLMService.logger.debug(
                "LLM response: %s",
                json.dumps(
                    {
                        "content": response.content,
                        "additional": getattr(response, "additional_kwargs", {}),
                    },
                    default=str,
                ),
            )
        return response.content
