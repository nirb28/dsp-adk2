from __future__ import annotations

import base64
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from app.models import LLMConfig, LLMOverride
from app.tools.image_tools import analyze_image

# Ensure project root is importable when running in varied execution contexts.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from examples.claim_processing.claim_processing_common import (
    compare_extracted_to_claim,
    decide_claim,
    evaluate_claim,
    extract_entities_from_representation,
    load_claims,
    load_representation_text,
)


def claim_get_context(claim_id: str) -> Dict[str, Any]:
    claims = load_claims()
    if claim_id not in claims:
        raise KeyError(f"Claim id not found: {claim_id}")
    return {
        "claim_id": claim_id,
        "claim_record": claims[claim_id],
        "merchant_representation_text": load_representation_text(claim_id),
    }


def claim_extract_entities(representation_text: str) -> Dict[str, Any]:
    return extract_entities_from_representation(representation_text)


def claim_compare(claim_record: Dict[str, Any], extracted_entities: Dict[str, Any]) -> Dict[str, Any]:
    return compare_extracted_to_claim(claim_record, extracted_entities)


def claim_decide(comparison: Dict[str, Any], reason_code: str) -> Dict[str, Any]:
    decision, rationale = decide_claim(comparison, reason_code)
    return {"decision": decision, "rationale": rationale}


def claim_evaluate_end_to_end(claim_id: str) -> Dict[str, Any]:
    result = evaluate_claim(claim_id)
    return result.to_dict()


async def claim_ocr_pdf_with_vision(
    pdf_path: str,
    model: Optional[str] = None,
    max_pages: int = 2,
    system_prompt: Optional[str] = None,
    user_prompt: Optional[str] = None,
    llm_override: Optional[LLMOverride] = None,
    llm_config: Optional[LLMConfig] = None,
) -> Dict[str, Any]:
    """
    OCR a scanned merchant representation PDF via a vision-capable LLM.

    Notes:
    - Requires `pymupdf` (import name `fitz`) to rasterize PDF pages.
    - Sends each page as a data URL image to the image analysis tool.
    """

    try:
        import fitz  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "pymupdf is required for PDF OCR. Install with: pip install pymupdf"
        ) from exc

    source_path = Path(pdf_path).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"PDF not found: {source_path}")

    ocr_system_prompt = system_prompt or (
        "You are an OCR specialist for payment dispute documents. Extract readable text exactly, "
        "preserve key-value labels, and do not invent missing content."
    )
    ocr_user_prompt = user_prompt or (
        "Extract all text from this merchant representation page. Return plain text only."
    )

    page_results = []
    combined_text_parts = []

    with fitz.open(source_path) as document:
        for page_index in range(min(max_pages, document.page_count)):
            page = document.load_page(page_index)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            png_bytes = pix.tobytes("png")
            data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")

            analysis = await analyze_image(
                image_url=data_url,
                model=model,
                system_prompt=ocr_system_prompt,
                user_prompt=ocr_user_prompt,
                temperature=0.0,
                top_p=0.1,
                max_tokens=1800,
                stream=False,
                llm_override=llm_override,
                llm_config=llm_config,
            )
            page_text = analysis.get("analysis") or ""
            combined_text_parts.append(page_text)
            page_results.append({
                "page": page_index + 1,
                "text": page_text,
                "model": analysis.get("model"),
            })

    return {
        "pdf_path": str(source_path),
        "pages_processed": len(page_results),
        "page_results": page_results,
        "combined_text": "\n\n".join(part for part in combined_text_parts if part),
    }
