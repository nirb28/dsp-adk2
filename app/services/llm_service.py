import json
import logging
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from app.models import LLMConfig
from app.config import settings


class LLMService:

    logger = logging.getLogger(__name__)
    
    @staticmethod
    def get_llm(llm_config: Optional[LLMConfig] = None):
        """Get LLM instance based on configuration."""
        LLMService.logger.debug("Initializing LLM instance")
        if llm_config is None:
            llm_config = LLMConfig(
                provider=settings.llm_provider,
                model=settings.llm_model,
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens
            )
        
        api_key = llm_config.api_key or settings.llm_api_key

        if llm_config.provider.lower() == "groq":
            LLMService.logger.debug(f"Using Groq provider with model: {llm_config.model}")
            return ChatGroq(
                model=llm_config.model,
                groq_api_key=api_key,
                temperature=llm_config.temperature,
                max_tokens=llm_config.max_tokens
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
                max_tokens=llm_config.max_tokens
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
