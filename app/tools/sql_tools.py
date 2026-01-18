import json
import re
import sqlite3
from typing import Any, Dict, List, Optional

from app.config import settings
from app.models import LLMConfig
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
    question: str,
    schema: str,
    sample_queries: str,
    sample_data: str,
    context: Optional[str],
    dialect: str,
) -> str:
    question = _coerce_text(question)
    schema = _coerce_text(schema)
    sample_queries = _coerce_text(sample_queries)
    sample_data = _coerce_text(sample_data)
    context = _coerce_text(context)
    sections = [
        f"SQL dialect: {dialect}",
        "\nSchema:\n" + schema.strip(),
        "\nSample queries (with context):\n" + sample_queries.strip(),
        "\nSample data:\n" + sample_data.strip(),
    ]
    if context:
        sections.append("\nAdditional context:\n" + context.strip())

    sections.append(
        "\nQuestion:\n" + question.strip()
    )

    return "\n\n".join(sections)


def _extract_sql(response: str) -> str:
    match = re.search(r"```sql\s*(.*?)```", response, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\s*(.*?)```", response, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return response.strip()


def _resolve_question(question: Optional[str], query: Optional[str]) -> str:
    if question:
        return question
    if query:
        return query
    return ""


def text_to_sql(
    question: Optional[str] = None,
    schema: str = "",
    sample_queries: str = "",
    sample_data: str = "",
    context: Optional[str] = None,
    dialect: str = "sqlite",
    query: Optional[str] = None,
    execute: bool = False,
    db_path: str = "",
    sql: Optional[str] = None,
    **_: Any,
) -> Dict[str, Any]:
    """Generate SQL from natural language using schema, samples, and context."""
    llm_config = LLMConfig(
        provider=settings.llm_provider,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )

    system_prompt = (
        "You are a database analyst. Generate a single SQL query that answers the user question. "
        "Use ONLY the provided schema and sample data context. Return SQL only."
    )

    resolved_question = _resolve_question(question, query)

    user_prompt = _build_prompt(
        question=resolved_question,
        schema=schema,
        sample_queries=sample_queries,
        sample_data=sample_data,
        context=context,
        dialect=dialect,
    )

    response = LLMService.invoke(llm_config, system_prompt, user_prompt)
    sql = _extract_sql(response)
    payload: Dict[str, Any] = {"sql": sql, "raw_response": response}

    if not execute:
        return payload

    if not db_path:
        return {
            **payload,
            "error": "db_path is required when execute=true",
        }

    try:
        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            cursor = connection.execute(sql)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            data = [dict(row) for row in rows]

        return {
            **payload,
            "columns": columns,
            "rows": data,
            "row_count": len(data),
        }
    except Exception as exc:
        return {
            **payload,
            "error": str(exc),
        }
