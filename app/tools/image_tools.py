import httpx
from typing import Any, Dict, Optional

from app.config import settings


DEFAULT_SYSTEM_PROMPT = (
    "You are a visual analysis expert. Describe the image content clearly, list any "
    "notable details, and answer the user request. Structure responses with headings when "
    "helpful and call out any uncertainties."
)

DEFAULT_USER_PROMPT = "Analyze this image:"


async def analyze_image(
    image_url: str,
    model: str,
    system_prompt: Optional[str] = None,
    user_prompt: Optional[str] = None,
    temperature: float = 0.2,
    top_p: float = 0.7,
    max_tokens: int = 1024,
    stream: bool = False,
) -> Dict[str, Any]:
    """Analyze an image using NVIDIA's vision chat completions endpoint."""
    api_key = settings.llm_api_key
    if not api_key:
        raise ValueError("LLM_API_KEY is required to run image analysis")

    base_url = settings.llm_base_url or "https://integrate.api.nvidia.com/v1"
    endpoint = f"{base_url.rstrip('/')}/chat/completions"

    payload = {
        "model": model,
        "messages": [
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
        ],
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "stream": stream,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    async with httpx.AsyncClient(verify=settings.ssl_verify) as client:
        response = await client.post(endpoint, json=payload, headers=headers, timeout=90.0)
        response.raise_for_status()
        data = response.json()

    message = None
    if isinstance(data, dict):
        message = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content")
        )

    return {
        "model": model,
        "analysis": message,
        "raw_response": data,
    }
