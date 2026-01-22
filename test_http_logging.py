"""Test script to verify OpenAI HTTP payload logging."""
import asyncio
import logging
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings
from app.models import AgentConfig, LLMConfig
from app.services.llm_service import LLMService

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True
)

async def test_openai_http_logging():
    """Test OpenAI HTTP payload logging."""
    print("=" * 80)
    print("Testing OpenAI HTTP Payload Logging")
    print(f"DEBUG_TRACE setting: {settings.debug_trace}")
    print(f"LOG_LEVEL setting: {settings.log_level}")
    print("=" * 80)
    
    # Create OpenAI LLM config
    llm_config = LLMConfig(
        provider="openai",
        model="gpt-3.5-turbo",
        api_key=settings.llm_api_key or "test-key",
        base_url=settings.llm_base_url,
        temperature=0.7,
        max_tokens=100,
    )
    
    print("\n[1] Testing LLMService.invoke() with OpenAI provider...")
    try:
        response = LLMService.invoke(
            llm_config,
            system_prompt="You are a helpful assistant.",
            user_message="Say hello in one sentence."
        )
        print(f"Response: {response[:100]}...")
    except Exception as e:
        print(f"Error (expected if no valid API key): {e}")
    
    print("\n" + "=" * 80)
    print("Test completed. Check logs above for:")
    print("  - 'OpenAI HTTP payload logging enabled'")
    print("  - 'OpenAI HTTP Request Payload: {...}'")
    print("  - 'OpenAI HTTP Response Payload: {...}'")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_openai_http_logging())
