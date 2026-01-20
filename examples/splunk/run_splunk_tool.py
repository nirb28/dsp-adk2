import asyncio
import os

import httpx


def build_parameters() -> dict:
    return {
        "query": "error OR failed",
        "indexes": ["auth", "security"],
        "earliest_time": "-24h",
        "latest_time": "now",
        "max_count": 50,
    }


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")

    payload = {
        "tool_name": "splunk_search",
        "parameters": build_parameters(),
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/execute/tool",
            json=payload,
            timeout=120.0,
        )

    response.raise_for_status()
    data = response.json()

    print("Success:", data.get("success"))
    print("Result:", data.get("result"))
    if data.get("error"):
        print("Error:", data.get("error"))


if __name__ == "__main__":
    asyncio.run(main())
