import json
from typing import Any, AsyncGenerator, Dict, List
from pydantic import BaseModel
import litellm
from litellm import Router
from litellm.integrations.custom_logger import CustomLogger

from app.dependencies import model_list, logger
from app.config import DEFAULT_LLM_MODEL, LITELLM_ALLOWED_FAILS, LITELLM_COOLDOWN_TIME
from app.models import LLMUsage

def safe_get(obj, *path, default=None):
    for key in path:
        if obj is None:
            return default
        obj = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, 0)
    return obj if obj is not None else default

class MyCustomHandler(CustomLogger):
    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        try:
            metadata = kwargs["litellm_params"]["metadata"]
            if metadata:
                metadata["usage_data"].llm_deployment = kwargs["model"]
        except Exception as e:
            logger.error(f"Error occurred while saving llm deployment post success: {e}")

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        logger.error(
            f"Error occurred while calling deployment {kwargs['model']}: {kwargs['exception']}"
        )


customHandler = MyCustomHandler()
litellm.callbacks = [customHandler]
litellm.drop_params = True

class LLMRouterService:
    def __init__(self, config: dict):
        """
        Initialize the LLMRouterService and configure the Router instance.
        """
        self.router = Router(**config)

    async def agenerate_streaming_response(
        self,
        prompt: List[Dict[str, Any]],
        model: str = DEFAULT_LLM_MODEL,
        usage_data: LLMUsage = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response using the Router object.

        :param prompts: A list of prompt messages formatted as dictionaries.
        :param model: The LLM model to use.
        :param usage_data: A mutable dictionary to store usage data.
        :param kwargs: Additional parameters (e.g. temperature) for the Router's method.
        :yield: Chunks of the response content.
        """

        try:
            # Call the Router with streaming enabled
            response = await self.router.acompletion(
                model=model,
                messages=prompt,
                stream=True,
                stream_options={"include_usage": True},
                metadata={"usage_data": usage_data},
                **kwargs,
            )

            # Stream chunks of the response
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content

                # Extract usage data from the last chunk
                if "usage" in chunk and usage_data is not None:
                    usage_data.cached_input_tokens = chunk.usage.prompt_tokens_details.cached_tokens if chunk.usage.prompt_tokens_details else 0
                    usage_data.input_tokens = chunk.usage.prompt_tokens
                    usage_data.response_tokens = chunk.usage.completion_tokens
                    usage_data.total_tokens = chunk.usage.total_tokens
        except Exception as e:
            logger.error("Error occurred while generating response: %s", str(e))
            raise
    
    async def agenerate_structured_response(
        self,
        prompt: List[Dict[str, Any]],
        response_model_format: BaseModel,
        model: str = DEFAULT_LLM_MODEL,
        usage_data: LLMUsage = None,
        **kwargs: Any,
    ):
        try:
            response = await self.router.acompletion(
                model=model,
                messages=prompt,
                response_format=response_model_format,
                # stream=False,
                # stream_options={"include_usage": True},
                metadata={"usage_data": usage_data},
                **kwargs
            )

            if "usage" in response and usage_data is not None:
                usage_data.input_tokens = response.usage.prompt_tokens
                usage_data.response_tokens = response.usage.completion_tokens
                usage_data.total_tokens = response.usage.total_tokens
        
        except Exception as e:
            logger.error("Error occurred while generating structured response: %s", str(e))
            raise

        try:
            response_json = json.loads(response.choices[0].message.content)
            return response_json
        except Exception as e:
            logger.error("Error occurred while parsing structured response: %s", str(e))
            return None


router_config = {
    "model_list": model_list,
    "routing_strategy": "usage-based-routing-v2",
    "fallbacks": [{"gpt-4o-mini": ["gpt-4o-mini-fallback"]}, {"gpt-5-mini": ["gpt-5-mini-fallback"]}],
    "allowed_fails": LITELLM_ALLOWED_FAILS,
    "cooldown_time": LITELLM_COOLDOWN_TIME,
    # Set these for debugging
    # "set_verbose": True,
    # "debug_level": "DEBUG",
}

# Create a global instance of LLMRouterService
router_service = LLMRouterService(router_config)


# Provide a dependency injection function
def get_router_service() -> LLMRouterService:
    return router_service
