import yaml
import os
from typing import Dict, List, Optional
from pathlib import Path
import re
from app.config import settings
from app.models import ToolConfig, AgentConfig, GraphConfig


class YAMLService:
    
    @staticmethod
    def _resolve_yaml_path(base_dir: str, item_name: str) -> Path:
        base_path = Path(base_dir)
        direct_path = base_path / f"{item_name}.yaml"
        if direct_path.exists():
            return direct_path

        nested_matches = sorted(base_path.rglob(f"{item_name}.yaml"))
        if nested_matches:
            return nested_matches[0]

        return direct_path

    @staticmethod
    def _list_yaml_names(base_dir: str) -> List[str]:
        base_path = Path(base_dir)
        if not base_path.exists():
            return []
        return sorted(f.stem for f in base_path.rglob("*.yaml"))
    
    @staticmethod
    def resolve_env_vars(data: Dict) -> Dict:
        """Recursively resolve environment variables in YAML data."""
        if isinstance(data, dict):
            return {k: YAMLService.resolve_env_vars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [YAMLService.resolve_env_vars(item) for item in data]
        elif isinstance(data, str):
            pattern = r'\$\{([^}]+)\}'
            matches = re.findall(pattern, data)
            result = data
            for match in matches:
                # First try os.getenv, then check settings object
                env_value = os.getenv(match)
                if env_value is None:
                    # Try to get from settings object (convert to lowercase for settings attribute)
                    settings_attr = match.lower()
                    env_value = getattr(settings, settings_attr, None)
                    if env_value is not None:
                        env_value = str(env_value)
                    else:
                        env_value = ""
                result = result.replace(f"${{{match}}}", env_value)
            return result
        return data
    
    @staticmethod
    def load_tool(tool_name: str) -> Optional[ToolConfig]:
        """Load a tool configuration from YAML file."""
        tool_path = YAMLService._resolve_yaml_path(settings.tools_dir, tool_name)
        if not tool_path.exists():
            return None
        
        with open(tool_path, 'r') as f:
            data = yaml.safe_load(f)
        
        resolved_data = YAMLService.resolve_env_vars(data)
        return ToolConfig(**resolved_data)
    
    @staticmethod
    def save_tool(tool: ToolConfig) -> None:
        """Save a tool configuration to YAML file."""
        tool_path = YAMLService._resolve_yaml_path(settings.tools_dir, tool.name)
        with open(tool_path, 'w') as f:
            yaml.dump(tool.model_dump(exclude_none=True), f, default_flow_style=False)
    
    @staticmethod
    def delete_tool(tool_name: str) -> bool:
        """Delete a tool configuration file."""
        tool_path = YAMLService._resolve_yaml_path(settings.tools_dir, tool_name)
        if tool_path.exists():
            tool_path.unlink()
            return True
        return False
    
    @staticmethod
    def list_tools() -> List[str]:
        """List all available tool names."""
        return YAMLService._list_yaml_names(settings.tools_dir)
    
    @staticmethod
    def load_agent(agent_name: str) -> Optional[AgentConfig]:
        """Load an agent configuration from YAML file."""
        agent_path = YAMLService._resolve_yaml_path(settings.agents_dir, agent_name)
        if not agent_path.exists():
            return None
        
        with open(agent_path, 'r') as f:
            data = yaml.safe_load(f)
        
        resolved_data = YAMLService.resolve_env_vars(data)
        return AgentConfig(**resolved_data)
    
    @staticmethod
    def save_agent(agent: AgentConfig) -> None:
        """Save an agent configuration to YAML file."""
        agent_path = YAMLService._resolve_yaml_path(settings.agents_dir, agent.name)
        with open(agent_path, 'w') as f:
            yaml.dump(agent.model_dump(exclude_none=True), f, default_flow_style=False)
    
    @staticmethod
    def delete_agent(agent_name: str) -> bool:
        """Delete an agent configuration file."""
        agent_path = YAMLService._resolve_yaml_path(settings.agents_dir, agent_name)
        if agent_path.exists():
            agent_path.unlink()
            return True
        return False
    
    @staticmethod
    def list_agents() -> List[str]:
        """List all available agent names."""
        return YAMLService._list_yaml_names(settings.agents_dir)

    @staticmethod
    def load_graph(graph_id: str) -> Optional[GraphConfig]:
        """Load a graph configuration from YAML file."""
        graph_path = YAMLService._resolve_yaml_path(settings.graphs_dir, graph_id)
        if not graph_path.exists():
            return None

        with open(graph_path, "r") as f:
            data = yaml.safe_load(f)

        resolved_data = YAMLService.resolve_env_vars(data)
        return GraphConfig(**resolved_data)

    @staticmethod
    def save_graph(graph: GraphConfig) -> None:
        """Save a graph configuration to YAML file."""
        graph_path = YAMLService._resolve_yaml_path(settings.graphs_dir, graph.id)
        with open(graph_path, "w") as f:
            yaml.dump(graph.model_dump(exclude_none=True), f, default_flow_style=False)

    @staticmethod
    def delete_graph(graph_id: str) -> bool:
        """Delete a graph configuration file."""
        graph_path = YAMLService._resolve_yaml_path(settings.graphs_dir, graph_id)
        if graph_path.exists():
            graph_path.unlink()
            return True
        return False

    @staticmethod
    def list_graphs() -> List[str]:
        """List all available graph IDs."""
        return YAMLService._list_yaml_names(settings.graphs_dir)
