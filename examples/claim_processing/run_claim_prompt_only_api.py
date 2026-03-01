import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from examples.claim_processing.claim_processing_common import load_claims, load_representation_text


def build_input(claim_id: str) -> str:
    claims = load_claims()
    claim = claims[claim_id]
    representation = load_representation_text(claim_id)
    return (
        "Analyze this credit card dispute.\n\n"
        f"claim_record: {json.dumps(claim, ensure_ascii=True)}\n\n"
        "merchant_representation:\n"
        f"{representation}\n"
    )


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")
    claim_id = os.getenv("CLAIM_ID", "C003")
    payload = {
        "agent_name": "claim_prompt_only_analyst",
        "input": build_input(claim_id),
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
