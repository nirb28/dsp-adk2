from typing import Any, Dict, Optional

from app.config import settings
from app.models import LLMConfig, LLMOverride
from app.services.llm_service import LLMService


DEFAULT_SYSTEM_PROMPT = (
    "You are a visual analysis expert. Describe the image content clearly, list any "
    "notable details, and answer the user request. Structure responses with headings when "
    "helpful and call out any uncertainties."
)

DEFAULT_USER_PROMPT = "Analyze this image:"


async def analyze_image(
    image_url: str,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    user_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    max_tokens: Optional[int] = None,
    stream: bool = False,
    llm_override: Optional[LLMOverride] = None,
    llm_config: Optional[LLMConfig] = None,
) -> Dict[str, Any]:
    """Analyze an image using OpenAI vision chat completions."""
    try:
        import openai
    except ImportError as exc:
        raise ImportError(
            "openai package is required for image analysis. Install with 'pip install openai'."
        ) from exc

    if llm_config is None:
        llm_config = LLMConfig(
            provider=settings.llm_provider,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
    llm_config = LLMService.resolve_llm_config(llm_config, llm_override)

    resolved_model = model or llm_config.model
    api_key = llm_config.api_key or settings.llm_api_key
    if not api_key:
        raise ValueError("LLM_API_KEY is required to run image analysis")

    client = openai.OpenAI(api_key=api_key, base_url=llm_config.base_url or settings.llm_base_url)

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
    if top_p is None and "top_p" in extra_params:
        top_p = extra_params.pop("top_p")

    request_params: Dict[str, Any] = {
        **extra_params,
    }
    request_params["temperature"] = llm_config.temperature if temperature is None else temperature
    request_params["max_tokens"] = llm_config.max_tokens if max_tokens is None else max_tokens
    if top_p is not None:
        request_params["top_p"] = top_p
    request_params.pop("extra_headers", None)

    messages = [
        {
            "role": "system",
            "content": system_prompt or DEFAULT_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_prompt or DEFAULT_USER_PROMPT},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        },
    ]

    if stream:
        content_parts = []
        raw_chunks = []
        response = client.chat.completions.create(
            model=resolved_model,
            messages=messages,
            stream=True,
            **request_params,
        )
        for chunk in response:
            raw_chunks.append(chunk.model_dump())
            delta = chunk.choices[0].delta
            if delta and getattr(delta, "content", None):
                content_parts.append(delta.content)
        message = "".join(content_parts).strip() if content_parts else None
        raw_response: Any = raw_chunks
    else:
        response = client.chat.completions.create(
            model=resolved_model,
            messages=messages,
            stream=False,
            **request_params,
        )
        message = response.choices[0].message.content if response.choices else None
        raw_response = response.model_dump()

    return {
        "model": resolved_model,
        "analysis": message,
        "raw_response": raw_response,
    }
