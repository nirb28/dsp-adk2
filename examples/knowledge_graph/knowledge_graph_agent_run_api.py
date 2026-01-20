import asyncio
import os

import httpx


def build_prompt() -> str:
    return (
        "Build a knowledge graph from the following entities and relations, then answer the question.\n\n"
        "Entities:\n"
        "- id: product_ai, type: product, name: DSP AI Platform\n"
        "- id: product_fd2, type: product, name: DSP Front Door\n"
        "- id: product_ct, type: product, name: DSP Control Tower\n"
        "- id: service_auth, type: service, name: JWT Auth Service\n"
        "- id: service_obs, type: service, name: Observability Stack\n\n"
        "Relations:\n"
        "- source: product_fd2, target: service_auth, relation: depends_on\n"
        "- source: product_fd2, target: service_obs, relation: depends_on\n"
        "- source: product_ct, target: service_auth, relation: depends_on\n"
        "- source: product_ct, target: product_fd2, relation: integrates_with\n\n"
        "Question: What services does DSP Control Tower depend on, and what is the shortest path between DSP Control Tower and DSP AI Platform?\n\n"
        "Use graph_id: demo_kg.\n"
    )


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")

    payload = {
        "agent_name": "knowledge_graph_analyst",
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
