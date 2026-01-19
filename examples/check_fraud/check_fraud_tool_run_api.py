import asyncio
import os

import httpx

CHECK_FRAUD_SYSTEM_PROMPT = (
    "You are a forensic document examiner and fraud detection expert specializing in bank "
    "checks. Analyze the provided check image in detail. Extract and describe all visible "
    "elements step-by-step, including:\n\n"
    "1. Issuing company/bank details (name, address, etc.).\n"
    "2. Check number, date, and any validity clauses.\n"
    "3. Payee, numeric and written amounts.\n"
    "4. Signature and any handwriting analysis.\n"
    "5. MICR line and routing/account info.\n"
    "6. Security features (background patterns, warnings, watermarks).\n\n"
    "Then, assess for potential fraud indicators:\n"
    "- Consistency between amounts.\n"
    "- Anomalies in formatting, dates, or payee.\n"
    "- Signature authenticity (based on visuals).\n"
    "- Bank/company verification (note if outdated or suspicious).\n"
    "- Visible alterations (erasures, ink mismatches, photocopying signs).\n\n"
    "Conclude with overall fraud likelihood (yes/no) and confidence level (low/medium/high), "
    "plus reasoning. If it resembles known scam templates, mention that. Structure your "
    "response clearly with headings like 'Key Details' and 'Fraud Assessment'."
)


def build_parameters() -> dict:
    return {
        "image_url": "https://raw.githubusercontent.com/nirb28/dsp-adk2/refs/heads/main/examples/check_fraud/images/sample_fraud_check.jpg",
        "model": "meta/llama-3.2-90b-vision-instruct", # meta/llama-3.2-90b-vision-instruct, openai/gpt-oss-120b
        "system_prompt": CHECK_FRAUD_SYSTEM_PROMPT,
        "user_prompt": "Analyze this check image:",
        "temperature": 0.2,
        "top_p": 0.7,
        "max_tokens": 1024,
        "stream": False,
    }


async def main() -> None:
    base_url = os.getenv("ADK2_BASE_URL", "http://localhost:8200")

    payload = {
        "tool_name": "image_analysis",
        "parameters": build_parameters(),
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/execute/tool",
            json=payload,
            timeout=120.0,
        )

    response.raise_for_status()
    data = response.json()

    print("Success:", data.get("success"))
    print("Analysis:\n", data.get("result", {}).get("analysis"))
    if data.get("error"):
        print("Error:", data.get("error"))


if __name__ == "__main__":
    asyncio.run(main())
