import os
from typing import Any, Dict, Optional

import httpx


def _build_headers(authorization: Optional[str] = None) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    return headers


async def rag_query(
    query: str,
    configuration_name: str = "default",
    k: Optional[int] = 5,
    similarity_threshold: Optional[float] = None,
    include_metadata: bool = True,
    context_items: Optional[list] = None,
    config: Optional[Dict[str, Any]] = None,
    filter_after_reranking: bool = True,
    query_expansion: Optional[Dict[str, Any]] = None,
    filter: Optional[Dict[str, Any]] = None,
    debug: bool = False,
    authorization: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Call the DSP AI RAG2 /query endpoint."""
    resolved_base_url = base_url or os.getenv("DSP_AI_RAG2_BASE_URL", "http://localhost:9000/api/v1")

    payload: Dict[str, Any] = {
        "query": query,
        "configuration_name": configuration_name,
        "k": k,
        "similarity_threshold": similarity_threshold,
        "include_metadata": include_metadata,
        "context_items": context_items,
        "config": config,
        "filter_after_reranking": filter_after_reranking,
        "query_expansion": query_expansion,
        "filter": filter,
        "debug": debug,
    }

    payload = {key: value for key, value in payload.items() if value is not None}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{resolved_base_url}/query",
            json=payload,
            headers=_build_headers(authorization),
            timeout=120.0,
        )
        response.raise_for_status()
        return response.json()


async def rag_retrieve(
    query: str,
    configuration_name: Optional[str] = "default",
    configuration_names: Optional[list] = None,
    k: int = 5,
    similarity_threshold: Optional[float] = None,
    include_metadata: bool = True,
    use_reranking: bool = False,
    include_vectors: bool = False,
    config: Optional[Dict[str, Any]] = None,
    fusion_method: Optional[str] = "rrf",
    rrf_k_constant: int = 60,
    filter_after_reranking: bool = True,
    query_expansion: Optional[Dict[str, Any]] = None,
    filter: Optional[Dict[str, Any]] = None,
    debug: bool = False,
    authorization: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Call the DSP AI RAG2 /retrieve endpoint."""
    resolved_base_url = base_url or os.getenv("DSP_AI_RAG2_BASE_URL", "http://localhost:9000/api/v1")

    payload: Dict[str, Any] = {
        "query": query,
        "configuration_name": configuration_name,
        "configuration_names": configuration_names,
        "k": k,
        "similarity_threshold": similarity_threshold,
        "include_metadata": include_metadata,
        "use_reranking": use_reranking,
        "include_vectors": include_vectors,
        "config": config,
        "fusion_method": fusion_method,
        "rrf_k_constant": rrf_k_constant,
        "filter_after_reranking": filter_after_reranking,
        "query_expansion": query_expansion,
        "filter": filter,
        "debug": debug,
    }

    payload = {key: value for key, value in payload.items() if value is not None}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{resolved_base_url}/retrieve",
            json=payload,
            headers=_build_headers(authorization),
            timeout=120.0,
        )
        response.raise_for_status()
        return response.json()
