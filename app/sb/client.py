from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
import trino
from trino.auth import BasicAuthentication, JWTAuthentication

from app.config import settings
from app.sb.utils import json_safe, parse_csv_list


@dataclass
class StarburstConnectionConfig:
    host: str
    port: int
    http_scheme: str
    user: str
    password: Optional[str]
    access_token: Optional[str]
    catalog: Optional[str]
    schema: Optional[str]
    source: str
    allowed_catalogs: List[str]
    allowed_schemas: List[str]
    denied_columns: List[str]

    @staticmethod
    def _normalize_host(host: Optional[str]) -> str:
        raw = host or settings.sb_host or ""
        raw = raw.strip()
        if not raw:
            raise ValueError("Starburst host is required. Set SB_HOST or pass host.")
        if "://" in raw:
            parsed = urlparse(raw)
            return parsed.netloc or parsed.path
        return raw.rstrip("/")

    @classmethod
    def from_inputs(
        cls,
        host: Optional[str] = None,
        port: Optional[int] = None,
        http_scheme: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        access_token: Optional[str] = None,
        catalog: Optional[str] = None,
        schema: Optional[str] = None,
        source: Optional[str] = None,
        allowed_catalogs: Optional[str] = None,
        allowed_schemas: Optional[str] = None,
        denied_columns: Optional[str] = None,
    ) -> "StarburstConnectionConfig":
        resolved_host = cls._normalize_host(host)
        resolved_user = user or settings.sb_user or ""
        if not resolved_user:
            raise ValueError("Starburst user is required. Set SB_USER or pass user.")

        return cls(
            host=resolved_host,
            port=port or settings.sb_port,
            http_scheme=(http_scheme or settings.sb_http_scheme or "https").lower(),
            user=resolved_user,
            password=password if password is not None else settings.sb_password,
            access_token=access_token if access_token is not None else settings.sb_access_token,
            catalog=catalog if catalog is not None else settings.sb_catalog,
            schema=schema if schema is not None else settings.sb_schema,
            source=source or settings.sb_source,
            allowed_catalogs=parse_csv_list(allowed_catalogs if allowed_catalogs is not None else settings.sb_allowed_catalogs),
            allowed_schemas=parse_csv_list(allowed_schemas if allowed_schemas is not None else settings.sb_allowed_schemas),
            denied_columns=parse_csv_list(denied_columns if denied_columns is not None else settings.sb_denied_columns),
        )


class StarburstClient:
    def __init__(self, config: StarburstConnectionConfig) -> None:
        self.config = config

    def _statement_url(self) -> str:
        return f"{self.config.http_scheme}://{self.config.host}:{self.config.port}/v1/statement"

    def _build_auth(self):
        if self.config.access_token:
            return JWTAuthentication(self.config.access_token)
        if self.config.password:
            return BasicAuthentication(self.config.user, self.config.password)
        return None

    def get_connection(self):
        return trino.dbapi.connect(
            host=self.config.host,
            port=self.config.port,
            user=self.config.user,
            auth=self._build_auth(),
            http_scheme=self.config.http_scheme,
            catalog=self.config.catalog,
            schema=self.config.schema,
            source=self.config.source,
            verify=settings.ssl_verify,
        )

    def query(self, sql: str) -> Dict[str, Any]:
        connection = self.get_connection()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(sql)
            except requests.HTTPError as exc:
                response = getattr(exc, "response", None)
                status_code = getattr(response, "status_code", None)
                if status_code == 405:
                    raise ValueError(
                        "Starburst returned HTTP 405 for /v1/statement. SB_HOST appears to point to the Galaxy web UI instead of a Trino-compatible query endpoint. Configure SB_HOST to the SQL endpoint hostname provided by Starburst, not the browser URL."
                    ) from exc
                raise
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            data = [dict(zip(columns, row)) for row in rows]
        finally:
            close_fn = getattr(connection, "close", None)
            if callable(close_fn):
                close_fn()
        return {
            "sql": sql,
            "columns": columns,
            "rows": json_safe(data),
            "row_count": len(data),
            "catalog": self.config.catalog,
            "schema": self.config.schema,
            "host": self.config.host,
            "statement_url": self._statement_url(),
        }

    def list_catalogs(self) -> Dict[str, Any]:
        result = self.query("SHOW CATALOGS")
        catalogs = []
        key = result["columns"][0] if result["columns"] else "Catalog"
        for row in result["rows"]:
            value = row.get(key)
            if value is not None:
                catalogs.append(value)
        result["catalogs"] = catalogs
        return result

    def list_schemas(self, catalog: Optional[str] = None) -> Dict[str, Any]:
        selected_catalog = catalog or self.config.catalog
        if not selected_catalog:
            raise ValueError("catalog is required to list schemas")
        result = self.query(f"SHOW SCHEMAS FROM {selected_catalog}")
        schemas = []
        key = result["columns"][0] if result["columns"] else "Schema"
        for row in result["rows"]:
            value = row.get(key)
            if value is not None:
                schemas.append(value)
        result["catalog"] = selected_catalog
        result["schemas"] = schemas
        return result

    def list_tables(self, catalog: Optional[str] = None, schema: Optional[str] = None) -> Dict[str, Any]:
        selected_catalog = catalog or self.config.catalog
        selected_schema = schema or self.config.schema
        if not selected_catalog or not selected_schema:
            raise ValueError("catalog and schema are required to list tables")
        result = self.query(f"SHOW TABLES FROM {selected_catalog}.{selected_schema}")
        tables = []
        key = result["columns"][0] if result["columns"] else "Table"
        for row in result["rows"]:
            value = row.get(key)
            if value is not None:
                tables.append(value)
        result["catalog"] = selected_catalog
        result["schema"] = selected_schema
        result["tables"] = tables
        return result

    def describe_table(self, table_name: str, catalog: Optional[str] = None, schema: Optional[str] = None) -> Dict[str, Any]:
        selected_catalog = catalog or self.config.catalog
        selected_schema = schema or self.config.schema
        if not table_name:
            raise ValueError("table_name is required")
        if not selected_catalog or not selected_schema:
            raise ValueError("catalog and schema are required to describe a table")
        sql = f"DESCRIBE {selected_catalog}.{selected_schema}.{table_name}"
        result = self.query(sql)
        result["table_name"] = table_name
        result["catalog"] = selected_catalog
        result["schema"] = selected_schema
        return result


def get_starburst_client(**kwargs: Any) -> StarburstClient:
    config = StarburstConnectionConfig.from_inputs(**kwargs)
    return StarburstClient(config)
