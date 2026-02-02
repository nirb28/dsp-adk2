import json
import os
from app.config import settings
from typing import Any, Dict, List, Optional

import httpx


def _build_search_query(
    query: str,
    indexes: Optional[List[str]] = None,
    search: Optional[str] = None,
) -> str:
    if search:
        return search

    index_clause = ""
    if indexes:
        joined_indexes = " OR ".join(f"index={index}" for index in indexes)
        index_clause = f"{joined_indexes} "

    query = query.strip()
    if query and not query.lower().startswith("search "):
        query = f"{query}"

    return f"search {index_clause}{query}".strip()


async def splunk_search(
    query: str,
    indexes: Optional[List[str]] = None,
    search: Optional[str] = None,
    earliest_time: Optional[str] = None,
    latest_time: Optional[str] = None,
    max_count: Optional[int] = None,
    output_mode: str = "json",
    base_url: Optional[str] = None,
    token: Optional[str] = None,
    session_key: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    auth_method: str = "auto",
    use_sid_flow: bool = False,
    verify_ssl: Optional[bool] = None,
) -> Dict[str, Any]:
    """Query Splunk using the search jobs export endpoint."""
    resolved_base_url = base_url or os.getenv("SPLUNK_BASE_URL", "http://localhost:8089")
    resolved_token = token or os.getenv("SPLUNK_TOKEN")
    resolved_session_key = session_key or os.getenv("SPLUNK_SESSION_KEY")
    resolved_username = username or os.getenv("SPLUNK_USERNAME")
    resolved_password = password or os.getenv("SPLUNK_PASSWORD")

    auth_method_normalized = auth_method.lower().strip()
    supported_methods = {"auto", "token", "session_key", "basic"}
    if auth_method_normalized not in supported_methods:
        raise ValueError(
            "Invalid auth_method. Use one of: auto, token, session_key, basic."
        )

    search_query = _build_search_query(query=query, indexes=indexes, search=search)

    payload: Dict[str, Any] = {
        "search": search_query,
        "output_mode": output_mode,
    }

    if earliest_time:
        payload["earliest_time"] = earliest_time
    if latest_time:
        payload["latest_time"] = latest_time
    if max_count is not None:
        payload["max_count"] = max_count

    resolved_verify = settings.ssl_verify if verify_ssl is None else verify_ssl
    headers: Dict[str, str] = {}
    client_kwargs: Dict[str, Any] = {"verify": resolved_verify}

    if auth_method_normalized == "token":
        if not resolved_token:
            raise ValueError("Splunk token is required for token auth.")
        headers["Authorization"] = f"Splunk {resolved_token}"
    elif auth_method_normalized == "session_key":
        if not resolved_session_key:
            raise ValueError("Splunk session key is required for session_key auth.")
        headers["Authorization"] = f"Splunk {resolved_session_key}"
    elif auth_method_normalized == "basic":
        if not (resolved_username and resolved_password):
            raise ValueError("Splunk username and password are required for basic auth.")
        client_kwargs["auth"] = (resolved_username, resolved_password)
    else:
        if resolved_session_key:
            headers["Authorization"] = f"Splunk {resolved_session_key}"
        elif resolved_token:
            headers["Authorization"] = f"Splunk {resolved_token}"
        elif resolved_username and resolved_password:
            client_kwargs["auth"] = (resolved_username, resolved_password)
        else:
            raise ValueError(
                "Provide SPLUNK_TOKEN, SPLUNK_SESSION_KEY, or SPLUNK_USERNAME/SPLUNK_PASSWORD."
            )

    async with httpx.AsyncClient(headers=headers or None, **client_kwargs) as client:
        if use_sid_flow:
            job_payload = dict(payload)
            job_payload["output_mode"] = "json"
            job_response = await client.post(
                f"{resolved_base_url}/services/search/jobs",
                data=job_payload,
                headers=headers,
                timeout=120.0,
            )
            job_response.raise_for_status()

            job_data = job_response.json()
            sid = job_data.get("sid")
            if not sid:
                raise ValueError("Splunk job did not return a SID.")

            results_params: Dict[str, Any] = {"output_mode": output_mode}
            if max_count is not None:
                results_params["count"] = max_count

            response = await client.get(
                f"{resolved_base_url}/services/search/jobs/{sid}/results",
                params=results_params,
                headers=headers,
                timeout=120.0,
            )
            response.raise_for_status()
        else:
            response = await client.post(
                f"{resolved_base_url}/services/search/jobs/export",
                data=payload,
                headers=headers,
                timeout=120.0,
            )
            response.raise_for_status()

    raw_text = response.text
    events: List[Dict[str, Any]] = []
    if response.headers.get("content-type", "").startswith("application/json"):
        data = response.json()
        if isinstance(data, dict) and "results" in data:
            events = data.get("results", [])
        elif isinstance(data, list):
            events = data
        raw_text = json.dumps(data)
    else:
        for line in raw_text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    result = {
        "search": search_query,
        "event_count": len(events),
        "events": events,
        "raw": raw_text,
    }
    if use_sid_flow:
        result["sid"] = sid
    return result
