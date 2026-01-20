from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import networkx as nx


_GRAPH_STORE: Dict[str, nx.DiGraph] = {}


def _get_graph(graph_id: str, directed: bool = True) -> nx.DiGraph:
    if graph_id in _GRAPH_STORE:
        return _GRAPH_STORE[graph_id]
    graph = nx.DiGraph() if directed else nx.Graph()
    _GRAPH_STORE[graph_id] = graph
    return graph


def knowledge_graph_upsert(
    graph_id: str,
    entities: List[Dict[str, Any]],
    relations: List[Dict[str, Any]],
    directed: bool = True,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Create or update an in-memory knowledge graph using NetworkX."""
    if overwrite or graph_id not in _GRAPH_STORE:
        _GRAPH_STORE[graph_id] = nx.DiGraph() if directed else nx.Graph()

    graph = _GRAPH_STORE[graph_id]

    for entity in entities:
        node_id = str(entity.get("id") or entity.get("name"))
        if not node_id:
            continue
        attributes = {k: v for k, v in entity.items() if k != "id"}
        graph.add_node(node_id, **attributes)

    for relation in relations:
        source = str(relation.get("source"))
        target = str(relation.get("target"))
        if not source or not target:
            continue
        attributes = {k: v for k, v in relation.items() if k not in {"source", "target"}}
        graph.add_edge(source, target, **attributes)

    return {
        "graph_id": graph_id,
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "directed": graph.is_directed(),
    }


def knowledge_graph_query(
    graph_id: str,
    node_id: str,
    depth: int = 1,
    relation_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """Return neighboring nodes and edges for a node within a depth."""
    graph = _GRAPH_STORE.get(graph_id)
    if not graph:
        return {"error": f"Graph '{graph_id}' not found"}

    if node_id not in graph:
        return {"error": f"Node '{node_id}' not found in graph '{graph_id}'"}

    distances = nx.single_source_shortest_path_length(graph, node_id, cutoff=depth)
    nodes = [n for n in distances.keys()]
    subgraph = graph.subgraph(nodes)

    node_payload = [
        {"id": node, **subgraph.nodes[node]} for node in subgraph.nodes
    ]

    edge_payload = []
    for source, target, attrs in subgraph.edges(data=True):
        relation = attrs.get("relation") or attrs.get("type")
        if relation_filter and relation != relation_filter:
            continue
        edge_payload.append({"source": source, "target": target, **attrs})

    return {
        "graph_id": graph_id,
        "center": node_id,
        "depth": depth,
        "nodes": node_payload,
        "edges": edge_payload,
    }


def knowledge_graph_shortest_path(
    graph_id: str,
    source: str,
    target: str,
    max_depth: int = 4,
) -> Dict[str, Any]:
    """Find the shortest path between two nodes."""
    graph = _GRAPH_STORE.get(graph_id)
    if not graph:
        return {"error": f"Graph '{graph_id}' not found"}

    if source not in graph or target not in graph:
        return {"error": "source or target node not found"}

    try:
        path = nx.shortest_path(graph, source=source, target=target)
    except nx.NetworkXNoPath:
        return {"error": f"No path between '{source}' and '{target}'"}

    if len(path) - 1 > max_depth:
        return {"error": "Path exceeds max_depth", "path": path}

    return {"graph_id": graph_id, "source": source, "target": target, "path": path}
