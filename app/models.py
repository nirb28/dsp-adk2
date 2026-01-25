from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any, Literal
from enum import Enum


class ToolType(str, Enum):
    FUNCTION = "function"
    API = "api"
    PYTHON = "python"


class LLMConfig(BaseModel):
    provider: str = Field(description="LLM provider (openai, groq, anthropic, etc.)")
    model: str = Field(description="Model name")
    api_key: Optional[str] = Field(default=None, description="API key (can use env var)")
    base_url: Optional[str] = Field(default=None, description="Base URL for API")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2000, ge=1)
    additional_params: Dict[str, Any] = Field(default_factory=dict)
    send_additional_params: Optional[bool] = Field(default=None)
    request_param_allowlist: Optional[str] = Field(default=None)
    request_param_denylist: Optional[str] = Field(default=None)
    request_param_rename: Optional[str] = Field(default=None)


class LLMOverride(BaseModel):
    provider: Optional[str] = Field(default=None, description="LLM provider override")
    model: Optional[str] = Field(default=None, description="Model override")
    api_key: Optional[str] = Field(default=None, description="API key override")
    base_url: Optional[str] = Field(default=None, description="Base URL override")
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    additional_params: Optional[Dict[str, Any]] = Field(default=None)
    send_additional_params: Optional[bool] = Field(default=None)
    request_param_allowlist: Optional[str] = Field(default=None)
    request_param_denylist: Optional[str] = Field(default=None)
    request_param_rename: Optional[str] = Field(default=None)


class ToolParameter(BaseModel):
    name: str
    type: str = Field(description="Parameter type (string, number, boolean, object, array)")
    description: str
    required: bool = Field(default=True)
    default: Optional[Any] = Field(default=None)
    enum: Optional[List[Any]] = Field(default=None)


class ToolConfig(BaseModel):
    name: str = Field(description="Unique tool name")
    description: str = Field(description="Tool description for LLM")
    type: ToolType = Field(description="Tool type")
    parameters: List[ToolParameter] = Field(default_factory=list)
    
    function_name: Optional[str] = Field(default=None, description="Python function name for FUNCTION type")
    module_path: Optional[str] = Field(default=None, description="Python module path for FUNCTION type")
    
    api_endpoint: Optional[str] = Field(default=None, description="API endpoint URL for API type")
    api_method: Optional[str] = Field(default="GET", description="HTTP method for API type")
    api_headers: Optional[Dict[str, str]] = Field(default=None, description="HTTP headers for API type")
    
    python_code: Optional[str] = Field(default=None, description="Python code for PYTHON type")
    
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentConfig(BaseModel):
    name: str = Field(description="Unique agent name")
    description: str = Field(description="Agent description")
    llm_config: LLMConfig = Field(description="LLM configuration for this agent")
    system_prompt: str = Field(description="System prompt for the agent")
    tools: List[str] = Field(default_factory=list, description="List of tool names available to agent")
    max_iterations: int = Field(default=10, ge=1, description="Maximum reasoning iterations")
    framework: Literal["langgraph", "google_adk"] = Field(default="langgraph")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphType(str, Enum):
    LANGGRAPH = "langgraph"
    GOOGLE_ADK = "google_adk"


class GraphNodeType(str, Enum):
    START = "start"
    END = "end"
    AGENT = "agent"
    TOOL = "tool"
    CUSTOM = "custom"


class GraphEdgeType(str, Enum):
    NORMAL = "normal"
    CONDITIONAL = "conditional"


class GraphNode(BaseModel):
    id: str = Field(description="Unique node identifier")
    name: str = Field(description="Human-readable node name")
    type: GraphNodeType = Field(default=GraphNodeType.AGENT)
    agent_id: Optional[str] = Field(default=None, description="Agent ID for agent nodes")
    tool_id: Optional[str] = Field(default=None, description="Tool ID for tool nodes")
    input_mapping: Dict[str, Any] = Field(default_factory=dict, description="Input mapping for node execution")
    output_mapping: Dict[str, Any] = Field(default_factory=dict, description="Output mapping for node execution")
    config: Dict[str, Any] = Field(default_factory=dict, description="Node-specific configuration")
    routes: Dict[str, str] = Field(default_factory=dict, description="Routing rules for conditional nodes")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str = Field(description="Unique edge identifier")
    source: str = Field(description="Source node ID")
    target: str = Field(description="Target node ID")
    type: GraphEdgeType = Field(default=GraphEdgeType.NORMAL)
    condition: Optional[str] = Field(default=None, description="Condition expression for conditional edges")
    condition_value: Optional[Any] = Field(default=None, description="Optional match value for conditional edges")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphConfig(BaseModel):
    id: str = Field(description="Unique graph identifier")
    name: str = Field(description="Human-readable graph name")
    description: Optional[str] = Field(default=None)
    type: GraphType = Field(default=GraphType.LANGGRAPH)
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    entry_point: Optional[str] = Field(default=None)
    max_iterations: int = Field(default=25, ge=1)
    timeout: int = Field(default=300, ge=1)
    streaming: bool = Field(default=True)
    agents: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GraphExecutionRequest(BaseModel):
    graph_id: str
    input: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    llm_override: Optional[LLMOverride] = None


class GraphExecutionResponse(BaseModel):
    graph_id: str
    success: bool
    output: Dict[str, Any] = Field(default_factory=dict)
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    execution_time: float


class ToolExecutionRequest(BaseModel):
    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    llm_override: Optional[LLMOverride] = None


class ToolExecutionResponse(BaseModel):
    tool_name: str
    success: bool
    result: Any
    error: Optional[str] = None
    execution_time: float


class AgentExecutionRequest(BaseModel):
    agent_name: str
    input: str
    context: Dict[str, Any] = Field(default_factory=dict)
    stream: bool = Field(default=False)
    llm_override: Optional[LLMOverride] = None


class AgentExecutionResponse(BaseModel):
    agent_name: str
    success: bool
    output: str
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    execution_time: float
