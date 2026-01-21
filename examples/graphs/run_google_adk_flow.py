import asyncio
import os

import httpx


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")

    payload = {
        "graph_id": "google_adk_flow",
        "input": {"message": "Summarize how retrieval-augmented generation helps support analysts."},
        "context": {},
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/execute/graph",
            json=payload,
            timeout=60.0,
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
