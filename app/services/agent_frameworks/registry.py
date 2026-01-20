from __future__ import annotations

from typing import Dict

from app.services.agent_frameworks.base import AgentFramework


class FrameworkRegistry:
    def __init__(self) -> None:
        self._frameworks: Dict[str, AgentFramework] = {}

    def register(self, framework: AgentFramework) -> None:
        self._frameworks[framework.name] = framework

    def get(self, name: str) -> AgentFramework:
        if name not in self._frameworks:
            raise ValueError(f"Unsupported framework: {name}")
        return self._frameworks[name]


framework_registry = FrameworkRegistry()
