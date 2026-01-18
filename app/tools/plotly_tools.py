from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.express as px

from app.config import settings


def plotly_visualization(
    data: Optional[List[Dict[str, Any]]] = None,
    chart_type: Optional[str] = None,
    x: Optional[str] = None,
    y: Optional[str] = None,
    title: Optional[str] = None,
    output_format: str = "html",
    output_path: Optional[str] = None,
    **_: Any,
) -> Dict[str, Any]:
    """Create a Plotly visualization from tabular data and save to file."""
    if not data:
        return {"error": "data must contain at least one row"}
    if not chart_type:
        return {"error": "chart_type is required"}
    if not x:
        return {"error": "x is required"}

    df = pd.DataFrame(data)
    if x not in df.columns:
        return {"error": f"x column '{x}' not found in data"}
    if y and y not in df.columns:
        return {"error": f"y column '{y}' not found in data"}

    chart_type = chart_type.lower()
    title = title or f"{chart_type.title()} chart"

    if chart_type == "bar":
        fig = px.bar(df, x=x, y=y, title=title)
    elif chart_type == "line":
        fig = px.line(df, x=x, y=y, title=title)
    elif chart_type == "scatter":
        fig = px.scatter(df, x=x, y=y, title=title)
    elif chart_type == "pie":
        fig = px.pie(df, names=x, values=y, title=title)
    else:
        return {"error": f"Unsupported chart_type '{chart_type}'"}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_format = output_format.lower()
    default_dir = Path(settings.data_dir) / "visualizations"
    default_dir.mkdir(parents=True, exist_ok=True)

    if output_path:
        target_path = Path(output_path)
    else:
        extension = "html" if output_format == "html" else output_format
        target_path = default_dir / f"plot_{timestamp}.{extension}"

    if output_format == "html":
        fig.write_html(str(target_path))
    elif output_format in {"png", "jpeg", "svg", "pdf"}:
        fig.write_image(str(target_path))
    else:
        return {"error": f"Unsupported output_format '{output_format}'"}

    return {
        "output_path": str(target_path),
        "output_format": output_format,
        "chart_type": chart_type,
        "title": title,
        "rows": len(df),
    }
