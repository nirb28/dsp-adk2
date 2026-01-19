import yaml
import os
from typing import Dict, List, Optional
from pathlib import Path
import re
from app.config import settings
from app.models import ToolConfig, AgentConfig, GraphConfig


class YAMLService:
    
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
        tool_path = Path(settings.tools_dir) / f"{tool_name}.yaml"
        if not tool_path.exists():
            return None
        
        with open(tool_path, 'r') as f:
            data = yaml.safe_load(f)
        
        resolved_data = YAMLService.resolve_env_vars(data)
        return ToolConfig(**resolved_data)
    
    @staticmethod
    def save_tool(tool: ToolConfig) -> None:
        """Save a tool configuration to YAML file."""
        tool_path = Path(settings.tools_dir) / f"{tool.name}.yaml"
        with open(tool_path, 'w') as f:
            yaml.dump(tool.model_dump(exclude_none=True), f, default_flow_style=False)
    
    @staticmethod
    def delete_tool(tool_name: str) -> bool:
        """Delete a tool configuration file."""
        tool_path = Path(settings.tools_dir) / f"{tool_name}.yaml"
        if tool_path.exists():
            tool_path.unlink()
            return True
        return False
    
    @staticmethod
    def list_tools() -> List[str]:
        """List all available tool names."""
        tools_path = Path(settings.tools_dir)
        if not tools_path.exists():
            return []
        return [f.stem for f in tools_path.glob("*.yaml")]
    
    @staticmethod
    def load_agent(agent_name: str) -> Optional[AgentConfig]:
        """Load an agent configuration from YAML file."""
        agent_path = Path(settings.agents_dir) / f"{agent_name}.yaml"
        if not agent_path.exists():
            return None
        
        with open(agent_path, 'r') as f:
            data = yaml.safe_load(f)
        
        resolved_data = YAMLService.resolve_env_vars(data)
        return AgentConfig(**resolved_data)
    
    @staticmethod
    def save_agent(agent: AgentConfig) -> None:
        """Save an agent configuration to YAML file."""
        agent_path = Path(settings.agents_dir) / f"{agent.name}.yaml"
        with open(agent_path, 'w') as f:
            yaml.dump(agent.model_dump(exclude_none=True), f, default_flow_style=False)
    
    @staticmethod
    def delete_agent(agent_name: str) -> bool:
        """Delete an agent configuration file."""
        agent_path = Path(settings.agents_dir) / f"{agent_name}.yaml"
        if agent_path.exists():
            agent_path.unlink()
            return True
        return False
    
    @staticmethod
    def list_agents() -> List[str]:
        """List all available agent names."""
        agents_path = Path(settings.agents_dir)
        if not agents_path.exists():
            return []
        return [f.stem for f in agents_path.glob("*.yaml")]

    @staticmethod
    def load_graph(graph_id: str) -> Optional[GraphConfig]:
        """Load a graph configuration from YAML file."""
        graph_path = Path(settings.graphs_dir) / f"{graph_id}.yaml"
        if not graph_path.exists():
            return None

        with open(graph_path, "r") as f:
            data = yaml.safe_load(f)

        resolved_data = YAMLService.resolve_env_vars(data)
        return GraphConfig(**resolved_data)

    @staticmethod
    def save_graph(graph: GraphConfig) -> None:
        """Save a graph configuration to YAML file."""
        graph_path = Path(settings.graphs_dir) / f"{graph.id}.yaml"
        with open(graph_path, "w") as f:
            yaml.dump(graph.model_dump(exclude_none=True), f, default_flow_style=False)

    @staticmethod
    def delete_graph(graph_id: str) -> bool:
        """Delete a graph configuration file."""
        graph_path = Path(settings.graphs_dir) / f"{graph_id}.yaml"
        if graph_path.exists():
            graph_path.unlink()
            return True
        return False

    @staticmethod
    def list_graphs() -> List[str]:
        """List all available graph IDs."""
        graphs_path = Path(settings.graphs_dir)
        if not graphs_path.exists():
            return []
        return [f.stem for f in graphs_path.glob("*.yaml")]
