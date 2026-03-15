from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.sb.utils import parse_csv_list


DISALLOWED_SQL_PATTERNS = [
    r"\binsert\b",
    r"\bupdate\b",
    r"\bdelete\b",
    r"\bmerge\b",
    r"\bdrop\b",
    r"\balter\b",
    r"\bcreate\b",
    r"\btruncate\b",
    r"\bgrant\b",
    r"\brevoke\b",
    r"\bcall\b",
]


def normalize_sql(sql: str) -> str:
    text = (sql or "").strip()
    text = re.sub(r"^```sql", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^```", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return text.rstrip(";").strip()


def _split_statements(sql: str) -> List[str]:
    return [part.strip() for part in sql.split(";") if part.strip()]


def _qualified_references(sql: str) -> List[Tuple[str, str, str]]:
    pattern = r"\b([A-Za-z_][\w]*)\.([A-Za-z_][\w]*)\.([A-Za-z_][\w]*)\b"
    return re.findall(pattern, sql)


def validate_sql(
    sql: str,
    catalog: Optional[str] = None,
    schema: Optional[str] = None,
    limit: Optional[int] = None,
    allowed_catalogs: Optional[str] = None,
    allowed_schemas: Optional[str] = None,
    denied_columns: Optional[str] = None,
    enforce_limit: bool = True,
    **_: Any,
) -> Dict[str, Any]:
    normalized = normalize_sql(sql)
    errors: List[str] = []
    warnings: List[str] = []

    if not normalized:
        errors.append("SQL is required")

    statements = _split_statements(normalized)
    if len(statements) > 1:
        errors.append("Only a single SQL statement is allowed")

    if normalized and not re.match(r"^(select|with)\b", normalized, flags=re.IGNORECASE):
        errors.append("Only SELECT queries are allowed")

    for pattern in DISALLOWED_SQL_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            errors.append(f"Disallowed SQL keyword detected: {pattern.replace('\\b', '').strip('r')}")

    resolved_allowed_catalogs = parse_csv_list(allowed_catalogs if allowed_catalogs is not None else settings.sb_allowed_catalogs)
    resolved_allowed_schemas = parse_csv_list(allowed_schemas if allowed_schemas is not None else settings.sb_allowed_schemas)
    resolved_denied_columns = parse_csv_list(denied_columns if denied_columns is not None else settings.sb_denied_columns)

    if catalog and resolved_allowed_catalogs and catalog not in resolved_allowed_catalogs:
        errors.append(f"Catalog '{catalog}' is not allowed")
    if schema and resolved_allowed_schemas and schema not in resolved_allowed_schemas:
        errors.append(f"Schema '{schema}' is not allowed")

    for ref_catalog, ref_schema, _ in _qualified_references(normalized):
        if resolved_allowed_catalogs and ref_catalog not in resolved_allowed_catalogs:
            errors.append(f"Catalog '{ref_catalog}' is not allowed")
        if resolved_allowed_schemas and ref_schema not in resolved_allowed_schemas:
            errors.append(f"Schema '{ref_schema}' is not allowed")

    for column_name in resolved_denied_columns:
        if re.search(rf"\b{re.escape(column_name)}\b", normalized, flags=re.IGNORECASE):
            errors.append(f"Column '{column_name}' is denylisted")

    applied_limit = None
    safe_sql = normalized
    resolved_limit = limit or settings.sb_default_limit
    if enforce_limit and normalized and not re.search(r"\blimit\s+\d+\b", normalized, flags=re.IGNORECASE):
        safe_sql = f"{normalized}\nLIMIT {resolved_limit}"
        applied_limit = resolved_limit
        warnings.append(f"Applied LIMIT {resolved_limit} for safety")

    return {
        "sql": normalized,
        "safe_sql": safe_sql,
        "catalog": catalog,
        "schema": schema,
        "can_execute": not errors,
        "errors": errors,
        "warnings": warnings,
        "applied_limit": applied_limit,
        "allowed_catalogs": resolved_allowed_catalogs,
        "allowed_schemas": resolved_allowed_schemas,
        "denied_columns": resolved_denied_columns,
    }
