from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4


def coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    return str(value)


def ensure_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return {"value": value}
    return {"value": value}


def ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            return [item.strip() for item in value.split(",") if item.strip()]
    return [value]


def ensure_json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def parse_csv_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def expand_env_placeholders(value: str, env_map: Optional[Dict[str, Any]] = None) -> str:
    text = value or ""
    resolved_map = {key: "" if val is None else str(val) for key, val in (env_map or {}).items()}
    pattern = r"\$\{([^}]+)\}"
    result = text
    for _ in range(3):
        matches = re.findall(pattern, result)
        if not matches:
            break
        updated = result
        for match in matches:
            replacement = os.getenv(match)
            if replacement is None:
                replacement = resolved_map.get(match)
            if replacement is None:
                replacement = f"${{{match}}}"
            updated = updated.replace(f"${{{match}}}", replacement)
        if updated == result:
            break
        result = updated
    return result


def expand_sql_placeholders(sql: str, catalog: Optional[str] = None, schema: Optional[str] = None) -> str:
    env_map = {
        "SB_CATALOG": catalog,
        "SB_SCHEMA": schema,
    }
    return expand_env_placeholders(sql or "", env_map=env_map)


def tokenize(text: Any) -> List[str]:
    normalized = coerce_text(text).lower()
    return re.findall(r"[a-z0-9_]+", normalized)


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def truncate_rows(rows: List[Dict[str, Any]], max_rows: int = 10) -> List[Dict[str, Any]]:
    return [json_safe(row) for row in rows[:max_rows]]


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value or "analysis")
    normalized = normalized.strip("-").lower()
    return normalized or "analysis"


def generate_analysis_id(prefix: str = "analysis") -> str:
    return f"{slugify(prefix)}-{uuid4().hex[:8]}"
