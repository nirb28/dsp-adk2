import asyncio
import os

import httpx


async def execute_tool(client: httpx.AsyncClient, base_url: str, tool_name: str, parameters: dict) -> dict:
    response = await client.post(
        f"{base_url}/execute/tool",
        json={"tool_name": tool_name, "parameters": parameters},
        timeout=180.0,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise RuntimeError(f"{tool_name} failed: {data.get('error')}")
    return data.get("result")


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")
    claim_id = os.getenv("CLAIM_ID", "C010")
    pdf_path = os.getenv("MERCHANT_PDF_PATH", "")

    if not pdf_path:
        raise ValueError("Set MERCHANT_PDF_PATH to a local PDF file before running this script.")

    async with httpx.AsyncClient() as client:
        ocr = await execute_tool(
            client,
            base_url,
            "claim_ocr_pdf_with_vision",
            {
                "pdf_path": pdf_path,
                "model": os.getenv("VISION_MODEL", "meta/llama-3.2-90b-vision-instruct"),
                "max_pages": int(os.getenv("OCR_MAX_PAGES", "2")),
            },
        )
        print("OCR pages processed:", ocr.get("pages_processed"))

        context = await execute_tool(client, base_url, "claim_get_context", {"claim_id": claim_id})
        extracted = await execute_tool(
            client,
            base_url,
            "claim_extract_entities",
            {"representation_text": ocr.get("combined_text", "")},
        )
        comparison = await execute_tool(
            client,
            base_url,
            "claim_compare",
            {"claim_record": context["claim_record"], "extracted_entities": extracted},
        )
        decision = await execute_tool(
            client,
            base_url,
            "claim_decide",
            {"comparison": comparison, "reason_code": context["claim_record"]["reason_code"]},
        )

    print("\nClaim ID:", claim_id)
    print("Decision:", decision.get("decision"))
    print("Rationale:")
    for line in decision.get("rationale", []):
        print("-", line)


if __name__ == "__main__":
    asyncio.run(main())
