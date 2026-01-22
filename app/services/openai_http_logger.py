"""HTTP request/response logger for OpenAI API calls."""
import json
import logging
from typing import Any, Dict, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


logger = logging.getLogger(__name__)


class OpenAIHTTPLogger(BaseCallbackHandler):
    """Callback handler to log OpenAI HTTP requests and responses."""
    
    def __init__(self, enabled: bool = True):
        """Initialize the logger.
        
        Args:
            enabled: Whether logging is enabled
        """
        self.enabled = enabled
        self.request_data: Optional[Dict[str, Any]] = None
    
    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: list[str], **kwargs: Any
    ) -> None:
        """Log when LLM starts processing."""
        if not self.enabled:
            return
        
        # Extract invocation params which contain the HTTP request details
        invocation_params = kwargs.get("invocation_params", {})
        
        # Build the request payload that will be sent to OpenAI
        request_payload = {
            "model": invocation_params.get("model", "unknown"),
            "messages": [],
            "temperature": invocation_params.get("temperature"),
            "max_tokens": invocation_params.get("max_tokens"),
            "stream": invocation_params.get("stream", False),
        }
        
        # Add any additional parameters
        for key in ["top_p", "frequency_penalty", "presence_penalty", "n", "stop"]:
            if key in invocation_params:
                request_payload[key] = invocation_params[key]
        
        # Extract messages from kwargs if available
        if "messages" in kwargs:
            messages = kwargs["messages"]
            if hasattr(messages, "__iter__"):
                request_payload["messages"] = [
                    msg.dict() if hasattr(msg, "dict") else msg 
                    for msg in messages
                ]
        
        # Store for potential use in response logging
        self.request_data = request_payload
        
        logger.debug(
            "OpenAI HTTP Request Payload: %s",
            json.dumps(request_payload, indent=2, default=str)
        )
    
    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Log when LLM finishes processing."""
        if not self.enabled:
            return
        
        # Extract response data
        response_data = {
            "generations": [],
            "llm_output": response.llm_output or {},
        }
        
        for generation_list in response.generations:
            for gen in generation_list:
                gen_data = {
                    "text": gen.text,
                    "generation_info": gen.generation_info or {},
                }
                if hasattr(gen, "message"):
                    gen_data["message"] = gen.message.dict() if hasattr(gen.message, "dict") else str(gen.message)
                response_data["generations"].append(gen_data)
        
        logger.debug(
            "OpenAI HTTP Response Payload: %s",
            json.dumps(response_data, indent=2, default=str)
        )
    
    def on_llm_error(self, error: Exception, **kwargs: Any) -> None:
        """Log when LLM encounters an error."""
        if not self.enabled:
            return
        
        logger.debug(
            "OpenAI HTTP Error: %s",
            json.dumps({"error": str(error), "type": type(error).__name__}, indent=2)
        )
