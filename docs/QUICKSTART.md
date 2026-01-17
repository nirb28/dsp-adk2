# ADK Quick Start Guide
## Step 1: Setup Environment

```bash
# Navigate to project
cd dsp-adk2

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

```bash
python run.py
```

You should see:
```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8200
```

### Test Tool Execution

```bash
curl -X POST http://localhost:8200/execute/tool \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "calculator",
    "parameters": {
      "expression": "10 * 5 + 2"
    }
  }'
```

Expected response:
```json
{
  "tool_name": "calculator",
  "success": true,
  "result": {
    "result": 52,
    "expression": "10 * 5 + 2"
  },
  "error": null,
  "execution_time": 0.001
}
```

### Test Agent Execution

```bash
curl -X POST http://localhost:8200/execute/agent \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "simple_assistant",
    "input": "Calculate 25 + 17 and tell me the result"
  }'
```

## Step 5: Explore Available Resources

### List Tools
```bash
curl http://localhost:8200/admin/tools
```

### List Agents
```bash
curl http://localhost:8200/admin/agents
```

### Get Tool Details
```bash
curl http://localhost:8200/admin/tools/calculator
```

## Next Steps

1. **Create Custom Tools**: Add new YAML files in `data/tools/`
2. **Create Custom Agents**: Add new YAML files in `data/agents/`
3. **Add Python Functions**: Extend `app/tools/basic_tools.py`
4. **Explore API**: Visit `http://localhost:8200/docs` for full API documentation

### Create a New Tool via API

```bash
curl -X POST http://localhost:8200/admin/tools \
  -H "Content-Type: application/json" \
  -d '{
    "name": "text_uppercase",
    "description": "Convert text to uppercase",
    "type": "function",
    "module_path": "app.tools.basic_tools",
    "function_name": "text_uppercase",
    "parameters": [
      {
        "name": "text",
        "type": "string",
        "description": "Text to convert",
        "required": true
      }
    ]
  }'
```

### Execute Your New Tool

```bash
curl -X POST http://localhost:8200/execute/tool \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "text_uppercase",
    "parameters": {
      "text": "hello world"
    }
  }'
```

