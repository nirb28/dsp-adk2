"""Debug test with full logging enabled."""
import asyncio
import os
import logging

# Set DEBUG logging before importing anything else
os.environ['LOG_LEVEL'] = 'DEBUG'
os.environ['DEBUG_TRACE'] = 'true'

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True
)

from app.services.agent_service import AgentService

async def test_agent():
    print("\n" + "="*80)
    print("STARTING AGENT EXECUTION TEST WITH FULL DEBUG LOGGING")
    print("="*80 + "\n")
    
    result = await AgentService.execute_agent(
        'simple_assistant', 
        'Calculate the length of the text "Hello World" and then multiply it by 5'
    )
    
    print("\n" + "="*80)
    print("AGENT EXECUTION RESULT")
    print("="*80)
    print(f'Success: {result.success}')
    print(f'Output: {result.output}')
    print(f'Error: {result.error}')
    print(f'Steps: {len(result.steps)}')
    for i, step in enumerate(result.steps):
        print(f'  Step {i+1}: {step.get("type")} - {step.get("content", step.get("tool_name"))}')
    print("="*80 + "\n")

if __name__ == '__main__':
    asyncio.run(test_agent())
