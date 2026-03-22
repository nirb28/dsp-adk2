from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models import GraphExecutionNormalizedResponse, GraphExecutionResponse


class GraphResponseNormalizer:
    @staticmethod
    def _as_dict(value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _as_list(value: Any) -> List[Any]:
        return value if isinstance(value, list) else []

    @staticmethod
    def _find_step_output(
        steps: List[Dict[str, Any]],
        *,
        node: Optional[str] = None,
        tool: Optional[str] = None,
    ) -> Dict[str, Any]:
        for step in reversed(steps):
            if node and step.get("node") != node:
                continue
            if tool and step.get("tool") != tool:
                continue
            return GraphResponseNormalizer._as_dict(step.get("output"))
        return {}

    @staticmethod
    def _first_populated_dict(*values: Any) -> Dict[str, Any]:
        for value in values:
            if isinstance(value, dict) and value:
                return value
        return {}

    @staticmethod
    def _build_artifact_url(path_value: Any) -> Optional[str]:
        if not isinstance(path_value, str) or not path_value.strip():
            return None
        normalized = path_value.replace("\\", "/").lower()
        name = Path(path_value).name
        if "/analyses/" in normalized or normalized.endswith(".json"):
            return f"/execute/artifacts/analysis/{name}"
        if "/visualizations/" in normalized or normalized.endswith((".html", ".png", ".jpg", ".jpeg", ".svg", ".webp")):
            return f"/execute/artifacts/visualization/{name}"
        return None

    @staticmethod
    def normalize(response: GraphExecutionResponse) -> GraphExecutionNormalizedResponse:
        output = GraphResponseNormalizer._as_dict(response.output)
        steps = GraphResponseNormalizer._as_list(response.steps)

        generated_sql = GraphResponseNormalizer._find_step_output(steps, node="generate_sql", tool="sb_text_to_sql")
        validated_sql = GraphResponseNormalizer._find_step_output(steps, node="validate_sql", tool="sb_validate_sql")
        executed_sql = GraphResponseNormalizer._find_step_output(steps, node="execute_sql", tool="sb_execute_sql")
        profile = GraphResponseNormalizer._find_step_output(steps, node="profile_results", tool="sb_profile_results")
        recommendation = GraphResponseNormalizer._find_step_output(steps, node="recommend_visualization", tool="sb_recommend_visualization")
        visualization = GraphResponseNormalizer._find_step_output(steps, node="create_visualization", tool="sb_create_visualization")
        formatted_answer = GraphResponseNormalizer._find_step_output(steps, node="format_answer", tool="sb_format_answer")
        saved_analysis = GraphResponseNormalizer._first_populated_dict(
            GraphResponseNormalizer._find_step_output(steps, node="save_final_analysis", tool="sb_save_analysis"),
            GraphResponseNormalizer._find_step_output(steps, node="save_analysis", tool="sb_save_analysis"),
        )

        result_rows = GraphResponseNormalizer._as_list(executed_sql.get("rows"))
        result_columns = GraphResponseNormalizer._as_list(executed_sql.get("columns"))
        result_preview = GraphResponseNormalizer._as_list(
            executed_sql.get("preview") or formatted_answer.get("preview")
        )
        validation = GraphResponseNormalizer._first_populated_dict(
            GraphResponseNormalizer._as_dict(executed_sql.get("validation")),
            validated_sql,
        )

        normalized: Dict[str, Any] = {
            "request": {
                "question": output.get("user_question"),
                "conversation_history": output.get("conversation_history"),
                "metadata_file": output.get("metadata_file"),
                "include_live_schema": output.get("include_live_schema"),
                "catalog": output.get("catalog"),
                "schema": output.get("schema"),
                "limit": output.get("limit"),
                "output_format": output.get("output_format"),
            },
            "summary": {
                "markdown": formatted_answer.get("answer") or "",
                "preview": result_preview,
                "row_count": executed_sql.get("row_count", len(result_rows)),
            },
            "results": {
                "columns": result_columns,
                "rows": result_rows,
                "row_count": executed_sql.get("row_count", len(result_rows)),
                "preview": result_preview,
            },
            "sql": {
                "generated": generated_sql.get("sql"),
                "raw_generated": generated_sql.get("raw_response"),
                "validated": validation.get("sql"),
                "safe": validation.get("safe_sql"),
                "catalog": validation.get("catalog") or executed_sql.get("catalog"),
                "schema": validation.get("schema") or executed_sql.get("schema"),
                "can_execute": validation.get("can_execute"),
                "warnings": validation.get("warnings", []),
                "errors": validation.get("errors", []),
            },
            "visualization": {
                "available": bool(visualization),
                "recommended": recommendation.get("should_visualize", profile.get("should_visualize", False)),
                "chart_type": visualization.get("chart_type") or recommendation.get("chart_type") or profile.get("chart_type"),
                "reason": recommendation.get("reason") or GraphResponseNormalizer._as_dict(profile.get("recommendation")).get("reason"),
                "artifact": visualization,
                "artifact_url": GraphResponseNormalizer._build_artifact_url(visualization.get("output_path")),
                "recommendation": recommendation,
                "profile": profile,
            },
            "analysis": {
                "analysis_id": saved_analysis.get("analysis_id"),
                "output_path": saved_analysis.get("output_path"),
                "artifact_url": GraphResponseNormalizer._build_artifact_url(saved_analysis.get("output_path")),
                "saved": bool(saved_analysis),
            },
            "semantic": {
                "metadata_file": output.get("metadata_file"),
                "semantic_summary": output.get("semantic_summary"),
                "matched_assets": output.get("matched_assets", []),
                "live_schema": output.get("live_schema", {}),
            },
            "plan": output.get("plan", {}),
            "diagnostics": {
                "graph_id": response.graph_id,
                "execution_time": response.execution_time,
                "step_count": len(steps),
                "success": response.success,
                "error": response.error,
                "host": executed_sql.get("host"),
                "statement_url": executed_sql.get("statement_url"),
            },
            "trace": {
                "steps": steps,
            },
        }

        return GraphExecutionNormalizedResponse(
            graph_id=response.graph_id,
            success=response.success,
            normalized=normalized,
            raw=response,
            error=response.error,
            execution_time=response.execution_time,
        )
