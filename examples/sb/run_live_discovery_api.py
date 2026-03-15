import asyncio
import os

import httpx


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")
    tool_calls = [
        {"tool_name": "sb_list_catalogs", "parameters": {}},
        {"tool_name": "sb_list_schemas", "parameters": {"catalog": os.getenv("SB_CATALOG")}},
        {
            "tool_name": "sb_list_tables",
            "parameters": {
                "catalog": os.getenv("SB_CATALOG"),
                "schema": os.getenv("SB_SCHEMA"),
            },
        },
    ]

    async with httpx.AsyncClient() as client:
        for payload in tool_calls:
            response = await client.post(
                f"{base_url}/execute/tool",
                json=payload,
                timeout=180.0,
            )
            response.raise_for_status()
            print(payload["tool_name"])
            print(response.json())
            print()


if __name__ == "__main__":
    asyncio.run(main())
