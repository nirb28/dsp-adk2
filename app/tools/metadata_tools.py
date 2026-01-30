import json
from typing import Any, Dict, Optional

from app.config import settings
from app.models import LLMConfig, LLMOverride
from app.services.llm_service import LLMService


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def _build_prompt(
    schema: str,
    sample_metadata: str,
    context: Optional[str],
    dialect: str,
) -> str:
    schema = _coerce_text(schema)
    sample_metadata = _coerce_text(sample_metadata)
    context = _coerce_text(context)

    sections = [
        f"SQL dialect: {dialect}",
        "\nSchema:\n" + schema.strip(),
        "\nSample metadata (format guidance):\n" + sample_metadata.strip(),
    ]
    if context:
        sections.append("\nAdditional context:\n" + context.strip())

    sections.append(
        "\nTask:\nGenerate metadata for every column in every table."
    )

    return "\n\n".join(sections)


def _parse_json_response(response: str) -> Dict[str, Any]:
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return {"raw_response": response}


def column_metadata(
    schema: str,
    sample_metadata: str,
    context: Optional[str] = None,
    dialect: str = "sqlite",
    llm_override: Optional[LLMOverride] = None,
    llm_config: Optional[LLMConfig] = None,
    **_: Any,
) -> Dict[str, Any]:
    """Generate column metadata for all tables in a schema using LLM."""
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

    system_prompt = (
        "You are a data catalog assistant. Generate metadata for every column in the schema. "
        "Use the sample metadata format. Return JSON only."
    )

    user_prompt = _build_prompt(
        schema=schema,
        sample_metadata=sample_metadata,
        context=context,
        dialect=dialect,
    )

    response = LLMService.invoke(llm_config, system_prompt, user_prompt)
    parsed = _parse_json_response(response)

    if "raw_response" in parsed:
        return {
            "metadata": None,
            "raw_response": response,
            "error": "Response was not valid JSON",
        }

    return {
        "metadata": parsed,
        "raw_response": response,
    }
