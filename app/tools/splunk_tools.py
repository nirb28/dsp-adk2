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
    username: Optional[str] = None,
    password: Optional[str] = None,
    verify_ssl: Optional[bool] = None,
) -> Dict[str, Any]:
    """Query Splunk using the search jobs endpoint with basic auth and oneshot exec mode."""
    resolved_base_url = base_url or os.getenv("SPLUNK_BASE_URL", "http://localhost:8089")
    resolved_username = username or os.getenv("SPLUNK_USERNAME")
    resolved_password = password or os.getenv("SPLUNK_PASSWORD")
    if not (resolved_username and resolved_password):
        raise ValueError("Splunk username and password are required for basic auth.")

    search_query = _build_search_query(query=query, indexes=indexes, search=search)

    payload: Dict[str, Any] = {
        "search": search_query,
        "output_mode": output_mode,
        "exec_mode": "oneshot",
    }

    if earliest_time:
        payload["earliest_time"] = earliest_time
    if latest_time:
        payload["latest_time"] = latest_time
    if max_count is not None:
        payload["max_count"] = max_count

    resolved_verify = settings.ssl_verify if verify_ssl is None else verify_ssl
    headers: Dict[str, str] = {"Content-Type": "application/x-www-form-urlencoded"}
    client_kwargs: Dict[str, Any] = {
        "verify": resolved_verify,
        "auth": (resolved_username, resolved_password),
    }

    async with httpx.AsyncClient(headers=headers, **client_kwargs) as client:
        response = await client.post(
            f"{resolved_base_url}/services/search/jobs",
            data=payload,
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

    return {
        "search": search_query,
        "event_count": len(events),
        "events": events,
        "raw": raw_text,
    }
