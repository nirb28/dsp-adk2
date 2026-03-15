import asyncio
import os

import httpx


def build_payload() -> dict:
    return {
        "graph_id": "starburst-ai-bi-chatbot",
        "input": {
            "user_question": os.getenv(
                "SB_EXAMPLE_QUESTION",
                "Show monthly revenue trend for the last 12 months by region and create a chart.",
            ),
            "conversation_history": os.getenv("SB_EXAMPLE_HISTORY", ""),
            "metadata_file": os.getenv("SB_METADATA_FILE", "galaxy_retail_semantic.yaml"),
            "include_live_schema": os.getenv("SB_INCLUDE_LIVE_SCHEMA", "false").lower() == "true",
            "catalog": os.getenv("SB_CATALOG"),
            "schema": os.getenv("SB_SCHEMA"),
            "limit": int(os.getenv("SB_LIMIT", "200")),
            "output_format": os.getenv("SB_OUTPUT_FORMAT", "html"),
        },
        "context": {},
    }


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/execute/graph",
            json=build_payload(),
            timeout=600.0,
        )
        response.raise_for_status()
        print(response.json())


if __name__ == "__main__":
    asyncio.run(main())
