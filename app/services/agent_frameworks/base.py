from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple, Optional

from app.models import AgentConfig, LLMOverride


class AgentFramework(ABC):
    name: str

    @abstractmethod
    async def execute(
        self,
        agent_config: AgentConfig,
        user_input: str,
        context: Dict[str, Any],
        llm_override: Optional[LLMOverride] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Execute the agent and return output plus step metadata."""
