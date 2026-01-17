import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root():
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data


def test_health():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_list_tools():
    """Test listing tools."""
    response = client.get("/admin/tools")
    assert response.status_code == 200
    tools = response.json()
    assert isinstance(tools, list)


def test_list_agents():
    """Test listing agents."""
    response = client.get("/admin/agents")
    assert response.status_code == 200
    agents = response.json()
    assert isinstance(agents, list)


@pytest.mark.asyncio
async def test_execute_calculator_tool():
    """Test executing calculator tool."""
    response = client.post(
        "/execute/tool",
        json={
            "tool_name": "calculator",
            "parameters": {
                "expression": "2 + 2"
            }
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["result"]["result"] == 4


def test_get_tool_schema():
    """Test getting tool schema."""
    response = client.get("/admin/tools/calculator/schema")
    assert response.status_code == 200
    schema = response.json()
    assert "type" in schema
    assert schema["type"] == "function"
