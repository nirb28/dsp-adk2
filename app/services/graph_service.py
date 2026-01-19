import time
import logging
from typing import Dict, Any, List, Optional

from langgraph.graph import StateGraph, END

from app.models import GraphConfig, GraphNodeType, GraphExecutionResponse
from app.services.yaml_service import YAMLService
from app.services.agent_service import AgentService
from app.services.tool_service import ToolService


class GraphService:
    logger = logging.getLogger(__name__)

    @staticmethod
    def list_graphs() -> List[str]:
        return YAMLService.list_graphs()

    @staticmethod
    def get_graph(graph_id: str) -> Optional[GraphConfig]:
        return YAMLService.load_graph(graph_id)

    @staticmethod
    def save_graph(graph: GraphConfig) -> None:
        YAMLService.save_graph(graph)

    @staticmethod
    def delete_graph(graph_id: str) -> bool:
        return YAMLService.delete_graph(graph_id)

    @staticmethod
    async def execute_graph(graph_id: str, input_data: Dict[str, Any], context: Dict[str, Any]) -> GraphExecutionResponse:
        start_time = time.time()
        graph_config = YAMLService.load_graph(graph_id)
        if not graph_config:
            return GraphExecutionResponse(
                graph_id=graph_id,
                success=False,
                output={},
                steps=[],
                error=f"Graph '{graph_id}' not found",
                execution_time=time.time() - start_time,
            )

        try:
            steps: List[Dict[str, Any]] = []
            workflow = StateGraph(dict)
            node_configs = {node.id: node for node in graph_config.nodes}

            def _get_value_from_state(path: str, state: Dict[str, Any]) -> Any:
                if not path.startswith("$." ):
                    return state.get(path, path)
                parts = path[2:].split(".")
                value: Any = state
                for part in parts:
                    if isinstance(value, dict):
                        value = value.get(part)
                    else:
                        return None
                return value

            def _apply_mapping(mapping: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
                if not mapping:
                    return state
                payload: Dict[str, Any] = {}
                for key, value in mapping.items():
                    if isinstance(value, str):
                        payload[key] = _get_value_from_state(value, state)
                    else:
                        payload[key] = value
                return payload

            for node in graph_config.nodes:
                if node.type == GraphNodeType.START:
                    workflow.add_node(node.id, lambda state: state)
                    continue
                if node.type == GraphNodeType.END:
                    continue

                async def node_runner(state: Dict[str, Any], node_id: str = node.id) -> Dict[str, Any]:
                    node_config = node_configs[node_id]
                    if node_config.type == GraphNodeType.AGENT:
                        agent_name = node_config.agent_id
                        agent_payload = _apply_mapping(node_config.input_mapping, state)
                        agent_input = agent_payload.get("prompt") or agent_payload.get("message") or agent_payload
                        result = await AgentService.execute_agent(agent_name, str(agent_input), context)
                        if not result.success:
                            raise RuntimeError(result.error or "Agent execution failed")
                        response_state = {"response": result.output}
                        state.update(_apply_mapping(node_config.output_mapping, response_state))
                        steps.append({"type": "agent", "node": node_id, "agent": agent_name, "output": result.output})
                    elif node_config.type == GraphNodeType.TOOL:
                        tool_name = node_config.tool_id
                        tool_payload = _apply_mapping(node_config.input_mapping, state)
                        result = await ToolService.execute_tool(tool_name, tool_payload)
                        if not result.success:
                            raise RuntimeError(result.error or "Tool execution failed")
                        response_state = {"response": result.result}
                        state.update(_apply_mapping(node_config.output_mapping, response_state))
                        steps.append({"type": "tool", "node": node_id, "tool": tool_name, "output": result.result})
                    else:
                        steps.append({"type": "custom", "node": node_id, "state": state})
                    return state

                workflow.add_node(node.id, node_runner)

            entry_point = graph_config.entry_point or next((n.id for n in graph_config.nodes if n.type == GraphNodeType.START), None)
            if not entry_point:
                raise ValueError("Graph entry point not defined")

            workflow.set_entry_point(entry_point)

            for edge in graph_config.edges:
                source = END if edge.source == "END" else edge.source
                target = END if edge.target == "END" else edge.target
                workflow.add_edge(source, target)

            compiled = workflow.compile()
            final_state = await compiled.ainvoke(input_data)

            return GraphExecutionResponse(
                graph_id=graph_id,
                success=True,
                output=final_state or {},
                steps=steps,
                error=None,
                execution_time=time.time() - start_time,
            )
        except Exception as exc:
            GraphService.logger.error("Graph execution failed: %s", exc)
            return GraphExecutionResponse(
                graph_id=graph_id,
                success=False,
                output={},
                steps=[],
                error=str(exc),
                execution_time=time.time() - start_time,
            )
