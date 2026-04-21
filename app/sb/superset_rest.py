from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

import httpx

from app.config import settings
from app.sb.utils import ensure_dict


def _slugify(value: str, default: str = "sb_dashboard") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return slug or default


def _result_payload(payload: Any) -> Any:
    if isinstance(payload, dict) and "result" in payload:
        return payload["result"]
    return payload


def _result_id(payload: Any) -> int | None:
    if isinstance(payload, dict):
        top_level_id = payload.get("id")
        if isinstance(top_level_id, int):
            return top_level_id
        result = payload.get("result")
        if isinstance(result, dict):
            nested_id = result.get("id")
            if isinstance(nested_id, int):
                return nested_id
    return None


def _make_adhoc_metric(column: str, aggregate: str = "SUM") -> dict[str, Any]:
    label = f"{aggregate}({column})"
    return {
        "expressionType": "SQL",
        "sqlExpression": f"{aggregate}({column})",
        "label": label,
        "optionName": label,
    }


def _build_chart_payload(
    dataset_id: int,
    dataset_name: str,
    dashboard_id: int,
    chart_title: str,
    chart_type: str,
    x_axis: str | None,
    y_axis: str | None,
    row_limit: int,
) -> dict[str, Any]:
    resolved_chart_type = (chart_type or "table").lower()
    datasource = {"id": dataset_id, "type": "table"}
    viz_type = "table"
    form_data: dict[str, Any] = {
        "datasource": f"{dataset_id}__table",
        "datasource_id": dataset_id,
        "datasource_type": "table",
        "slice_id": None,
        "viz_type": "table",
        "row_limit": row_limit,
    }
    query_context: dict[str, Any] = {
        "datasource": datasource,
        "force": False,
        "queries": [
            {
                "columns": [column for column in [x_axis, y_axis] if column],
                "metrics": [],
                "orderby": [],
                "row_limit": row_limit,
                "time_range": "No filter",
            }
        ],
        "result_format": "json",
        "result_type": "full",
    }

    if resolved_chart_type in {"line", "area"} and x_axis and y_axis:
        metric = _make_adhoc_metric(y_axis)
        viz_type = "echarts_timeseries_line" if resolved_chart_type == "line" else "echarts_area"
        form_data.update(
            {
                "viz_type": viz_type,
                "granularity_sqla": x_axis,
                "adhoc_metrics": [metric],
                "metrics": [metric],
                "groupby": [],
            }
        )
        query_context["queries"][0].update(
            {
                "columns": [],
                "metrics": [metric],
                "granularity": x_axis,
                "orderby": [],
            }
        )
    elif resolved_chart_type in {"bar", "hbar"} and x_axis and y_axis:
        metric = _make_adhoc_metric(y_axis)
        viz_type = "dist_bar"
        form_data.update(
            {
                "viz_type": viz_type,
                "groupby": [x_axis],
                "adhoc_metrics": [metric],
                "metrics": [metric],
                "orientation": "horizontal" if resolved_chart_type == "hbar" else "vertical",
            }
        )
        query_context["queries"][0].update(
            {
                "columns": [x_axis],
                "metrics": [metric],
                "groupby": [x_axis],
            }
        )
    elif resolved_chart_type == "pie" and x_axis and y_axis:
        metric = _make_adhoc_metric(y_axis)
        viz_type = "pie"
        form_data.update(
            {
                "viz_type": viz_type,
                "groupby": [x_axis],
                "adhoc_metrics": [metric],
                "metric": metric,
                "metrics": [metric],
            }
        )
        query_context["queries"][0].update(
            {
                "columns": [x_axis],
                "metrics": [metric],
                "groupby": [x_axis],
            }
        )
    elif resolved_chart_type == "scatter" and x_axis and y_axis:
        viz_type = "scatter_plot"
        form_data.update(
            {
                "viz_type": viz_type,
                "x": x_axis,
                "y": y_axis,
            }
        )
        query_context["queries"][0].update(
            {
                "columns": [x_axis, y_axis],
                "metrics": [],
            }
        )

    return {
        "slice_name": chart_title,
        "description": f"Auto-generated for dashboard '{chart_title}'",
        "viz_type": viz_type,
        "datasource_id": dataset_id,
        "datasource_type": "table",
        "datasource_name": dataset_name,
        "params": json.dumps(form_data),
        "query_context": json.dumps(query_context),
        "dashboards": [dashboard_id],
    }


def _build_position_json(chart_id: int, chart_uuid: str | None, chart_title: str) -> str:
    chart_key = f"CHART-{chart_id}"
    layout = {
        "ROOT_ID": {"id": "ROOT_ID", "type": "ROOT", "children": ["GRID_ID"], "parents": []},
        "GRID_ID": {"id": "GRID_ID", "type": "GRID", "children": ["ROW-1"], "parents": ["ROOT_ID"]},
        "ROW-1": {
            "id": "ROW-1",
            "type": "ROW",
            "children": [chart_key],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        },
        chart_key: {
            "id": chart_key,
            "type": "CHART",
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID", "ROW-1"],
            "meta": {
                "chartId": chart_id,
                "uuid": chart_uuid,
                "sliceName": chart_title,
                "width": 12,
                "height": 50,
            },
        },
    }
    return json.dumps(layout)


class SupersetRESTService:
    def __init__(self) -> None:
        if not settings.superset_rest_url:
            raise ValueError("SUPERSET_REST_URL is not configured")
        if not settings.superset_api_username or not settings.superset_api_password:
            raise ValueError("SUPERSET_API_USERNAME and SUPERSET_API_PASSWORD are required for Superset REST integration")
        self._base_url = settings.superset_rest_url.rstrip("/")
        self._public_url = (settings.superset_public_url or settings.superset_rest_url).rstrip("/")
        self._access_token: Optional[str] = None

    async def _login(self, client: httpx.AsyncClient) -> str:
        response = await client.post(
            f"{self._base_url}/api/v1/security/login",
            json={
                "username": settings.superset_api_username,
                "password": settings.superset_api_password,
                "provider": "db",
                "refresh": True,
            },
        )
        response.raise_for_status()
        payload = response.json()
        access_token = payload.get("access_token")
        if not access_token:
            raise RuntimeError("Superset login succeeded but no access token was returned")
        self._access_token = access_token
        return access_token

    async def _headers(self, client: httpx.AsyncClient) -> Dict[str, str]:
        token = self._access_token or await self._login(client)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        timeout = settings.superset_api_timeout
        async with httpx.AsyncClient(timeout=timeout, verify=settings.ssl_verify) as client:
            headers = kwargs.pop("headers", {})
            merged_headers = {**await self._headers(client), **headers}
            response = await client.request(
                method,
                f"{self._base_url}{path}",
                headers=merged_headers,
                **kwargs,
            )
            if response.status_code == 401:
                await self._login(client)
                merged_headers = {**await self._headers(client), **headers}
                response = await client.request(
                    method,
                    f"{self._base_url}{path}",
                    headers=merged_headers,
                    **kwargs,
                )
            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()

    async def health(self) -> Any:
        return await self._request("GET", "/health")

    async def list_databases(self, page: int = 0, page_size: int = 1000) -> Any:
        return await self._request(
            "GET",
            "/api/v1/database/",
            params={"q": f"(page:{page},page_size:{page_size})"},
        )

    async def find_database_by_name(self, database_name: str) -> Dict[str, Any]:
        payload = await self.list_databases(page=0, page_size=1000)
        for item in _result_payload(payload) or []:
            if isinstance(item, dict) and item.get("database_name") == database_name:
                return item
        raise ValueError(f"Superset database '{database_name}' was not found")

    async def create_dataset(
        self,
        database_id: int,
        dataset_name: str,
        sql: str,
        schema_name: str | None = None,
        catalog_name: str | None = None,
    ) -> Any:
        return await self._request(
            "POST",
            "/api/v1/dataset/",
            json={
                "database": database_id,
                "catalog": catalog_name,
                "schema": schema_name,
                "table_name": dataset_name,
                "sql": sql,
            },
        )

    async def create_chart(self, payload: Dict[str, Any]) -> Any:
        return await self._request("POST", "/api/v1/chart/", json=payload)

    async def get_chart(self, chart_id: int) -> Any:
        return await self._request("GET", f"/api/v1/chart/{chart_id}")

    async def create_dashboard(self, dashboard_title: str, slug: str | None = None, published: bool = True) -> Any:
        return await self._request(
            "POST",
            "/api/v1/dashboard/",
            json={
                "dashboard_title": dashboard_title,
                "slug": slug,
                "published": published,
                "position_json": json.dumps({}),
                "json_metadata": json.dumps({}),
            },
        )

    async def update_dashboard_layout(self, dashboard_id: int, dashboard_title: str, position_json: str, published: bool = True) -> Any:
        return await self._request(
            "PUT",
            f"/api/v1/dashboard/{dashboard_id}",
            json={
                "dashboard_title": dashboard_title,
                "published": published,
                "position_json": position_json,
                "json_metadata": json.dumps({}),
            },
        )

    async def get_dashboard(self, dashboard_id: int) -> Any:
        return await self._request("GET", f"/api/v1/dashboard/{dashboard_id}")

    async def create_guest_token(self, dashboard_id: int, guest_username: str) -> Any:
        return await self._request(
            "POST",
            "/api/v1/security/guest_token/",
            json={
                "user": {
                    "username": guest_username,
                    "first_name": "SB",
                    "last_name": "Guest",
                },
                "resources": [{"type": "dashboard", "id": str(dashboard_id)}],
                "rls": [],
            },
        )

    async def publish_dashboard(
        self,
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
        resolved_catalog_name = settings.sb_catalog
        resolved_guest_username = guest_username or settings.superset_mcp_guest_username

        database = await self.find_database_by_name(resolved_database_name)
        database_id = database.get("id")
        if not database_id:
            raise ValueError(f"Superset database '{resolved_database_name}' did not include an id")

        dashboard_response = await self.create_dashboard(
            dashboard_title=resolved_title,
            slug=_slugify(resolved_title, "dashboard"),
            published=True,
        )
        dashboard_result = _result_payload(dashboard_response) or {}
        dashboard_id = _result_id(dashboard_response)
        if not dashboard_id:
            raise ValueError("Superset did not return a dashboard id")

        dataset_name = f"{_slugify(resolved_title)}_dataset"
        dataset_response = await self.create_dataset(
            database_id=database_id,
            dataset_name=dataset_name,
            sql=sql,
            schema_name=resolved_schema_name,
            catalog_name=resolved_catalog_name,
        )
        dataset_result = _result_payload(dataset_response) or {}
        dataset_id = _result_id(dataset_response)
        if not dataset_id:
            raise ValueError("Superset did not return a dataset id")

        chart_response = await self.create_chart(
            _build_chart_payload(
                dataset_id=dataset_id,
                dataset_name=dataset_name,
                dashboard_id=dashboard_id,
                chart_title=resolved_chart_title,
                chart_type=resolved_chart_type,
                x_axis=resolved_x,
                y_axis=resolved_y,
                row_limit=row_limit,
            )
        )
        chart_result = _result_payload(chart_response) or {}
        chart_id = _result_id(chart_response)
        if not chart_id:
            raise ValueError("Superset did not return a chart id")

        chart_detail = _result_payload(await self.get_chart(chart_id)) or {}
        position_json = _build_position_json(
            chart_id=chart_id,
            chart_uuid=chart_detail.get("uuid"),
            chart_title=resolved_chart_title,
        )
        await self.update_dashboard_layout(
            dashboard_id=dashboard_id,
            dashboard_title=resolved_title,
            position_json=position_json,
            published=True,
        )

        payload: Dict[str, Any] = {
            "database": database,
            "dataset": dataset_result,
            "chart": chart_detail or chart_result,
            "dashboard": _result_payload(await self.get_dashboard(dashboard_id)) or dashboard_result,
            "dashboard_id": dashboard_id,
            "chart_id": chart_id,
            "dataset_id": dataset_id,
            "dashboard_url": f"{self._public_url}/superset/dashboard/{dashboard_id}/?standalone=1",
            "standalone_url": f"{self._public_url}/superset/dashboard/{dashboard_id}/?standalone=1",
            "chart_url": f"{self._public_url}/explore/?slice_id={chart_id}",
            "question": question,
            "sql": sql,
            "chart_type": resolved_chart_type,
            "x": resolved_x,
            "y": resolved_y,
            "database_name": resolved_database_name,
            "catalog_name": resolved_catalog_name,
            "schema_name": resolved_schema_name,
            "integration_mode": "rest",
        }
        payload["guest_token"] = await self.create_guest_token(dashboard_id=dashboard_id, guest_username=resolved_guest_username)
        return payload

    async def serve_dashboard(self, dashboard_id: int, guest_username: Optional[str] = None, standalone: bool = True) -> Dict[str, Any]:
        resolved_guest_username = guest_username or settings.superset_mcp_guest_username
        guest_token = await self.create_guest_token(dashboard_id=dashboard_id, guest_username=resolved_guest_username)
        suffix = "?standalone=1" if standalone else ""
        return {
            "dashboard_id": dashboard_id,
            "guest_username": resolved_guest_username,
            "guest_token": guest_token,
            "url": f"{self._public_url}/superset/dashboard/{dashboard_id}/{suffix}" if suffix else f"{self._public_url}/superset/dashboard/{dashboard_id}/",
            "integration_mode": "rest",
        }
