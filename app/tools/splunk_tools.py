import json
import os
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
    verify_ssl: bool = True,
) -> Dict[str, Any]:
    """Query Splunk using the search jobs export endpoint."""
    resolved_base_url = base_url or os.getenv("SPLUNK_BASE_URL", "http://localhost:8089")
    resolved_token = token or os.getenv("SPLUNK_TOKEN")
    if not resolved_token:
        raise ValueError("Splunk token is required. Provide token or set SPLUNK_TOKEN.")

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

    headers = {
        "Authorization": f"Splunk {resolved_token}",
    }

    async with httpx.AsyncClient(verify=verify_ssl) as client:
        response = await client.post(
            f"{resolved_base_url}/services/search/jobs/export",
            data=payload,
            headers=headers,
            timeout=120.0,
        )
        response.raise_for_status()

    raw_text = response.text
    events: List[Dict[str, Any]] = []
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
