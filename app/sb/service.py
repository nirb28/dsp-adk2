from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional

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
    def _find_text_date_columns(context: Dict[str, Any]) -> List[Dict[str, str]]:
        matches: List[Dict[str, str]] = []
        for table in ensure_list(context.get("tables")):
            if not isinstance(table, dict):
                continue
            table_name = coerce_text(table.get("name")).strip()
            for column in ensure_list(table.get("columns")):
                if not isinstance(column, dict):
                    continue
                column_name = coerce_text(column.get("name")).strip()
                column_type = coerce_text(column.get("type")).strip().lower()
                description = coerce_text(column.get("description")).strip().lower()
                if not column_name:
                    continue
                if column_type.startswith("varchar") and "date" in column_name.lower():
                    matches.append({
                        "table": table_name,
                        "column": column_name,
                        "type": column_type,
                        "description": coerce_text(column.get("description")).strip(),
                    })
                    continue
                if column_type.startswith("varchar") and re.search(r"\bdate\b", description):
                    matches.append({
                        "table": table_name,
                        "column": column_name,
                        "type": column_type,
                        "description": coerce_text(column.get("description")).strip(),
                    })
        deduped: List[Dict[str, str]] = []
        seen = set()
        for item in matches:
            key = (item.get("table"), item.get("column"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    @staticmethod
    def _looks_like_trino_text_date_mismatch(error: Exception) -> bool:
        message = coerce_text(error).lower()
        return "type_mismatch" in message and "varchar" in message and "date" in message

    @staticmethod
    def _looks_like_trino_alias_resolution_error(error: Exception) -> bool:
        message = coerce_text(error).lower()
        return "column_not_found" in message and "cannot be resolved" in message

    @staticmethod
    def _split_sql_csv(segment: str) -> List[str]:
        parts: List[str] = []
        current: List[str] = []
        depth = 0
        in_single_quote = False
        for char in segment:
            if char == "'":
                in_single_quote = not in_single_quote
            elif not in_single_quote:
                if char == "(":
                    depth += 1
                elif char == ")" and depth > 0:
                    depth -= 1
                elif char == "," and depth == 0:
                    item = "".join(current).strip()
                    if item:
                        parts.append(item)
                    current = []
                    continue
            current.append(char)
        tail = "".join(current).strip()
        if tail:
            parts.append(tail)
        return parts

    @staticmethod
    def _select_alias_positions(sql: str) -> Dict[str, int]:
        match = re.search(r"^\s*select\s+(.*?)\s+from\b", sql, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return {}
        aliases: Dict[str, int] = {}
        for index, item in enumerate(StarburstBIService._split_sql_csv(match.group(1)), start=1):
            alias_match = re.search(r"\bas\s+([A-Za-z_][\w]*)\s*$", item, flags=re.IGNORECASE)
            if alias_match:
                aliases[alias_match.group(1).lower()] = index
        return aliases

    @staticmethod
    def _select_alias_expressions(sql: str) -> Dict[str, str]:
        match = re.search(r"^\s*select\s+(.*?)\s+from\b", sql, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return {}
        aliases: Dict[str, str] = {}
        for item in StarburstBIService._split_sql_csv(match.group(1)):
            alias_match = re.search(r"\bas\s+([A-Za-z_][\w]*)\s*$", item, flags=re.IGNORECASE)
            if alias_match:
                aliases[alias_match.group(1).lower()] = item[: alias_match.start()].strip()
        return aliases

    @staticmethod
    def _rewrite_group_by_aliases(sql: str) -> str:
        alias_expressions = StarburstBIService._select_alias_expressions(sql)
        if not alias_expressions:
            return sql

        def _rewrite_clause(match: re.Match[str]) -> str:
            clause = match.group(1)
            segment = match.group(2)
            rewritten_items: List[str] = []
            changed = False
            for item in StarburstBIService._split_sql_csv(segment):
                stripped = item.strip()
                order_match = re.match(r"^([A-Za-z_][\w]*)(\s+(?:ASC|DESC))?$", stripped, flags=re.IGNORECASE)
                if order_match:
                    alias = order_match.group(1).lower()
                    suffix = order_match.group(2) or ""
                    expression = alias_expressions.get(alias)
                    if expression is not None:
                        rewritten_items.append(f"{expression}{suffix}")
                        changed = True
                        continue
                rewritten_items.append(stripped)
            if not changed:
                return match.group(0)
            return f"{clause} {', '.join(rewritten_items)}"

        rewritten = re.sub(
            r"\b(GROUP\s+BY)\b\s*(.+?)(?=\bHAVING\b|\bORDER\s+BY\b|\bLIMIT\b|\bOFFSET\b|\bFETCH\b|$)",
            _rewrite_clause,
            sql,
            flags=re.IGNORECASE | re.DOTALL,
        )
        rewritten = re.sub(
            r"\b(ORDER\s+BY)\b\s*(.+?)(?=\bLIMIT\b|\bOFFSET\b|\bFETCH\b|$)",
            _rewrite_clause,
            rewritten,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return rewritten

    @staticmethod
    def _rewrite_text_date_sql(sql: str) -> str:
        rewritten = sql

        def _wrap_identifier(match: re.Match[str]) -> str:
            identifier = match.group(1)
            return f"try_cast({identifier} as date)"

        rewritten = re.sub(
            r"date_trunc\(\s*'[^']+'\s*,\s*((?:[A-Za-z_][\w]*\.)?[A-Za-z_][\w]*date)\s*\)",
            lambda match: match.group(0).replace(match.group(1), f"try_cast({match.group(1)} as date)"),
            rewritten,
            flags=re.IGNORECASE,
        )
        rewritten = re.sub(
            r"\b((?:[A-Za-z_][\w]*\.)?[A-Za-z_][\w]*date)\b\s*(<=|>=|<|>)\s*(current_date\b(?:\s*[-+]\s*interval\s*'[^']+'\s+[A-Za-z_]+)?)",
            lambda match: f"try_cast({match.group(1)} as date) {match.group(2)} {match.group(3)}",
            rewritten,
            flags=re.IGNORECASE,
        )
        rewritten = re.sub(
            r"(current_date\b(?:\s*[-+]\s*interval\s*'[^']+'\s+[A-Za-z_]+)?)\s*(<=|>=|<|>)\s*\b((?:[A-Za-z_][\w]*\.)?[A-Za-z_][\w]*date)\b",
            lambda match: f"{match.group(1)} {match.group(2)} try_cast({match.group(3)} as date)",
            rewritten,
            flags=re.IGNORECASE,
        )
        rewritten = re.sub(
            r"\b((?:[A-Za-z_][\w]*\.)?[A-Za-z_][\w]*date)\b\s+(between)\s+(date\s*'[^']+'|current_date\b(?:\s*[-+]\s*interval\s*'[^']+'\s+[A-Za-z_]+)?)\s+(and)\s+(date\s*'[^']+'|current_date\b(?:\s*[-+]\s*interval\s*'[^']+'\s+[A-Za-z_]+)?)",
            lambda match: f"try_cast({match.group(1)} as date) {match.group(2)} {match.group(3)} {match.group(4)} {match.group(5)}",
            rewritten,
            flags=re.IGNORECASE,
        )
        return rewritten

    @staticmethod
    def _format_metric_value(value: Any) -> str:
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, int):
            return f"{value:,}"
        if isinstance(value, float):
            rounded = round(value, 6)
            if rounded.is_integer():
                return f"{int(rounded):,}"
            return f"{rounded:,.6f}".rstrip("0").rstrip(".")
        return coerce_text(value)

    @staticmethod
    def _compute_authoritative_result_stats(rows: List[Dict[str, Any]], profile: Dict[str, Any]) -> Dict[str, Any]:
        numeric_columns = [column for column in profile.get("numeric_columns", []) if isinstance(column, str)]
        categorical_columns = [column for column in profile.get("categorical_columns", []) if isinstance(column, str)]
        totals: Dict[str, float] = {}
        non_null_counts: Dict[str, int] = {}
        distinct_counts: Dict[str, int] = {}

        for column in numeric_columns:
            values = [row.get(column) for row in rows]
            numeric_values = [value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
            if numeric_values:
                totals[column] = float(sum(numeric_values))
                non_null_counts[column] = len(numeric_values)

        for column in categorical_columns:
            distinct_values = {coerce_text(row.get(column)) for row in rows if row.get(column) is not None}
            if distinct_values:
                distinct_counts[column] = len(distinct_values)

        return {
            "row_count": len(rows),
            "numeric_totals": totals,
            "numeric_non_null_counts": non_null_counts,
            "categorical_distinct_counts": distinct_counts,
        }

    @staticmethod
    def _build_authoritative_summary(
        rows: List[Dict[str, Any]],
        plan: Dict[str, Any],
        profile: Dict[str, Any],
        stats: Dict[str, Any],
    ) -> str:
        row_count = stats.get("row_count", len(rows))
        summary_lines: List[str] = [f"- Returned **{StarburstBIService._format_metric_value(row_count)}** row(s) in the full result set."]

        if row_count == 0:
            return "\n".join(summary_lines)

        metric_name = coerce_text(plan.get("metric")).strip()
        numeric_totals = stats.get("numeric_totals", {})
        numeric_non_null_counts = stats.get("numeric_non_null_counts", {})
        categorical_distinct_counts = stats.get("categorical_distinct_counts", {})

        if len(rows) == 1:
            row = rows[0]
            scalar_values = []
            for key, value in row.items():
                if value is None or isinstance(value, (dict, list, tuple)):
                    continue
                scalar_values.append(f"`{key}` = **{StarburstBIService._format_metric_value(value)}**")
            if scalar_values:
                summary_lines.append(f"- Exact value(s) from the full result: {', '.join(scalar_values[:6])}.")

        if metric_name and metric_name in numeric_totals:
            summary_lines.append(
                f"- Authoritative total for **{metric_name}** across all returned rows: **{StarburstBIService._format_metric_value(numeric_totals[metric_name])}**."
            )

        other_numeric_summaries = []
        for column, total in numeric_totals.items():
            if metric_name and column == metric_name:
                continue
            count_value = numeric_non_null_counts.get(column, row_count)
            other_numeric_summaries.append(
                f"`{column}` total = **{StarburstBIService._format_metric_value(total)}** over {StarburstBIService._format_metric_value(count_value)} numeric row(s)"
            )
        if other_numeric_summaries:
            summary_lines.append(f"- Full-result numeric aggregates: {'; '.join(other_numeric_summaries[:4])}.")

        distinct_summaries = [
            f"`{column}` distinct values = **{StarburstBIService._format_metric_value(count)}**"
            for column, count in categorical_distinct_counts.items()
        ]
        if distinct_summaries:
            summary_lines.append(f"- Full-result category counts: {'; '.join(distinct_summaries[:3])}.")

        return "\n".join(summary_lines)

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
        text_date_columns = StarburstBIService._find_text_date_columns(context_dict)
        text_date_guidance = [
            f"{item.get('table')}.{item.get('column')} ({item.get('type')}): {item.get('description')}"
            for item in text_date_columns
        ]

        system_prompt = (
            "You are a Starburst SQL analyst. Generate one safe SELECT query only. "
            "Use the provided business metadata, sample queries, metric definitions, and Starburst SQL dialect. "
            "If a date-like column is stored as varchar/text, use try_cast(column as date) before any date comparison, date_trunc, ordering by date semantics, or interval arithmetic. "
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
                f"Text date columns requiring try_cast(... as date) for date logic:\n{ensure_json_text(text_date_guidance)}",
                "Constraints:\n- SELECT only\n- Prefer fully qualified table names\n- Add ORDER BY when ranking\n- Avoid SELECT *\n- Use LIMIT only if the question does not require a full aggregation\n- Never compare varchar columns directly to DATE/current_date values\n- For text-backed dates, use try_cast(column as date) in WHERE, JOIN, date_trunc, and ORDER BY date expressions",
            ]
        )
        response = LLMService.invoke(resolved_config, system_prompt, user_prompt)
        sql = response.strip()
        if sql.lower().startswith("```sql"):
            sql = sql[6:].strip()
        sql = sql.removeprefix("```").removesuffix("```").strip()
        fallback = {"sql": sql}
        return {
            **fallback,
            **StarburstBIService._parse_json_response(response, fallback),
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
        sql_to_execute = validation.get("safe_sql") or validation.get("sql") or sql
        original_sql = sql_to_execute
        rewrite_notes: List[str] = []
        result: Dict[str, Any]
        for _ in range(3):
            try:
                result = client.query(sql_to_execute)
                break
            except Exception as exc:
                rewritten_sql = ""
                rewrite_note = ""
                if StarburstBIService._looks_like_trino_text_date_mismatch(exc):
                    rewritten_sql = StarburstBIService._rewrite_text_date_sql(sql_to_execute)
                    rewrite_note = "Automatically rewrote text-backed date predicates with try_cast(... as date) after Trino reported a varchar/date mismatch."
                elif StarburstBIService._looks_like_trino_alias_resolution_error(exc):
                    rewritten_sql = StarburstBIService._rewrite_group_by_aliases(sql_to_execute)
                    rewrite_note = "Automatically rewrote SELECT alias references in GROUP BY/ORDER BY to ordinal positions after Trino could not resolve the alias name."
                if not rewritten_sql or rewritten_sql == sql_to_execute:
                    raise
                rewritten_validation = validate_sql(
                    sql=rewritten_sql,
                    catalog=catalog,
                    schema=schema,
                    limit=limit,
                    allowed_catalogs=connection_kwargs.get("allowed_catalogs"),
                    allowed_schemas=connection_kwargs.get("allowed_schemas"),
                    denied_columns=connection_kwargs.get("denied_columns"),
                )
                next_sql = rewritten_validation.get("safe_sql") or rewritten_validation.get("sql") or rewritten_sql
                if next_sql == sql_to_execute:
                    raise
                sql_to_execute = next_sql
                validation = rewritten_validation
                rewrite_notes.append(rewrite_note)
        else:
            raise RuntimeError("Starburst SQL execution retries were exhausted")

        if rewrite_notes:
            validation = {
                **validation,
                "warnings": [*validation.get("warnings", []), *rewrite_notes],
                "original_sql": original_sql,
            }
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
        rows_list = ensure_list(rows)
        plan_dict = ensure_dict(plan)
        validation_dict = ensure_dict(validation)
        profile_dict = ensure_dict(profile)
        visualization_dict = ensure_dict(visualization)
        analysis_dict = ensure_dict(analysis_record)
        preview = truncate_rows(rows_list, max_rows=10)
        full_result_stats = StarburstBIService._compute_authoritative_result_stats(rows_list, profile_dict)
        authoritative_summary = StarburstBIService._build_authoritative_summary(
            rows=rows_list,
            plan=plan_dict,
            profile=profile_dict,
            stats=full_result_stats,
        )

        system_prompt = (
            "You are an AI BI assistant. Produce a concise markdown answer with sections: Visualization, SQL, Assumptions. "
            "Do not compute or restate totals, counts, or numeric aggregates from the preview rows. "
            "The Summary section has already been computed from the full result set and must not be contradicted. "
            "Be explicit about filters, grain, and caveats."
        )
        user_prompt = "\n\n".join(
            [
                f"Question:\n{coerce_text(question)}",
                f"Plan:\n{ensure_json_text(plan_dict)}",
                f"Semantic summary:\n{coerce_text(semantic_summary)}",
                f"SQL:\n{coerce_text(sql)}",
                f"Validation:\n{ensure_json_text(validation_dict)}",
                f"Authoritative full-result statistics:\n{ensure_json_text(full_result_stats)}",
                f"Authoritative Summary section to preserve verbatim:\n{authoritative_summary}",
                f"Rows preview:\n{ensure_json_text(preview)}",
                f"Profile:\n{ensure_json_text(profile_dict)}",
                f"Visualization:\n{ensure_json_text(visualization_dict)}",
                f"Saved analysis:\n{ensure_json_text(analysis_dict)}",
            ]
        )
        response = LLMService.invoke(resolved_config, system_prompt, user_prompt).strip()
        answer_sections = [f"## Summary\n{authoritative_summary}"]
        if response:
            answer_sections.append(response)
        return {
            "answer": "\n\n".join(answer_sections),
            "preview": preview,
            "row_count": len(rows_list),
            "full_result_stats": full_result_stats,
        }
