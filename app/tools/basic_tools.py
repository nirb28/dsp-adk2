import httpx
import json
from typing import Dict, Any


def text_length(text: str) -> Dict[str, Any]:
    """Calculate the length of text."""
    return {
        "length": len(text),
        "words": len(text.split()),
        "lines": len(text.splitlines())
    }


def text_uppercase(text: str) -> str:
    """Convert text to uppercase."""
    return text.upper()


def text_lowercase(text: str) -> str:
    """Convert text to lowercase."""
    return text.lower()


def text_reverse(text: str) -> str:
    """Reverse the text."""
    return text[::-1]


def calculator(expression: str) -> Dict[str, Any]:
    """Evaluate a mathematical expression safely."""
    try:
        allowed_chars = set("0123456789+-*/(). ")
        if not all(c in allowed_chars for c in expression):
            return {"error": "Invalid characters in expression"}
        
        result = eval(expression, {"__builtins__": {}}, {})
        return {"result": result, "expression": expression}
    except Exception as e:
        return {"error": str(e)}


async def http_get(url: str, headers: Dict[str, str] = None) -> Dict[str, Any]:
    """Make an HTTP GET request."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers or {}, timeout=30.0)
            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.text,
                "json": response.json() if response.headers.get("content-type", "").startswith("application/json") else None
            }
    except Exception as e:
        return {"error": str(e)}


async def http_post(url: str, data: Dict[str, Any] = None, headers: Dict[str, str] = None) -> Dict[str, Any]:
    """Make an HTTP POST request."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, 
                json=data or {}, 
                headers=headers or {}, 
                timeout=30.0
            )
            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.text,
                "json": response.json() if response.headers.get("content-type", "").startswith("application/json") else None
            }
    except Exception as e:
        return {"error": str(e)}


def json_parse(json_string: str) -> Dict[str, Any]:
    """Parse a JSON string."""
    try:
        return {"result": json.loads(json_string)}
    except Exception as e:
        return {"error": str(e)}


def json_stringify(data: Dict[str, Any], indent: int = 2) -> str:
    """Convert data to JSON string."""
    try:
        return json.dumps(data, indent=indent)
    except Exception as e:
        return json.dumps({"error": str(e)})


def truncate_text(text: str, max_chars: int = 2000, suffix: str = "...") -> Dict[str, Any]:
    """Truncate text to a maximum number of characters."""
    if max_chars < 1:
        return {"error": "max_chars must be >= 1"}

    if len(text) <= max_chars:
        return {"result": text, "truncated": False, "original_length": len(text)}

    trimmed = text[: max_chars - len(suffix)] + suffix if len(suffix) < max_chars else text[:max_chars]
    return {
        "result": trimmed,
        "truncated": True,
        "original_length": len(text),
        "final_length": len(trimmed),
    }
