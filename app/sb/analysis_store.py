from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import settings
from app.sb.utils import generate_analysis_id, json_safe


class AnalysisStore:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self.base_dir = Path(base_dir or settings.sb_saved_analyses_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, payload: Dict[str, Any], analysis_id: Optional[str] = None) -> Dict[str, Any]:
        resolved_analysis_id = analysis_id or generate_analysis_id(payload.get("question") or "analysis")
        path = self.base_dir / f"{resolved_analysis_id}.json"
        record = {
            "analysis_id": resolved_analysis_id,
            "saved_at": datetime.utcnow().isoformat() + "Z",
            **json_safe(payload),
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2, default=str)
        return {"analysis_id": resolved_analysis_id, "output_path": str(path)}

    def load(self, analysis_id: str) -> Dict[str, Any]:
        path = self.base_dir / f"{analysis_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Analysis '{analysis_id}' not found")
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
