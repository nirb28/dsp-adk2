import asyncio
import os

import httpx


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")
    analysis_id = os.getenv("SB_ANALYSIS_ID")
    if not analysis_id:
        raise ValueError("Set SB_ANALYSIS_ID to load a saved analysis.")

    payload = {
        "tool_name": "sb_load_analysis",
        "parameters": {"analysis_id": analysis_id},
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/execute/tool",
            json=payload,
            timeout=180.0,
        )
        response.raise_for_status()
        print(response.json())


if __name__ == "__main__":
    asyncio.run(main())
