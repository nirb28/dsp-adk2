from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.config import settings


class MCPClientService:
    @staticmethod
    def _normalize_result(tool_name: str, result: Any) -> Dict[str, Any]:
        content_blocks = []
        for block in getattr(result, "content", []) or []:
            if getattr(block, "type", None) == "text":
                content_blocks.append(block.text)
            else:
                content_blocks.append(block.model_dump(mode="json", by_alias=True))

        payload = getattr(result, "structuredContent", None)
        if payload is None and content_blocks:
            first_block = content_blocks[0]
            if isinstance(first_block, str):
                try:
                    payload = json.loads(first_block)
                except json.JSONDecodeError:
                    payload = {"text": first_block}

        return {
            "tool_name": tool_name,
            "is_error": bool(getattr(result, "isError", False)),
            "payload": payload,
            "content": content_blocks,
        }

    @staticmethod
    async def call_tool(
        server_url: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        resolved_timeout = timeout_seconds or settings.superset_mcp_timeout
        async with httpx.AsyncClient(
            headers=headers or {},
            timeout=resolved_timeout,
            verify=settings.ssl_verify,
        ) as http_client:
            async with streamable_http_client(server_url, http_client=http_client) as streams:
                read_stream, write_stream, _ = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=arguments or {})
        normalized = MCPClientService._normalize_result(tool_name, result)
        if normalized["is_error"]:
            raise RuntimeError(f"MCP tool '{tool_name}' failed: {normalized['payload'] or normalized['content']}")
        return normalized

    @staticmethod
    async def list_tools(
        server_url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        resolved_timeout = timeout_seconds or settings.superset_mcp_timeout
        async with httpx.AsyncClient(
            headers=headers or {},
            timeout=resolved_timeout,
            verify=settings.ssl_verify,
        ) as http_client:
            async with streamable_http_client(server_url, http_client=http_client) as streams:
                read_stream, write_stream, _ = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.list_tools()
        return {
            "tools": [tool.model_dump(mode="json", by_alias=True) for tool in result.tools],
        }
