from __future__ import annotations

import re
from typing import Any, Dict, Optional

from app.config import settings
from app.sb.utils import ensure_dict
from app.services.mcp_client_service import MCPClientService


def _slugify(value: str, default: str = "sb_dashboard") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return slug or default


def _extract_payload(response: Dict[str, Any]) -> Dict[str, Any]:
    payload = response.get("payload")
    if isinstance(payload, dict):
        return payload
    return {"payload": payload, "content": response.get("content", [])}


class SupersetMCPService:
    @staticmethod
    def _server_url() -> str:
        if not settings.superset_mcp_url:
            raise ValueError("SUPERSET_MCP_URL is not configured")
        return settings.superset_mcp_url

    @staticmethod
    async def health() -> Dict[str, Any]:
        response = await MCPClientService.call_tool(
            server_url=SupersetMCPService._server_url(),
            tool_name="superset_health",
        )
        return _extract_payload(response)

    @staticmethod
    async def publish_dashboard(
        question: str,
        sql: str,
        recommendation: Optional[Any] = None,
        profile: Optional[Any] = None,
        title: Optional[str] = None,
        chart_title: Optional[str] = None,
        chart_type: Optional[str] = None,
        x: Optional[str] = None,
        y: Optional[str] = None,
        database_name: Optional[str] = None,
        schema_name: Optional[str] = None,
        row_limit: int = 1000,
        guest_username: Optional[str] = None,
    ) -> Dict[str, Any]:
        recommendation_dict = ensure_dict(recommendation)
        profile_dict = ensure_dict(profile)
        resolved_title = title or question or "Starburst dashboard"
        resolved_chart_type = chart_type or recommendation_dict.get("chart_type") or profile_dict.get("chart_type") or "table"
        resolved_x = x or recommendation_dict.get("x") or profile_dict.get("x")
        resolved_y = y or recommendation_dict.get("y") or profile_dict.get("y")
        resolved_chart_title = chart_title or resolved_title
        resolved_schema_name = schema_name or settings.sb_schema
        resolved_database_name = database_name or settings.superset_database_name
        resolved_guest_username = guest_username or settings.superset_mcp_guest_username
        response = await MCPClientService.call_tool(
            server_url=SupersetMCPService._server_url(),
            tool_name="provision_dashboard_from_sql",
            arguments={
                "dashboard_title": resolved_title,
                "sql": sql,
                "database_name": resolved_database_name,
                "schema_name": resolved_schema_name,
                "chart_title": resolved_chart_title,
                "dataset_name": f"{_slugify(resolved_title)}_dataset",
                "chart_type": resolved_chart_type,
                "x_axis": resolved_x,
                "y_axis": resolved_y,
                "row_limit": row_limit,
                "publish": True,
                "create_guest_token": True,
                "guest_username": resolved_guest_username,
            },
        )
        payload = _extract_payload(response)
        dashboard = ensure_dict(payload.get("dashboard"))
        chart = ensure_dict(payload.get("chart"))
        dataset = ensure_dict(payload.get("dataset"))
        return {
            **payload,
            "dashboard_id": dashboard.get("id"),
            "chart_id": chart.get("id"),
            "dataset_id": dataset.get("id"),
            "dashboard_url": payload.get("dashboard_url") or payload.get("standalone_url"),
            "standalone_url": payload.get("standalone_url") or payload.get("dashboard_url"),
            "guest_token": payload.get("guest_token"),
            "question": question,
            "sql": sql,
            "chart_type": resolved_chart_type,
            "x": resolved_x,
            "y": resolved_y,
            "database_name": resolved_database_name,
            "schema_name": resolved_schema_name,
        }

    @staticmethod
    async def serve_dashboard(
        dashboard_id: int,
        guest_username: Optional[str] = None,
        standalone: bool = True,
    ) -> Dict[str, Any]:
        resolved_guest_username = guest_username or settings.superset_mcp_guest_username
        response = await MCPClientService.call_tool(
            server_url=SupersetMCPService._server_url(),
            tool_name="serve_dashboard",
            arguments={
                "dashboard_id": dashboard_id,
                "guest_username": resolved_guest_username,
                "standalone": standalone,
            },
        )
        payload = _extract_payload(response)
        return {
            **payload,
            "dashboard_id": dashboard_id,
            "guest_username": resolved_guest_username,
        }
