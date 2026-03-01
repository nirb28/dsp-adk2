import asyncio
import os

import httpx


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")
    claim_id = os.getenv("CLAIM_ID", "C002")

    payload = {
        "agent_name": "claim_langgraph_analyst",
        "input": f"Process claim_id={claim_id} and provide final decision with rationale.",
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
    print("Output:\n", data.get("output"))
    print("\nSteps:")
    for step in data.get("steps", []):
        print(step)
    if data.get("error"):
        print("Error:", data.get("error"))


if __name__ == "__main__":
    asyncio.run(main())
