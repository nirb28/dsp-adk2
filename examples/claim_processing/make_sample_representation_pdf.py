from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    try:
        import fitz  # type: ignore
    except ImportError as exc:
        raise ImportError("Install pymupdf first: pip install pymupdf") from exc

    base_dir = Path(__file__).resolve().parent
    claim_id = os.getenv("CLAIM_ID", "C010")
    txt_path = base_dir / "data" / "merchant_representation_docs" / f"{claim_id}_representation.txt"
    output_path = base_dir / "data" / "merchant_representation_docs" / f"{claim_id}_representation.pdf"

    if not txt_path.exists():
        raise FileNotFoundError(f"Text representation not found: {txt_path}")

    content = txt_path.read_text(encoding="utf-8")

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    rect = fitz.Rect(48, 48, 547, 794)
    page.insert_textbox(rect, content, fontsize=11, fontname="helv")
    doc.save(output_path)
    doc.close()

    print(f"Created sample PDF: {output_path}")


if __name__ == "__main__":
    main()
