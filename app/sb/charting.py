from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.express as px

from app.config import settings
from app.sb.utils import ensure_dict, ensure_list


SUPPORTED_CHARTS = {"bar", "line", "scatter", "pie", "area", "hbar"}


def create_visualization(
    data: Optional[List[Dict[str, Any]]] = None,
    recommendation: Optional[Any] = None,
    chart_type: Optional[str] = None,
    x: Optional[str] = None,
    y: Optional[str] = None,
    color: Optional[str] = None,
    title: Optional[str] = None,
    output_format: str = "html",
    output_path: Optional[str] = None,
    analysis_id: Optional[str] = None,
    **_: Any,
) -> Dict[str, Any]:
    normalized_data = ensure_list(data)
    if not normalized_data:
        return {"error": "data must contain at least one row"}

    rec = ensure_dict(recommendation)
    resolved_chart_type = (chart_type or rec.get("chart_type") or "bar").lower()
    resolved_x = x or rec.get("x")
    resolved_y = y or rec.get("y")
    resolved_color = color or rec.get("color")

    if resolved_chart_type not in SUPPORTED_CHARTS:
        return {"error": f"Unsupported chart_type '{resolved_chart_type}'"}
    if not resolved_x:
        return {"error": "x is required"}

    df = pd.DataFrame(normalized_data)
    if resolved_x not in df.columns:
        return {"error": f"x column '{resolved_x}' not found"}
    if resolved_y and resolved_y not in df.columns:
        return {"error": f"y column '{resolved_y}' not found"}
    if resolved_color and resolved_color not in df.columns:
        resolved_color = None

    resolved_title = title or rec.get("title") or f"{resolved_chart_type.title()} chart"

    if resolved_chart_type == "bar":
        fig = px.bar(df, x=resolved_x, y=resolved_y, color=resolved_color, title=resolved_title)
    elif resolved_chart_type == "line":
        fig = px.line(df, x=resolved_x, y=resolved_y, color=resolved_color, title=resolved_title)
    elif resolved_chart_type == "scatter":
        fig = px.scatter(df, x=resolved_x, y=resolved_y, color=resolved_color, title=resolved_title)
    elif resolved_chart_type == "pie":
        fig = px.pie(df, names=resolved_x, values=resolved_y, title=resolved_title)
    elif resolved_chart_type == "area":
        fig = px.area(df, x=resolved_x, y=resolved_y, color=resolved_color, title=resolved_title)
    else:
        fig = px.bar(df, x=resolved_y, y=resolved_x, orientation="h", color=resolved_color, title=resolved_title)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    extension = "html" if output_format.lower() == "html" else output_format.lower()
    target_dir = Path(settings.sb_visualizations_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = Path(output_path) if output_path else target_dir / f"{analysis_id or 'sb'}_{timestamp}.{extension}"

    if output_format.lower() == "html":
        fig.write_html(str(target_path))
    else:
        fig.write_image(str(target_path))

    return {
        "output_path": str(target_path),
        "output_format": output_format.lower(),
        "chart_type": resolved_chart_type,
        "x": resolved_x,
        "y": resolved_y,
        "color": resolved_color,
        "title": resolved_title,
        "rows": len(df),
    }
