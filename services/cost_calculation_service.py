from app.config import OPENAI_COST
from app.models import LLMUsage


def calculate_llm_cost(usage_data: LLMUsage, model: str) -> float:
    return (
                (usage_data.input_tokens - usage_data.cached_input_tokens)
                / 1000
                * OPENAI_COST[model]["input_tokens"]
                + usage_data.cached_input_tokens
                / 1000
                * OPENAI_COST[model]["cached_input_tokens"]
                + usage_data.response_tokens
                / 1000
                * OPENAI_COST[model]["response_tokens"]
            )
