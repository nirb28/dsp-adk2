import json
import logging
import os
import re
from typing import Optional, Any, Iterable

import httpx
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
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
    def _parse_csv(value: Optional[str]) -> set[str]:
        if not value:
            return set()
        return {item.strip() for item in value.split(",") if item.strip()}

    @staticmethod
    def _parse_rename_map(value: Optional[str]) -> dict[str, str]:
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            LLMService.logger.warning("Invalid llm_request_param_rename JSON; ignoring")
            return {}
        if not isinstance(parsed, dict):
            LLMService.logger.warning("llm_request_param_rename must be a JSON object; ignoring")
            return {}
        return {str(key): str(val) for key, val in parsed.items()}

    @staticmethod
    def _apply_request_param_policy(
        params: dict[str, Any],
        allowlist: Optional[str] = None,
        denylist: Optional[str] = None,
        rename_map: Optional[str] = None,
    ) -> dict[str, Any]:
        rename_map = LLMService._parse_rename_map(rename_map)
        if rename_map:
            applied_renames = {
                key: rename_map[key]
                for key in params.keys()
                if key in rename_map and rename_map[key] != key
            }
            if applied_renames:
                LLMService.logger.debug("LLM request param renames applied: %s", applied_renames)
        renamed: dict[str, Any] = {}
        for key, value in params.items():
            renamed_key = rename_map.get(key, key)
            renamed[renamed_key] = value

        allowlist = LLMService._parse_csv(allowlist)
        denylist = LLMService._parse_csv(denylist)

        if allowlist:
            before_allow = set(renamed.keys())
            renamed = {key: val for key, val in renamed.items() if key in allowlist}
            denied_by_allowlist = sorted(before_allow - set(renamed.keys()))
            LLMService.logger.debug(
                "LLM request param allowlist applied. Allowed: %s Denied: %s",
                sorted(allowlist),
                denied_by_allowlist,
            )
        if denylist:
            before_deny = set(renamed.keys())
            renamed = {key: val for key, val in renamed.items() if key not in denylist}
            denied_by_denylist = sorted(before_deny - set(renamed.keys()))
            LLMService.logger.debug(
                "LLM request param denylist applied. Denied: %s",
                denied_by_denylist,
            )

        return renamed

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
                "send_additional_params": (
                    override.send_additional_params
                    if override.send_additional_params is not None
                    else config.send_additional_params
                ),
                "request_param_allowlist": (
                    override.request_param_allowlist
                    if override.request_param_allowlist is not None
                    else config.request_param_allowlist
                ),
                "request_param_denylist": (
                    override.request_param_denylist
                    if override.request_param_denylist is not None
                    else config.request_param_denylist
                ),
                "request_param_rename": (
                    override.request_param_rename
                    if override.request_param_rename is not None
                    else config.request_param_rename
                ),
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
        extra_params: dict[str, Any] = {}
        send_additional_params = (
            llm_config.send_additional_params
            if llm_config.send_additional_params is not None
            else settings.llm_send_additional_params
        )
        if send_additional_params:
            extra_params = {
                key: value
                for key, value in (llm_config.additional_params or {}).items()
                if key not in reserved_keys
            }
        allowlist = llm_config.request_param_allowlist or settings.llm_request_param_allowlist
        denylist = llm_config.request_param_denylist or settings.llm_request_param_denylist
        rename_map = llm_config.request_param_rename or settings.llm_request_param_rename
        request_params = LLMService._apply_request_param_policy(
            {
                "temperature": llm_config.temperature,
                "max_tokens": llm_config.max_tokens,
                **extra_params,
            },
            allowlist=allowlist,
            denylist=denylist,
            rename_map=rename_map,
        )

        http_client = httpx.Client(verify=settings.ssl_verify)
        http_async_client = httpx.AsyncClient(verify=settings.ssl_verify)

        def _build_client(client_cls, **kwargs):
            try:
                return client_cls(
                    **kwargs,
                    http_client=http_client,
                    http_async_client=http_async_client,
                )
            except TypeError:
                return client_cls(**kwargs)

        if llm_config.provider.lower() == "groq":
            LLMService.logger.debug(f"Using Groq provider with model: {llm_config.model}")
            callbacks = LLMService._build_callbacks()
            return _build_client(
                ChatGroq,
                model=llm_config.model,
                groq_api_key=api_key,
                callbacks=callbacks if callbacks else None,
                **request_params,
            )
        elif llm_config.provider.lower() in ["openai", "nvidia", "openai_compatible"]:
            base_url = llm_config.base_url or settings.llm_base_url
            if llm_config.provider.lower() == "nvidia":
                base_url = base_url or "https://integrate.api.nvidia.com/v1"
            
            LLMService.logger.debug(f"Using {llm_config.provider} provider with model: {llm_config.model}, base_url: {base_url}")
            
            callbacks = LLMService._build_callbacks()
            
            return _build_client(
                ChatOpenAI,
                model=llm_config.model,
                api_key=api_key,
                base_url=base_url,
                callbacks=callbacks if callbacks else None,
                **request_params,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {llm_config.provider}")
    
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
