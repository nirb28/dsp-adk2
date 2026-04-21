import json
import logging
import os
import re
import time
from typing import Optional, Any, Iterable

import httpx
import openai
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from app.models import LLMConfig, LLMOverride
from app.config import settings
from app.services.openai_http_logger import OpenAIHTTPLogger


class LLMService:

    logger = logging.getLogger(__name__)
    _max_invoke_retries = 3

    @staticmethod
    def _expand_env_value(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if "${" not in value:
            return value
        pattern = r"\$\{([^}]+)\}"
        resolved = value
        # Support nested indirection such as ${LLM_BASE_URL} -> ${AZURE_OPENAI_BASE_URL} -> https://...
        for _ in range(3):
            matches = re.findall(pattern, resolved)
            if not matches:
                break
            updated = resolved
            for match in matches:
                env_value = os.getenv(match, "")
                updated = updated.replace(f"${{{match}}}", env_value)
            if updated == resolved:
                break
            resolved = updated
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

        # Always expand env placeholders from YAML/base config values (e.g. ${LLM_BASE_URL})
        # before applying request-time overrides.
        config = config.model_copy(
            update={
                "provider": LLMService._expand_env_value(config.provider) or config.provider,
                "model": LLMService._expand_env_value(config.model) or config.model,
                "api_key": LLMService._expand_env_value(config.api_key)
                if config.api_key is not None
                else None,
                "base_url": LLMService._expand_env_value(config.base_url)
                if config.base_url is not None
                else None,
            }
        )
        config.additional_params = LLMService._expand_env_in_additional_params(config.additional_params)

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
    def _normalize_positive_int(value: Any, field_name: str) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, bool):
            LLMService.logger.warning("Ignoring non-integer %s value: %s", field_name, value)
            return None
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            LLMService.logger.warning("Ignoring invalid %s value: %s", field_name, value)
            return None
        if normalized < 1:
            LLMService.logger.warning("Ignoring non-positive %s value: %s", field_name, value)
            return None
        return normalized

    @staticmethod
    def build_openai_request_params(
        llm_config: LLMConfig,
        *,
        max_tokens_value: Any = None,
        temperature_value: Optional[float] = None,
        top_p_value: Optional[float] = None,
        for_langchain: bool = False,
    ) -> dict[str, Any]:
        additional_params = dict(llm_config.additional_params or {})
        disabled_params = additional_params.pop("disabled_params", None)
        additional_params.pop("model", None)
        additional_params.pop("api_key", None)
        additional_params.pop("base_url", None)
        additional_params.pop("temperature", None)
        additional_params.pop("max_tokens", None)
        additional_params.pop("max_completion_tokens", None)
        additional_params.pop("max_output_tokens", None)
        additional_params.pop("extra_headers", None)

        request_params = dict(additional_params)
        request_params["temperature"] = (
            llm_config.temperature if temperature_value is None else temperature_value
        )

        if top_p_value is None and "top_p" in request_params:
            top_p_value = request_params.pop("top_p")
        if top_p_value is not None:
            request_params["top_p"] = top_p_value

        effective_max_tokens = LLMService._normalize_positive_int(
            llm_config.max_tokens if max_tokens_value is None else max_tokens_value,
            "max_tokens",
        )

        if effective_max_tokens is not None and not (
            for_langchain and settings.llm_disable_max_completion_tokens
        ):
            request_params["max_tokens"] = effective_max_tokens

        if for_langchain:
            merged_disabled_params = dict(disabled_params) if isinstance(disabled_params, dict) else {}
            if settings.llm_disable_max_completion_tokens:
                merged_disabled_params["max_completion_tokens"] = None
                merged_disabled_params["max_output_tokens"] = None
            if merged_disabled_params:
                request_params["disabled_params"] = merged_disabled_params

        return request_params
    
    @staticmethod
    def get_llm(llm_config: Optional[LLMConfig] = None):
        """Get LLM instance based on configuration."""
        LLMService.logger.debug("Initializing LLM instance")
        if llm_config is None:
            llm_config = LLMService._default_config()

        api_key = llm_config.api_key or settings.llm_api_key
        request_params = LLMService.build_openai_request_params(
            llm_config,
            max_tokens_value=llm_config.max_tokens,
            for_langchain=True,
        )

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
    def _extract_retry_delay(exc: Exception, attempt: int) -> float:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", {}) or {}
        retry_after = headers.get("retry-after")
        if retry_after:
            try:
                return max(float(retry_after), 1.0)
            except (TypeError, ValueError):
                pass
        return float(min(60, 2 ** attempt))

    @staticmethod
    def _is_retryable_rate_limit(exc: Exception) -> bool:
        if isinstance(exc, openai.RateLimitError):
            return True
        if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None and exc.response.status_code == 429:
            return True
        status_code = getattr(exc, "status_code", None)
        if status_code == 429:
            return True
        message = str(exc).lower()
        return "429" in message or "rate limit" in message or "too many requests" in message
    
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

        last_exc: Optional[Exception] = None
        for attempt in range(LLMService._max_invoke_retries + 1):
            try:
                response = llm.invoke(messages)
                break
            except Exception as exc:
                last_exc = exc
                if attempt >= LLMService._max_invoke_retries or not LLMService._is_retryable_rate_limit(exc):
                    raise
                delay_seconds = LLMService._extract_retry_delay(exc, attempt)
                LLMService.logger.warning(
                    "LLM rate-limited for %s/%s on attempt %s/%s. Retrying in %.1f seconds.",
                    llm_config.provider,
                    llm_config.model,
                    attempt + 1,
                    LLMService._max_invoke_retries + 1,
                    delay_seconds,
                )
                time.sleep(delay_seconds)
        else:
            if last_exc is not None:
                raise last_exc
            raise RuntimeError("LLM invocation failed without a response")

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
