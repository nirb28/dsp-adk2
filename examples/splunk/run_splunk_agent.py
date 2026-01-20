import asyncio
import os

import httpx


def build_prompt() -> str:
    return (
        "Use Splunk to summarize failed login events in the last 24 hours.\n"
        "Indexes: auth, security\n"
        "Time range: earliest=-24h latest=now\n"
    )


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")

    payload = {
        "agent_name": "splunk_analyst",
        "input": build_prompt(),
        "context": {},
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/execute/agent",
            json=payload,
            timeout=120.0,
        )

    response.raise_for_status()
    data = response.json()

    print("Success:", data.get("success"))
    print("Output:", data.get("output"))
    if data.get("error"):
        print("Error:", data.get("error"))


if __name__ == "__main__":
    asyncio.run(main())
