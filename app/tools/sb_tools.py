from __future__ import annotations

from typing import Any, Dict, Optional

from app.models import LLMConfig, LLMOverride
from app.sb.service import StarburstBIService


def sb_plan_request(
    question: str,
    conversation_history: Optional[Any] = None,
    llm_override: Optional[LLMOverride] = None,
    llm_config: Optional[LLMConfig] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    return StarburstBIService.plan_request(
        question=question,
        conversation_history=conversation_history,
        llm_override=llm_override,
        llm_config=llm_config,
        **kwargs,
    )


def sb_metadata_search(question: str, plan: Optional[Any] = None, **kwargs: Any) -> Dict[str, Any]:
    return StarburstBIService.metadata_search(question=question, plan=plan, **kwargs)


def sb_text_to_sql(
    question: str,
    plan: Optional[Any] = None,
    semantic_context: Optional[Any] = None,
    semantic_summary: Optional[str] = None,
    llm_override: Optional[LLMOverride] = None,
    llm_config: Optional[LLMConfig] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    return StarburstBIService.text_to_sql(
        question=question,
        plan=plan,
        semantic_context=semantic_context,
        semantic_summary=semantic_summary,
        llm_override=llm_override,
        llm_config=llm_config,
        **kwargs,
    )


def sb_validate_sql(sql: str, **kwargs: Any) -> Dict[str, Any]:
    return StarburstBIService.validate_sql(sql=sql, **kwargs)


def sb_execute_sql(sql: str, **kwargs: Any) -> Dict[str, Any]:
    return StarburstBIService.execute_sql(sql=sql, **kwargs)


def sb_profile_results(rows: Optional[Any] = None, columns: Optional[Any] = None, question: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
    return StarburstBIService.profile_results(rows=rows, columns=columns, question=question, **kwargs)


def sb_recommend_visualization(profile: Optional[Any] = None, question: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
    return StarburstBIService.recommend_visualization(profile=profile, question=question, **kwargs)


def sb_create_visualization(data: Optional[Any] = None, recommendation: Optional[Any] = None, **kwargs: Any) -> Dict[str, Any]:
    return StarburstBIService.create_visualization(data=data, recommendation=recommendation, **kwargs)


def sb_save_analysis(question: str, **kwargs: Any) -> Dict[str, Any]:
    return StarburstBIService.save_analysis(question=question, **kwargs)


def sb_load_analysis(analysis_id: str, **kwargs: Any) -> Dict[str, Any]:
    return StarburstBIService.load_analysis(analysis_id=analysis_id, **kwargs)


def sb_list_catalogs(**kwargs: Any) -> Dict[str, Any]:
    return StarburstBIService.list_catalogs(**kwargs)


def sb_list_schemas(catalog: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
    return StarburstBIService.list_schemas(catalog=catalog, **kwargs)


def sb_list_tables(catalog: Optional[str] = None, schema: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
    return StarburstBIService.list_tables(catalog=catalog, schema=schema, **kwargs)


def sb_describe_table(table_name: str, catalog: Optional[str] = None, schema: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
    return StarburstBIService.describe_table(table_name=table_name, catalog=catalog, schema=schema, **kwargs)


def sb_format_answer(
    question: str,
    plan: Optional[Any] = None,
    semantic_summary: Optional[str] = None,
    sql: Optional[str] = None,
    validation: Optional[Any] = None,
    rows: Optional[Any] = None,
    profile: Optional[Any] = None,
    visualization: Optional[Any] = None,
    analysis_record: Optional[Any] = None,
    llm_override: Optional[LLMOverride] = None,
    llm_config: Optional[LLMConfig] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    return StarburstBIService.format_answer(
        question=question,
        plan=plan,
        semantic_summary=semantic_summary,
        sql=sql,
        validation=validation,
        rows=rows,
        profile=profile,
        visualization=visualization,
        analysis_record=analysis_record,
        llm_override=llm_override,
        llm_config=llm_config,
        **kwargs,
    )
