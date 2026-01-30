import json
import logging
import os
import re
from typing import Optional, Any, Iterable

import httpx
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from app.models import LLMConfig, LLMOverride
from app.config import settings
from app.services.openai_http_logger import OpenAIHTTPLogger


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
    def _build_callbacks():
        callbacks = []
        if settings.debug_trace:
            callbacks.append(OpenAIHTTPLogger(enabled=True))
            LLMService.logger.debug("OpenAI HTTP payload logging enabled")

        if settings.langfuse_enabled:
            try:
                from langfuse.langchain import CallbackHandler

                if settings.langfuse_public_key:
                    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
                if settings.langfuse_secret_key:
                    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
                if settings.langfuse_host:
                    os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)

                callbacks.append(CallbackHandler())
                LLMService.logger.debug("Langfuse callback enabled")
            except Exception as exc:
                LLMService.logger.warning("Langfuse callback disabled: %s", exc)

        return callbacks

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

        def _strip_extra_headers(request: httpx.Request) -> None:
            for header in list(request.headers.keys()):
                header_lower = header.lower()
                if header_lower == "x-stainless-raw-response":
                    continue
                if header_lower.startswith("x-stainless-"):
                    request.headers.pop(header, None)

        http_client = httpx.Client(
            verify=settings.ssl_verify,
            event_hooks={"request": [_strip_extra_headers]},
        )
        http_async_client = httpx.AsyncClient(
            verify=settings.ssl_verify,
            event_hooks={"request": [_strip_extra_headers]},
        )

        def _build_client(client_cls, **kwargs):
            try:
                return client_cls(
                    **kwargs,
                    http_client=http_client,
                    http_async_client=http_async_client,
                )
            except TypeError:
                return client_cls(**kwargs)

        if llm_config.provider.lower() != "openai":
            raise ValueError(f"Unsupported LLM provider: {llm_config.provider}")

        base_url = llm_config.base_url or settings.llm_base_url

        LLMService.logger.debug(
            "Using OpenAI provider with model: %s, base_url: %s",
            llm_config.model,
            base_url,
        )

        callbacks = LLMService._build_callbacks()

        return _build_client(
            ChatOpenAI,
            model=llm_config.model,
            api_key=api_key,
            base_url=base_url,
            callbacks=callbacks if callbacks else None,
            **request_params,
        )
    
    @staticmethod
    def invoke(llm_config: LLMConfig, system_prompt: str, user_message: str) -> str:
        """Invoke LLM with system and user messages."""
        LLMService.logger.debug(f"Invoking LLM: {llm_config.provider}/{llm_config.model}")
        llm = LLMService.get_llm(llm_config)
        messages = [
            SystemMessage(content=system_prompt or ""),
            HumanMessage(content=user_message or "")
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
