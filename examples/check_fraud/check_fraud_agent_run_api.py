import asyncio
import os

import httpx


def build_prompt() -> str:
    return (
        "Analyze this check image.\n\n"
        "image_url: https://raw.githubusercontent.com/nirb28/dsp-adk2/refs/heads/main/examples/check_fraud/images/sample_fraud_check.jpg\n"
        "model: meta/llama-3.2-90b-vision-instruct\n"
    )


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")

    payload = {
        "agent_name": "check_fraud_analyst",
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
    print("Output:\n", data.get("output"))
    if data.get("error"):
        print("Error:", data.get("error"))


if __name__ == "__main__":
    asyncio.run(main())
