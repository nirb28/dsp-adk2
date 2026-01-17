# Agent Development Kit (ADK) v2

A simple base agent development framework with YAML-based configurations, environment variable support, and REST APIs for managing and executing AI agents and tools.

## Features

- **YAML-Based Configuration**: Define agents and tools using simple YAML files
- **Environment Variable Support**: Use `.env` file for sensitive configuration (API keys, LLM settings)
- **Multiple Tool Types**: Support for function-based, API-based, and Python code-based tools
- **LangGraph Integration**: Build agents using LangGraph framework
- **REST API**: Complete admin and execution APIs
- **Basic Tools Included**: Text processing, HTTP requests, calculator, and more

## Project Structure

```
dsp-adk2/
├── app/
│   ├── api/
│   │   ├── admin.py          # Admin CRUD endpoints
│   │   └── execution.py      # Tool/agent execution endpoints
│   ├── services/
│   │   ├── agent_service.py  # Agent execution logic
│   │   ├── llm_service.py    # LLM provider integration
│   │   ├── tool_service.py   # Tool execution logic
│   │   └── yaml_service.py   # YAML config management
│   ├── tools/
│   │   └── basic_tools.py    # Built-in tools
│   ├── config.py             # Application settings
│   ├── models.py             # Pydantic models
│   └── main.py               # FastAPI application
├── data/
│   ├── agents/               # Agent YAML configurations
│   └── tools/                # Tool YAML configurations
├── .env.example              # Example environment variables
├── requirements.txt          # Python dependencies
├── run.py                    # Application entry point
└── README.md                 # This file
```
**Get a specific agent:**
```bash
GET http://localhost:8200/admin/agents/simple_assistant
```

### Execution API - Run Agents

```bash
POST http://localhost:8200/execute/agent
Content-Type: application/json

{
  "agent_name": "simple_assistant",
  "input": "Calculate the length of the text 'Hello World' and then multiply it by 5",
  "context": {}
}
```

Response:
```json
{
  "agent_name": "simple_assistant",
  "success": true,
  "output": "The text 'Hello World' has 11 characters. Multiplied by 5, that equals 55.",
  "steps": [
    {
      "type": "reasoning",
      "content": "I'll help you with that calculation..."
    },
    {
      "type": "tool_execution",
      "tool_name": "text_length",
      "success": true
    }
  ],
  "error": null,
  "execution_time": 2.5
}
```

## Tool Types

### 1. Function-Based Tools

Execute Python functions from your codebase:

```yaml
name: text_length
description: Calculate text length
type: function
module_path: app.tools.basic_tools
function_name: text_length
parameters:
  - name: text
    type: string
    description: The text to analyze
    required: true
```

### 2. API-Based Tools

Make HTTP requests to external APIs:

```yaml
name: weather_api
description: Get weather information
type: api
api_endpoint: https://wttr.in/${city}
api_method: GET
parameters:
  - name: city
    type: string
    description: City name
    required: true
```

### 3. Python Code Tools

Execute inline Python code:

```yaml
name: custom_processor
description: Custom data processing
type: python
python_code: |
  result = parameters['value'] * 2
parameters:
  - name: value
    type: number
    description: Input value
    required: true
```

## Agent Configuration

Agents are defined in YAML with LLM configuration and tool assignments:

```yaml
name: simple_assistant
description: A helpful AI assistant
llm_config:
  provider: ${LLM_PROVIDER}
  model: ${LLM_MODEL}
  api_key: ${LLM_API_KEY}
  temperature: 0.7
  max_tokens: 2000
system_prompt: |
  You are a helpful AI assistant...
tools:
  - text_length
  - calculator
max_iterations: 5
framework: langgraph
```

## Environment Variables

All YAML configurations support environment variable substitution using `${VARIABLE_NAME}` syntax:

```yaml
llm_config:
  provider: ${LLM_PROVIDER}      # Resolves from .env
  api_key: ${LLM_API_KEY}        # Resolves from .env
  model: ${LLM_MODEL}            # Resolves from .env
```

## Built-in Tools

The framework includes several built-in tools:

- **text_length**: Calculate text statistics (characters, words, lines)
- **text_uppercase**: Convert text to uppercase
- **text_lowercase**: Convert text to lowercase
- **calculator**: Evaluate mathematical expressions
- **http_get**: Make HTTP GET requests
- **http_post**: Make HTTP POST requests
- **json_parse**: Parse JSON strings
- **json_stringify**: Convert data to JSON

## LLM Provider Support

Supported LLM providers:

- **OpenAI**: GPT-4, GPT-3.5-turbo, etc.
- **Groq**: Llama, Mixtral models
- **NVIDIA**: NVIDIA AI Endpoints
- **OpenAI-Compatible**: Any OpenAI-compatible API

Configure in `.env`:

```env
# OpenAI
LLM_PROVIDER=openai
LLM_MODEL=gpt-4
LLM_API_KEY=sk-...

# Groq
LLM_PROVIDER=groq
LLM_MODEL=llama3-70b-8192
GROQ_API_KEY=gsk_...

# NVIDIA
LLM_PROVIDER=nvidia
LLM_MODEL=meta/llama-3.3-70b-instruct
NVIDIA_API_KEY=nvapi-...
```

## API Endpoints

### Admin Endpoints

- `GET /admin/tools` - List all tools
- `GET /admin/tools/{tool_name}` - Get tool details
- `POST /admin/tools` - Create new tool
- `PUT /admin/tools/{tool_name}` - Update tool
- `DELETE /admin/tools/{tool_name}` - Delete tool
- `GET /admin/tools/{tool_name}/schema` - Get OpenAI function schema

- `GET /admin/agents` - List all agents
- `GET /admin/agents/{agent_name}` - Get agent details
- `POST /admin/agents` - Create new agent
- `PUT /admin/agents/{agent_name}` - Update agent
- `DELETE /admin/agents/{agent_name}` - Delete agent

### Execution Endpoints

- `POST /execute/tool` - Execute a tool
- `POST /execute/agent` - Execute an agent

### System Endpoints

- `GET /` - API information
- `GET /health` - Health check
- `GET /docs` - Swagger documentation
- `GET /redoc` - ReDoc documentation

## Development

### Adding New Tools

1. Create a Python function in `app/tools/basic_tools.py` or your own module
2. Create a YAML configuration in `data/tools/`
3. The tool will be automatically available via API

Example:

```python
# app/tools/basic_tools.py
def my_custom_tool(param1: str, param2: int) -> dict:
    return {"result": f"{param1} - {param2}"}
```

```yaml
# data/tools/my_custom_tool.yaml
name: my_custom_tool
description: My custom tool
type: function
module_path: app.tools.basic_tools
function_name: my_custom_tool
parameters:
  - name: param1
    type: string
    description: First parameter
    required: true
  - name: param2
    type: number
    description: Second parameter
    required: true
```

### Creating New Agents

1. Create a YAML file in `data/agents/`
2. Configure LLM settings and assign tools
3. The agent will be automatically available via API

## Testing

Test the API using the interactive documentation at `http://localhost:8200/docs` or use curl/Postman.

Example test:

```bash
# Test tool execution
curl -X POST http://localhost:8200/execute/tool \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "calculator", "parameters": {"expression": "10 * 5"}}'

# Test agent execution
curl -X POST http://localhost:8200/execute/agent \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "simple_assistant", "input": "What is 25 + 17?"}'
```
