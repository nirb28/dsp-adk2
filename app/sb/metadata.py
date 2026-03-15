from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from app.config import settings
from app.sb.client import get_starburst_client
from app.sb.utils import coerce_text, ensure_dict, ensure_json_text, tokenize


class SemanticMetadataStore:
    def __init__(self, metadata_dir: Optional[str] = None) -> None:
        self.metadata_dir = Path(metadata_dir or settings.sb_metadata_dir)

    def _load_yaml_file(self, path: Path) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        if not isinstance(payload, dict):
            return {"name": path.stem, "raw": payload}
        payload.setdefault("name", path.stem)
        payload.setdefault("source_file", str(path))
        return payload

    def load_assets(self, metadata_file: Optional[str] = None) -> List[Dict[str, Any]]:
        if metadata_file:
            explicit_path = Path(metadata_file)
            if not explicit_path.is_absolute():
                explicit_path = self.metadata_dir / metadata_file
            if explicit_path.exists():
                return [self._load_yaml_file(explicit_path)]
            raise FileNotFoundError(f"Metadata file not found: {explicit_path}")

        if not self.metadata_dir.exists():
            return []
        return [self._load_yaml_file(path) for path in sorted(self.metadata_dir.rglob("*.yaml"))]

    def search(
        self,
        question: str,
        plan: Optional[Any] = None,
        metadata_file: Optional[str] = None,
        max_results: int = 5,
    ) -> Dict[str, Any]:
        assets = self.load_assets(metadata_file=metadata_file)
        plan_dict = ensure_dict(plan)
        search_text = " ".join(
            part
            for part in [
                question,
                plan_dict.get("metric"),
                ensure_json_text(plan_dict.get("dimensions")),
                ensure_json_text(plan_dict.get("filters")),
                plan_dict.get("intent"),
            ]
            if part
        )
        query_tokens = set(tokenize(search_text))
        scored: List[Dict[str, Any]] = []

        for asset in assets:
            asset_text_parts: List[str] = [
                asset.get("name", ""),
                asset.get("description", ""),
                ensure_json_text(asset.get("metrics", [])),
                ensure_json_text(asset.get("dimensions", [])),
                ensure_json_text(asset.get("sample_queries", [])),
                ensure_json_text(asset.get("tables", [])),
                ensure_json_text(asset.get("business_rules", [])),
            ]
            asset_tokens = set(tokenize(" ".join(asset_text_parts)))
            score = len(query_tokens.intersection(asset_tokens))
            scored.append({"asset": asset, "score": score})

        scored.sort(key=lambda item: item["score"], reverse=True)
        selected_assets = [item["asset"] for item in scored[:max_results] if item["score"] > 0] or [item["asset"] for item in scored[:1] if item.get("asset")]
        context = self._build_context(selected_assets)
        return {
            "question": question,
            "plan": plan_dict,
            "matched_assets": selected_assets,
            "semantic_context": context,
            "summary": self._build_summary(selected_assets),
        }

    def _build_context(self, assets: List[Dict[str, Any]]) -> Dict[str, Any]:
        tables: List[Dict[str, Any]] = []
        metrics: List[Dict[str, Any]] = []
        dimensions: List[Dict[str, Any]] = []
        sample_queries: List[Dict[str, Any]] = []
        business_rules: List[Any] = []

        for asset in assets:
            tables.extend(asset.get("tables", []))
            metrics.extend(asset.get("metrics", []))
            dimensions.extend(asset.get("dimensions", []))
            sample_queries.extend(asset.get("sample_queries", []))
            business_rules.extend(asset.get("business_rules", []))

        return {
            "tables": tables,
            "metrics": metrics,
            "dimensions": dimensions,
            "sample_queries": sample_queries,
            "business_rules": business_rules,
        }

    def _build_summary(self, assets: List[Dict[str, Any]]) -> str:
        sections: List[str] = []
        for asset in assets:
            sections.append(f"Domain: {asset.get('name', 'unknown')}")
            if asset.get("description"):
                sections.append(f"Description: {asset['description']}")
            tables = asset.get("tables", [])
            if tables:
                table_lines = []
                for table in tables[:8]:
                    columns = ", ".join(column.get("name", "") for column in table.get("columns", [])[:10])
                    table_lines.append(f"- {table.get('catalog', '')}.{table.get('schema', '')}.{table.get('name', '')}: {table.get('description', '')} Columns: {columns}")
                sections.append("Tables:\n" + "\n".join(table_lines))
            metrics = asset.get("metrics", [])
            if metrics:
                metric_lines = [f"- {metric.get('name')}: {metric.get('description')} ({metric.get('expression')})" for metric in metrics[:10]]
                sections.append("Metrics:\n" + "\n".join(metric_lines))
            sample_queries = asset.get("sample_queries", [])
            if sample_queries:
                query_lines = [f"- {item.get('question')}: {item.get('sql')}" for item in sample_queries[:5]]
                sections.append("Sample queries:\n" + "\n".join(query_lines))
            business_rules = asset.get("business_rules", [])
            if business_rules:
                sections.append("Business rules:\n" + "\n".join(f"- {rule}" for rule in business_rules[:10]))
        return "\n\n".join(part for part in sections if part)


def search_semantic_metadata(
    question: str,
    plan: Optional[Any] = None,
    metadata_file: Optional[str] = None,
    include_live_schema: bool = False,
    catalog: Optional[str] = None,
    schema: Optional[str] = None,
    max_results: int = 5,
    **connection_kwargs: Any,
) -> Dict[str, Any]:
    store = SemanticMetadataStore()
    result = store.search(question=coerce_text(question), plan=plan, metadata_file=metadata_file, max_results=max_results)

    live_schema: Dict[str, Any] = {}
    if include_live_schema and (catalog or settings.sb_catalog) and (schema or settings.sb_schema):
        client = get_starburst_client(catalog=catalog, schema=schema, **connection_kwargs)
        live_schema = client.list_tables(catalog=catalog, schema=schema)

    result["live_schema"] = live_schema
    return result
