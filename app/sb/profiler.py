from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from app.sb.utils import truncate_rows


NUMERIC_TYPES = (int, float)
DATE_TYPES = (datetime, date)


def _infer_type(values: List[Any]) -> str:
    non_null = [value for value in values if value is not None]
    if not non_null:
        return "unknown"
    if all(isinstance(value, bool) for value in non_null):
        return "boolean"
    if all(isinstance(value, NUMERIC_TYPES) and not isinstance(value, bool) for value in non_null):
        return "number"
    if all(isinstance(value, DATE_TYPES) for value in non_null):
        return "date"
    if all(isinstance(value, str) for value in non_null):
        lowered = [value.lower() for value in non_null[:20]]
        if all("-" in value or "/" in value or "t" in value for value in lowered):
            return "date"
        return "string"
    return "string"


def profile_result_set(
    rows: Optional[List[Dict[str, Any]]] = None,
    columns: Optional[List[str]] = None,
    question: Optional[str] = None,
    **_: Any,
) -> Dict[str, Any]:
    result_rows = rows or []
    result_columns = columns or (list(result_rows[0].keys()) if result_rows else [])
    column_profiles: List[Dict[str, Any]] = []

    for column in result_columns:
        values = [row.get(column) for row in result_rows]
        inferred_type = _infer_type(values)
        unique_values = {str(value) for value in values if value is not None}
        column_profiles.append(
            {
                "name": column,
                "inferred_type": inferred_type,
                "non_null_count": sum(value is not None for value in values),
                "unique_count": len(unique_values),
                "sample_values": [value for value in values if value is not None][:5],
            }
        )

    numeric_columns = [item["name"] for item in column_profiles if item["inferred_type"] == "number"]
    date_columns = [item["name"] for item in column_profiles if item["inferred_type"] == "date"]
    categorical_columns = [
        item["name"]
        for item in column_profiles
        if item["inferred_type"] == "string" and item["unique_count"] <= 50
    ]

    recommendation = recommend_visualization(
        {
            "row_count": len(result_rows),
            "numeric_columns": numeric_columns,
            "date_columns": date_columns,
            "categorical_columns": categorical_columns,
        },
        question=question,
    )

    return {
        "row_count": len(result_rows),
        "column_count": len(result_columns),
        "columns": column_profiles,
        "numeric_columns": numeric_columns,
        "date_columns": date_columns,
        "categorical_columns": categorical_columns,
        "preview": truncate_rows(result_rows, max_rows=10),
        "recommendation": recommendation,
    }


def recommend_visualization(profile: Dict[str, Any], question: Optional[str] = None) -> Dict[str, Any]:
    row_count = profile.get("row_count", 0)
    numeric_columns = profile.get("numeric_columns", [])
    date_columns = profile.get("date_columns", [])
    categorical_columns = profile.get("categorical_columns", [])
    question_text = (question or "").lower()

    if row_count == 0:
        return {
            "should_visualize": False,
            "chart_type": None,
            "reason": "No rows returned",
        }

    if date_columns and numeric_columns:
        return {
            "should_visualize": True,
            "chart_type": "line",
            "x": date_columns[0],
            "y": numeric_columns[0],
            "reason": "Time series data detected",
        }

    if categorical_columns and numeric_columns:
        chart_type = "pie" if len(categorical_columns) == 1 and row_count <= 8 and any(term in question_text for term in ["share", "split", "percentage", "proportion"]) else "bar"
        return {
            "should_visualize": True,
            "chart_type": chart_type,
            "x": categorical_columns[0],
            "y": numeric_columns[0],
            "reason": "Categorical breakdown with a measure detected",
        }

    if len(numeric_columns) >= 2:
        return {
            "should_visualize": True,
            "chart_type": "scatter",
            "x": numeric_columns[0],
            "y": numeric_columns[1],
            "reason": "Two numeric measures detected",
        }

    return {
        "should_visualize": False,
        "chart_type": None,
        "reason": "Tabular answer is more appropriate",
    }
