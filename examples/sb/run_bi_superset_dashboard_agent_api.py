import asyncio
import os

import httpx


def build_prompt() -> str:
    question = os.getenv(
        "SB_EXAMPLE_QUESTION",
        "Analyze monthly revenue for the last 12 months by region and publish a Superset dashboard with a shareable URL.",
    )
    integration_mode = os.getenv("SUPERSET_INTEGRATION_MODE", "auto")
    return (
        f"{question}\n\n"
        f"Use Superset integration mode {integration_mode}. "
        f"Use metadata_file={os.getenv('SB_METADATA_FILE', 'galaxy_retail_semantic.yaml')}. "
        f"Use catalog={os.getenv('SB_CATALOG', '')}. "
        f"Use schema={os.getenv('SB_SCHEMA', '')}."
    )


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")
    payload = {
        "agent_name": "sb_bi_chatbot_analyst",
        "input": build_prompt(),
        "context": {},
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/execute/agent",
            json=payload,
            timeout=600.0,
        )
        response.raise_for_status()
        print(response.json())


if __name__ == "__main__":
    asyncio.run(main())
