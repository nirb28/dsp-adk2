import asyncio
import os
from pathlib import Path

import httpx


def build_payload() -> dict:
    db_path = Path(__file__).parents[1] / "text_to_sql" / "sample_complex.db"
    focus_node = os.getenv("KG_FOCUS_NODE", "segment_enterprise_north")

    return {
        "graph_id": "sql-kg-tool-chain",
        "input": {
            "db_path": str(db_path),
            "focus_node": focus_node,
        },
        "context": {},
    }


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")
    payload = build_payload()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/execute/graph",
            json=payload,
            timeout=120.0,
        )

    if response.status_code >= 400:
        print("Request failed:", response.status_code)
        print("Response:", response.text)
        return

    data = response.json()

    print("Success:", data.get("success"))
    print("Output:", data.get("output"))
    if data.get("error"):
        print("Error:", data.get("error"))


if __name__ == "__main__":
    asyncio.run(main())
