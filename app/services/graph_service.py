import time
import logging
import os
from typing import Dict, Any, List, Optional

from langgraph.graph import StateGraph, END

import json

from app.models import GraphConfig, GraphNodeType, GraphExecutionResponse, GraphEdgeType, GraphType, LLMOverride
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
    async def execute_graph(
        graph_id: str,
        input_data: Dict[str, Any],
        context: Dict[str, Any],
        llm_override: Optional[LLMOverride] = None,
    ) -> GraphExecutionResponse:
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

        if graph_config.type == GraphType.GOOGLE_ADK:
            return await GraphService._execute_google_adk_flow(graph_config, input_data, context, llm_override)

        try:
            steps: List[Dict[str, Any]] = []
            workflow = StateGraph(dict)
            node_configs = {node.id: node for node in graph_config.nodes}

            def _get_value_from_state(path: str, state: Dict[str, Any]) -> Any:
                if not path.startswith("$."):
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
                        resolved = _get_value_from_state(value, state)
                        if resolved == value and "{{" in value:
                            rendered = value
                            for state_key, state_value in state.items():
                                rendered = rendered.replace(f"{{{{ {state_key} }}}}", str(state_value))
                            payload[key] = rendered
                        else:
                            payload[key] = resolved
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
                        result = await AgentService.execute_agent(agent_name, str(agent_input), context, llm_override)
                        if not result.success:
                            raise RuntimeError(result.error or "Agent execution failed")
                        response_state = {"response": result.output}
                        state.update(_apply_mapping(node_config.output_mapping, response_state))
                        steps.append({"type": "agent", "node": node_id, "agent": agent_name, "output": result.output})
                    elif node_config.type == GraphNodeType.TOOL:
                        tool_name = node_config.tool_id
                        tool_payload = _apply_mapping(node_config.input_mapping, state)
                        payload_override = node_config.config.get("payload", {}) if isinstance(node_config.config, dict) else {}
                        if payload_override:
                            resolved_override = _apply_mapping(payload_override, state)
                            tool_payload = {**resolved_override, **tool_payload}
                        result = await ToolService.execute_tool(tool_name, tool_payload, llm_override)
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

            edges_by_source: Dict[str, List[Any]] = {}
            for edge in graph_config.edges:
                edges_by_source.setdefault(edge.source, []).append(edge)

            for source, edges in edges_by_source.items():
                has_conditional = any(edge.type == GraphEdgeType.CONDITIONAL for edge in edges)
                if has_conditional:
                    conditional_edges = [edge for edge in edges if edge.type == GraphEdgeType.CONDITIONAL]

                    def route(state: Dict[str, Any], edge_set: List[Any] = conditional_edges) -> str:
                        for edge in edge_set:
                            if edge.condition:
                                value = _get_value_from_state(edge.condition, state)
                            else:
                                value = None

                            if edge.condition_value is not None:
                                if value == edge.condition_value:
                                    return END if edge.target == "END" else edge.target
                            else:
                                if value:
                                    return END if edge.target == "END" else edge.target
                        return END

                    workflow.add_conditional_edges(source, route)

                normal_edges = [edge for edge in edges if edge.type == GraphEdgeType.NORMAL]
                for edge in normal_edges:
                    source_node = END if edge.source == "END" else edge.source
                    target_node = END if edge.target == "END" else edge.target
                    workflow.add_edge(source_node, target_node)

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

    @staticmethod
    async def _execute_google_adk_flow(
        graph_config: GraphConfig,
        input_data: Dict[str, Any],
        context: Dict[str, Any],
        llm_override: Optional[LLMOverride] = None,
    ) -> GraphExecutionResponse:
        start_time = time.time()

        try:
            from google.adk.agents import LlmAgent, SequentialAgent
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
            from google.genai import types
        except ImportError as exc:
            return GraphExecutionResponse(
                graph_id=graph_config.id,
                success=False,
                output={},
                steps=[],
                error="google-adk is required for google_adk graphs. Install with 'pip install google-adk'.",
                execution_time=time.time() - start_time,
            )

        try:
            node_configs = {node.id: node for node in graph_config.nodes}
            entry_point = graph_config.entry_point or next(
                (n.id for n in graph_config.nodes if n.type == GraphNodeType.START),
                None,
            )
            if not entry_point:
                raise ValueError("Graph entry point not defined")

            edges_by_source: Dict[str, List[Any]] = {}
            for edge in graph_config.edges:
                if edge.type != GraphEdgeType.NORMAL:
                    continue
                edges_by_source.setdefault(edge.source, []).append(edge)

            def _next_node(node_id: str) -> Optional[str]:
                edges = edges_by_source.get(node_id, [])
                if len(edges) > 1:
                    raise ValueError(f"Google ADK flow expects a linear path. Multiple edges from {node_id}.")
                if not edges:
                    return None
                return edges[0].target

            ordered_agent_nodes: List[str] = []
            visited = set()
            current = entry_point
            if current == "START":
                current = _next_node(current)

            while current and current != "END":
                if current in visited:
                    raise ValueError("Cycle detected in Google ADK flow")
                visited.add(current)
                node = node_configs.get(current)
                if not node:
                    raise ValueError(f"Node '{current}' not found")
                if node.type != GraphNodeType.AGENT:
                    raise ValueError("Google ADK flow supports agent nodes only")
                if not node.agent_id:
                    raise ValueError(f"Agent node '{current}' missing agent_id")
                ordered_agent_nodes.append(node.agent_id)
                current = _next_node(current)

            if not ordered_agent_nodes:
                raise ValueError("No agent nodes found for Google ADK flow")

            tools_cache: Dict[str, List[Any]] = {}

            def build_tools(tool_names: List[str]) -> List[Any]:
                tool_funcs: List[Any] = []
                for tool_name in tool_names:
                    if tool_name in tools_cache:
                        tool_funcs.extend(tools_cache[tool_name])
                        continue

                    tool_config = YAMLService.load_tool(tool_name)
                    if not tool_config:
                        continue

                    async def tool_func(tool_name_arg=tool_name, **kwargs):
                        result = await ToolService.execute_tool(tool_name_arg, kwargs, llm_override)
                        if result.success:
                            return result.result
                        return {"error": result.error}

                    tool_func.__name__ = tool_name
                    tool_func.__doc__ = tool_config.description
                    tool_funcs.append(tool_func)
                    tools_cache[tool_name] = [tool_func]

                return tool_funcs

            sub_agents = []
            for agent_name in ordered_agent_nodes:
                agent_config = YAMLService.load_agent(agent_name)
                if not agent_config:
                    raise ValueError(f"Agent '{agent_name}' not found")

                if agent_config.llm_config.api_key:
                    os.environ["GOOGLE_API_KEY"] = agent_config.llm_config.api_key

                tools = build_tools(agent_config.tools)

                sub_agents.append(
                    LlmAgent(
                        name=agent_config.name,
                        model=agent_config.llm_config.model,
                        instruction=agent_config.system_prompt,
                        description=agent_config.description,
                        tools=tools,
                    )
                )

            root_agent = SequentialAgent(
                name=graph_config.name,
                sub_agents=sub_agents,
                description=graph_config.description or "Google ADK flow",
            )

            app_name = graph_config.metadata.get("app_name", graph_config.id)
            user_id = graph_config.metadata.get("user_id", "local-user")
            session_id = graph_config.metadata.get("session_id", "local-session")

            session_service = InMemorySessionService()
            await session_service.create_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
            )

            runner = Runner(agent=root_agent, app_name=app_name, session_service=session_service)

            user_message = input_data.get("message") or input_data.get("prompt")
            if not user_message:
                user_message = json.dumps(input_data) if input_data else "Hello"

            content = types.Content(role="user", parts=[types.Part(text=str(user_message))])
            events = runner.run_async(user_id=user_id, session_id=session_id, new_message=content)

            steps: List[Dict[str, Any]] = []
            final_output = ""
            async for event in events:
                step: Dict[str, Any] = {"type": "adk_event"}
                event_type = getattr(event, "type", None)
                if event_type is not None:
                    step["event_type"] = event_type

                content_text = None
                if getattr(event, "content", None) is not None and getattr(event.content, "parts", None):
                    part = event.content.parts[0]
                    content_text = getattr(part, "text", None)

                if content_text:
                    step["content"] = content_text

                steps.append(step)

                if hasattr(event, "is_final_response") and event.is_final_response():
                    final_output = content_text or ""

            return GraphExecutionResponse(
                graph_id=graph_config.id,
                success=True,
                output={"response": final_output},
                steps=steps,
                error=None,
                execution_time=time.time() - start_time,
            )
        except Exception as exc:
            GraphService.logger.error("Google ADK flow execution failed: %s", exc)
            return GraphExecutionResponse(
                graph_id=graph_config.id,
                success=False,
                output={},
                steps=[],
                error=str(exc),
                execution_time=time.time() - start_time,
            )

