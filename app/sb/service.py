from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from app.config import settings
from app.models import LLMConfig, LLMOverride
from app.sb.analysis_store import AnalysisStore
from app.sb.charting import create_visualization
from app.sb.client import get_starburst_client
from app.sb.metadata import search_semantic_metadata
from app.sb.profiler import profile_result_set, recommend_visualization
from app.sb.safety import validate_sql
from app.sb.utils import coerce_text, ensure_dict, ensure_json_text, ensure_list, expand_sql_placeholders, truncate_rows
from app.services.llm_service import LLMService


class StarburstBIService:
    @staticmethod
    def _default_llm_config() -> LLMConfig:
        return LLMConfig(
            provider=settings.llm_provider,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )

    @staticmethod
    def _resolve_llm_config(
        llm_override: Optional[LLMOverride] = None,
        llm_config: Optional[LLMConfig] = None,
    ) -> LLMConfig:
        base = llm_config or StarburstBIService._default_llm_config()
        return LLMService.resolve_llm_config(base, llm_override)

    @staticmethod
    def _parse_json_response(response: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
        try:
            parsed = json.loads(response)
            return parsed if isinstance(parsed, dict) else {"value": parsed, **fallback}
        except json.JSONDecodeError:
            return {**fallback, "raw_response": response}

    @staticmethod
    def plan_request(
        question: str,
        conversation_history: Optional[Any] = None,
        llm_override: Optional[LLMOverride] = None,
        llm_config: Optional[LLMConfig] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        resolved_config = StarburstBIService._resolve_llm_config(llm_override, llm_config)
        system_prompt = (
            "You are a BI planning assistant. Convert the user request into JSON only. "
            "Return keys: intent, metric, dimensions, filters, time_grain, comparison, requested_visualization, needs_visualization, answer_format, ambiguities."
        )
        user_prompt = (
            f"Question:\n{coerce_text(question)}\n\n"
            f"Conversation history:\n{coerce_text(conversation_history)}"
        )
        response = LLMService.invoke(resolved_config, system_prompt, user_prompt)
        fallback = {
            "intent": "analysis",
            "metric": None,
            "dimensions": [],
            "filters": [],
            "time_grain": None,
            "comparison": None,
            "requested_visualization": None,
            "needs_visualization": True,
            "answer_format": "summary_with_sql",
            "ambiguities": [],
        }
        parsed = StarburstBIService._parse_json_response(response, fallback)
        return {**fallback, **parsed, "raw_response": response}

    @staticmethod
    def metadata_search(
        question: str,
        plan: Optional[Any] = None,
        metadata_file: Optional[str] = None,
        include_live_schema: bool = False,
        catalog: Optional[str] = None,
        schema: Optional[str] = None,
        max_results: int = 5,
        **connection_kwargs: Any,
    ) -> Dict[str, Any]:
        return search_semantic_metadata(
            question=question,
            plan=plan,
            metadata_file=metadata_file,
            include_live_schema=include_live_schema,
            catalog=catalog,
            schema=schema,
            max_results=max_results,
            **connection_kwargs,
        )

    @staticmethod
    def text_to_sql(
        question: str,
        plan: Optional[Any] = None,
        semantic_context: Optional[Any] = None,
        semantic_summary: Optional[str] = None,
        catalog: Optional[str] = None,
        schema: Optional[str] = None,
        llm_override: Optional[LLMOverride] = None,
        llm_config: Optional[LLMConfig] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        resolved_config = StarburstBIService._resolve_llm_config(llm_override, llm_config)
        plan_dict = ensure_dict(plan)
        context_dict = ensure_dict(semantic_context)
        tables = context_dict.get("tables", [])
        metrics = context_dict.get("metrics", [])
        dimensions = context_dict.get("dimensions", [])
        sample_queries = context_dict.get("sample_queries", [])
        business_rules = context_dict.get("business_rules", [])

        system_prompt = (
            "You are a Starburst SQL analyst. Generate one safe SELECT query only. "
            "Use the provided business metadata, sample queries, metric definitions, and Starburst SQL dialect. "
            "Never return explanations. Return SQL only."
        )
        user_prompt = "\n\n".join(
            [
                f"Question:\n{coerce_text(question)}",
                f"Plan JSON:\n{ensure_json_text(plan_dict)}",
                f"Catalog: {catalog or settings.sb_catalog}",
                f"Schema: {schema or settings.sb_schema}",
                f"Semantic summary:\n{coerce_text(semantic_summary)}",
                f"Tables:\n{ensure_json_text(tables)}",
                f"Metrics:\n{ensure_json_text(metrics)}",
                f"Dimensions:\n{ensure_json_text(dimensions)}",
                f"Sample queries:\n{ensure_json_text(sample_queries)}",
                f"Business rules:\n{ensure_json_text(business_rules)}",
                "Constraints:\n- SELECT only\n- Prefer fully qualified table names\n- Add ORDER BY when ranking\n- Avoid SELECT *\n- Use LIMIT only if the question does not require a full aggregation",
            ]
        )
        response = LLMService.invoke(resolved_config, system_prompt, user_prompt)
        sql = response.strip()
        if sql.lower().startswith("```sql"):
            sql = sql[6:].strip()
        sql = sql.removeprefix("```").removesuffix("```").strip()
        return {
            "sql": sql,
            "raw_response": response,
            "catalog": catalog or settings.sb_catalog,
            "schema": schema or settings.sb_schema,
        }

    @staticmethod
    def validate_sql(
        sql: str,
        catalog: Optional[str] = None,
        schema: Optional[str] = None,
        limit: Optional[int] = None,
        allowed_catalogs: Optional[str] = None,
        allowed_schemas: Optional[str] = None,
        denied_columns: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        resolved_sql = expand_sql_placeholders(
            sql,
            catalog=catalog or settings.sb_catalog,
            schema=schema or settings.sb_schema,
        )
        return validate_sql(
            sql=resolved_sql,
            catalog=catalog,
            schema=schema,
            limit=limit,
            allowed_catalogs=allowed_catalogs,
            allowed_schemas=allowed_schemas,
            denied_columns=denied_columns,
            **kwargs,
        )

    @staticmethod
    def execute_sql(
        sql: str,
        catalog: Optional[str] = None,
        schema: Optional[str] = None,
        limit: Optional[int] = None,
        validate_first: bool = True,
        **connection_kwargs: Any,
    ) -> Dict[str, Any]:
        start_time = time.time()
        resolved_sql = expand_sql_placeholders(
            sql,
            catalog=catalog or settings.sb_catalog,
            schema=schema or settings.sb_schema,
        )
        validation = validate_sql(
            sql=resolved_sql,
            catalog=catalog,
            schema=schema,
            limit=limit,
            allowed_catalogs=connection_kwargs.get("allowed_catalogs"),
            allowed_schemas=connection_kwargs.get("allowed_schemas"),
            denied_columns=connection_kwargs.get("denied_columns"),
        )
        if validate_first and not validation.get("can_execute"):
            raise ValueError("; ".join(validation.get("errors", [])) or "SQL validation failed")

        client = get_starburst_client(catalog=catalog, schema=schema, **connection_kwargs)
        result = client.query(validation.get("safe_sql") or validation.get("sql") or sql)
        result["validation"] = validation
        result["preview"] = truncate_rows(result.get("rows", []), max_rows=10)
        result["execution_time"] = time.time() - start_time
        return result

    @staticmethod
    def profile_results(
        rows: Optional[Any] = None,
        columns: Optional[Any] = None,
        question: Optional[str] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        result = profile_result_set(rows=ensure_list(rows), columns=ensure_list(columns), question=question)
        recommendation = result.get("recommendation", {})
        return {
            **result,
            "should_visualize": recommendation.get("should_visualize", False),
            "chart_type": recommendation.get("chart_type"),
            "x": recommendation.get("x"),
            "y": recommendation.get("y"),
        }

    @staticmethod
    def recommend_visualization(
        profile: Optional[Any] = None,
        question: Optional[str] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        profile_dict = ensure_dict(profile)
        return recommend_visualization(profile_dict, question=question)

    @staticmethod
    def create_visualization(
        data: Optional[Any] = None,
        recommendation: Optional[Any] = None,
        chart_type: Optional[str] = None,
        x: Optional[str] = None,
        y: Optional[str] = None,
        color: Optional[str] = None,
        title: Optional[str] = None,
        output_format: str = "html",
        output_path: Optional[str] = None,
        analysis_id: Optional[str] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        result = create_visualization(
            data=data,
            recommendation=recommendation,
            chart_type=chart_type,
            x=x,
            y=y,
            color=color,
            title=title,
            output_format=output_format,
            output_path=output_path,
            analysis_id=analysis_id,
        )
        if result.get("error"):
            raise ValueError(result["error"])
        return result

    @staticmethod
    def save_analysis(
        question: str,
        sql: Optional[str] = None,
        result: Optional[Any] = None,
        validation: Optional[Any] = None,
        profile: Optional[Any] = None,
        visualization: Optional[Any] = None,
        plan: Optional[Any] = None,
        semantic_context: Optional[Any] = None,
        answer: Optional[str] = None,
        analysis_id: Optional[str] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        store = AnalysisStore()
        payload = {
            "question": question,
            "sql": sql,
            "result": result,
            "validation": validation,
            "profile": profile,
            "visualization": visualization,
            "plan": plan,
            "semantic_context": semantic_context,
            "answer": answer,
        }
        return store.save(payload=payload, analysis_id=analysis_id)

    @staticmethod
    def load_analysis(analysis_id: str, **_: Any) -> Dict[str, Any]:
        store = AnalysisStore()
        return store.load(analysis_id)

    @staticmethod
    def list_catalogs(**connection_kwargs: Any) -> Dict[str, Any]:
        client = get_starburst_client(**connection_kwargs)
        return client.list_catalogs()

    @staticmethod
    def list_schemas(catalog: Optional[str] = None, **connection_kwargs: Any) -> Dict[str, Any]:
        client = get_starburst_client(catalog=catalog, **connection_kwargs)
        return client.list_schemas(catalog=catalog)

    @staticmethod
    def list_tables(catalog: Optional[str] = None, schema: Optional[str] = None, **connection_kwargs: Any) -> Dict[str, Any]:
        client = get_starburst_client(catalog=catalog, schema=schema, **connection_kwargs)
        return client.list_tables(catalog=catalog, schema=schema)

    @staticmethod
    def describe_table(table_name: str, catalog: Optional[str] = None, schema: Optional[str] = None, **connection_kwargs: Any) -> Dict[str, Any]:
        client = get_starburst_client(catalog=catalog, schema=schema, **connection_kwargs)
        return client.describe_table(table_name=table_name, catalog=catalog, schema=schema)

    @staticmethod
    def format_answer(
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
        **_: Any,
    ) -> Dict[str, Any]:
        resolved_config = StarburstBIService._resolve_llm_config(llm_override, llm_config)
        plan_dict = ensure_dict(plan)
        validation_dict = ensure_dict(validation)
        profile_dict = ensure_dict(profile)
        visualization_dict = ensure_dict(visualization)
        analysis_dict = ensure_dict(analysis_record)
        preview = truncate_rows(rows or [], max_rows=10)

        system_prompt = (
            "You are an AI BI assistant. Produce a concise markdown answer with sections: Summary, Visualization, SQL, Assumptions. "
            "Be explicit about filters, grain, and caveats."
        )
        user_prompt = "\n\n".join(
            [
                f"Question:\n{coerce_text(question)}",
                f"Plan:\n{ensure_json_text(plan_dict)}",
                f"Semantic summary:\n{coerce_text(semantic_summary)}",
                f"SQL:\n{coerce_text(sql)}",
                f"Validation:\n{ensure_json_text(validation_dict)}",
                f"Rows preview:\n{ensure_json_text(preview)}",
                f"Profile:\n{ensure_json_text(profile_dict)}",
                f"Visualization:\n{ensure_json_text(visualization_dict)}",
                f"Saved analysis:\n{ensure_json_text(analysis_dict)}",
            ]
        )
        response = LLMService.invoke(resolved_config, system_prompt, user_prompt)
        return {
            "answer": response,
            "preview": preview,
            "row_count": len(rows or []),
        }
