import importlib
import time
import httpx
import json
import logging
from typing import Dict, Any, Optional
from app.models import ToolConfig, ToolType, ToolExecutionResponse, LLMOverride, LLMConfig
from app.services.yaml_service import YAMLService
from app.config import settings


class ToolService:

    logger = logging.getLogger(__name__)
    
    @staticmethod
    async def execute_tool(
        tool_name: str,
        parameters: Dict[str, Any],
        llm_override: Optional[LLMOverride] = None,
        llm_config: Optional[LLMConfig] = None,
    ) -> ToolExecutionResponse:
        """Execute a tool by name with given parameters."""
        start_time = time.time()

        normalized_parameters = dict(parameters)
        nested_kwargs = normalized_parameters.pop("kwargs", None)
        if isinstance(nested_kwargs, dict):
            normalized_parameters = {**nested_kwargs, **normalized_parameters}
        
        ToolService.logger.debug(f"Executing tool: {tool_name}")

        if settings.debug_trace:
            ToolService.logger.debug(
                "Tool request: %s",
                json.dumps({"tool_name": tool_name, "parameters": normalized_parameters}, default=str)
            )
        
        tool_config = YAMLService.load_tool(tool_name)
        if not tool_config:
            ToolService.logger.warning(f"Tool not found: {tool_name}")
            return ToolExecutionResponse(
                tool_name=tool_name,
                success=False,
                result=None,
                error=f"Tool '{tool_name}' not found",
                execution_time=time.time() - start_time
            )
        
        try:
            ToolService.logger.debug(f"Tool type: {tool_config.type}")
            if tool_config.type == ToolType.FUNCTION:
                result = await ToolService._execute_function_tool(
                    tool_config,
                    normalized_parameters,
                    llm_override,
                    llm_config,
                )
            elif tool_config.type == ToolType.API:
                result = await ToolService._execute_api_tool(tool_config, normalized_parameters)
            elif tool_config.type == ToolType.PYTHON:
                result = await ToolService._execute_python_tool(
                    tool_config,
                    normalized_parameters,
                    llm_override,
                    llm_config,
                )
            else:
                raise ValueError(f"Unsupported tool type: {tool_config.type}")
            
            execution_time = time.time() - start_time
            ToolService.logger.debug(f"Tool executed successfully: {tool_name} (took {execution_time:.3f}s)")
            
            if settings.debug_trace:
                ToolService.logger.debug(
                    "Tool response: %s",
                    json.dumps(
                        {
                            "tool_name": tool_name,
                            "result": result,
                            "execution_time": execution_time,
                        },
                        default=str,
                    ),
                )

            return ToolExecutionResponse(
                tool_name=tool_name,
                success=True,
                result=result,
                error=None,
                execution_time=time.time() - start_time
            )
        except Exception as e:
            ToolService.logger.error(f"Tool execution failed: {tool_name} - {str(e)}")
            if settings.debug_trace:
                ToolService.logger.debug(
                    "Tool error: %s",
                    json.dumps({"tool_name": tool_name, "error": str(e)}, default=str)
                )
            return ToolExecutionResponse(
                tool_name=tool_name,
                success=False,
                result=None,
                error=str(e),
                execution_time=time.time() - start_time
            )
    
    @staticmethod
    async def _execute_function_tool(
        tool_config: ToolConfig,
        parameters: Dict[str, Any],
        llm_override: Optional[LLMOverride] = None,
        llm_config: Optional[LLMConfig] = None,
    ) -> Any:
        """Execute a function-based tool."""
        if not tool_config.module_path or not tool_config.function_name:
            raise ValueError("Function tool requires module_path and function_name")
        
        module = importlib.import_module(tool_config.module_path)
        func = getattr(module, tool_config.function_name)
        
        import inspect
        enriched_params = dict(parameters)
        signature = inspect.signature(func)
        accepts_kwargs = any(
            param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()
        )
        if llm_override is not None and "llm_override" not in enriched_params:
            if "llm_override" in signature.parameters or accepts_kwargs:
                enriched_params["llm_override"] = llm_override
        if llm_config is not None and "llm_config" not in enriched_params:
            if "llm_config" in signature.parameters or accepts_kwargs:
                enriched_params["llm_config"] = llm_config

        if inspect.iscoroutinefunction(func):
            return await func(**enriched_params)
        else:
            return func(**enriched_params)
    
    @staticmethod
    async def _execute_api_tool(tool_config: ToolConfig, parameters: Dict[str, Any]) -> Any:
        """Execute an API-based tool."""
        if not tool_config.api_endpoint:
            raise ValueError("API tool requires api_endpoint")
        
        method = (tool_config.api_method or "GET").upper()
        headers = tool_config.api_headers or {}
        
        async with httpx.AsyncClient(verify=settings.ssl_verify) as client:
            if method == "GET":
                response = await client.get(
                    tool_config.api_endpoint,
                    params=parameters,
                    headers=headers,
                    timeout=30.0
                )
            elif method == "POST":
                response = await client.post(
                    tool_config.api_endpoint,
                    json=parameters,
                    headers=headers,
                    timeout=30.0
                )
            elif method == "PUT":
                response = await client.put(
                    tool_config.api_endpoint,
                    json=parameters,
                    headers=headers,
                    timeout=30.0
                )
            elif method == "DELETE":
                response = await client.delete(
                    tool_config.api_endpoint,
                    params=parameters,
                    headers=headers,
                    timeout=30.0
                )
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            
            if response.headers.get("content-type", "").startswith("application/json"):
                return response.json()
            else:
                return response.text
    
    @staticmethod
    async def _execute_python_tool(
        tool_config: ToolConfig,
        parameters: Dict[str, Any],
        llm_override: Optional[LLMOverride] = None,
        llm_config: Optional[LLMConfig] = None,
    ) -> Any:
        """Execute a Python code-based tool."""
        if not tool_config.python_code:
            raise ValueError("Python tool requires python_code")

        enriched_params = dict(parameters)
        if llm_override is not None and "llm_override" not in enriched_params:
            enriched_params["llm_override"] = llm_override
        if llm_config is not None and "llm_config" not in enriched_params:
            enriched_params["llm_config"] = llm_config

        local_vars = {
            "parameters": enriched_params,
            "llm_override": llm_override,
            "llm_config": llm_config,
        }
        exec(tool_config.python_code, {}, local_vars)
        
        if "result" in local_vars:
            return local_vars["result"]
        else:
            raise ValueError("Python tool must set 'result' variable")
    
    @staticmethod
    def get_tool_schema(tool_config: ToolConfig) -> Dict[str, Any]:
        """Convert tool config to OpenAI function calling schema."""
        properties = {}
        required = []
        
        for param in tool_config.parameters:
            prop = {
                "type": param.type,
                "description": param.description
            }
            if param.type == "array":
                prop["items"] = {"type": "object"}
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            
            properties[param.name] = prop
            
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": tool_config.name,
                "description": tool_config.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }
