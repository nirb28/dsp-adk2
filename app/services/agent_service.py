import time
import json
import logging
from typing import Dict, Any, Optional

from app.models import AgentExecutionResponse, LLMOverride
from app.services.yaml_service import YAMLService
from app.services.agent_frameworks import framework_registry
from app.services.llm_service import LLMService
from app.config import settings


class AgentService:

    logger = logging.getLogger(__name__)
    
    @staticmethod
    async def execute_agent(
        agent_name: str,
        user_input: str,
        context: Dict[str, Any] = None,
        llm_override: Optional[LLMOverride] = None,
        framework_override: Optional[str] = None,
    ) -> AgentExecutionResponse:
        """Execute an agent by name with given input."""
        start_time = time.time()
        context = context or {}
        
        AgentService.logger.debug(f"Executing agent: {agent_name}")

        if settings.debug_trace:
            AgentService.logger.debug(
                "Agent request: %s",
                json.dumps(
                    {"agent_name": agent_name, "input": user_input, "context": context},
                    default=str,
                ),
            )
        
        agent_config = YAMLService.load_agent(agent_name)
        if not agent_config:
            AgentService.logger.warning(f"Agent not found: {agent_name}")
            return AgentExecutionResponse(
                agent_name=agent_name,
                success=False,
                output="",
                steps=[],
                error=f"Agent '{agent_name}' not found",
                execution_time=time.time() - start_time
            )
        
        try:
            AgentService.logger.debug(f"Agent framework: {agent_config.framework}, tools: {agent_config.tools}")
            if llm_override:
                agent_config = agent_config.model_copy(
                    update={
                        "llm_config": LLMService.resolve_llm_config(
                            agent_config.llm_config,
                            llm_override,
                        )
                    }
                )
            selected_framework = framework_override or agent_config.framework
            framework = framework_registry.get(selected_framework)
            output, steps = await framework.execute(agent_config, user_input, context, llm_override)

            execution_time = time.time() - start_time
            AgentService.logger.debug(f"Agent executed successfully: {agent_name} (took {execution_time:.3f}s, {len(steps)} steps)")
            
            if settings.debug_trace:
                AgentService.logger.debug(
                    "Agent response: %s",
                    json.dumps(
                        {
                            "agent_name": agent_name,
                            "output": output,
                            "steps": steps,
                            "execution_time": execution_time,
                        },
                        default=str,
                    ),
                )
            
            return AgentExecutionResponse(
                agent_name=agent_name,
                success=True,
                output=output,
                steps=steps,
                error=None,
                execution_time=execution_time
            )
        except Exception as e:
            AgentService.logger.error(f"Agent execution failed: {agent_name} - {str(e)}")
            return AgentExecutionResponse(
                agent_name=agent_name,
                success=False,
                output="",
                steps=[],
                error=str(e),
                execution_time=time.time() - start_time
            )
    
