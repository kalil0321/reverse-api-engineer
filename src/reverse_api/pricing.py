"""Pricing models for different models."""

MODEL_PRICING = {
    "claude-sonnet-4-5": {
        "input": 3.00,
        "output": 15.00,
        "cache_creation": 3.75,
        "cache_read": 0.30,
        "reasoning": 15.00,
    },
    "claude-opus-4-5": {
        "input": 15.00,
        "output": 25.00,
        "cache_creation": 6.25,
        "cache_read": 0.50,
        "reasoning": 25.00,
    },
    "claude-haiku-4-5": {
        "input": 1.00,
        "output": 5.00,
        "cache_creation": 1.25,
        "cache_read": 0.10,
        "reasoning": 5.00,
    },
    "gemini-3-flash": {
        "input": 0.5,
        "output": 3,
        "cache_creation": 1,
        "cache_read": 0.05,
        "reasoning": 3,
    },
    "gemini-3-pro": {
        "input": 3,
        "output": 12,
        "cache_creation": 4.5,
        "cache_read": 0.20,
        "reasoning": 12,
    },
    "gemini-3-pro-low": {
        "input": 3,
        "output": 12,
        "cache_creation": 4.5,
        "cache_read": 0.20,
        "reasoning": 12,
    },
    "gemini-3-pro-high": {
        "input": 3,
        "output": 12,
        "cache_creation": 4.5,
        "cache_read": 0.20,
        "reasoning": 12,
    },
    "claude-sonnet-4-5-thinking-low": {
        "input": 3.00,
        "output": 15.00,
        "cache_creation": 3.75,
        "cache_read": 0.30,
        "reasoning": 15.00,
    },
    "claude-sonnet-4-5-thinking-medium": {
        "input": 3.00,
        "output": 15.00,
        "cache_creation": 3.75,
        "cache_read": 0.30,
        "reasoning": 15.00,
    },
    "claude-sonnet-4-5-thinking-high": {
        "input": 3.00,
        "output": 15.00,
        "cache_creation": 3.75,
        "cache_read": 0.30,
        "reasoning": 15.00,
    },
    "claude-opus-4-5-thinking-low": {
        "input": 15.00,
        "output": 25.00,
        "cache_creation": 6.25,
        "cache_read": 0.50,
        "reasoning": 25.00,
    },
    "claude-opus-4-5-thinking-medium": {
        "input": 15.00,
        "output": 25.00,
        "cache_creation": 6.25,
        "cache_read": 0.50,
        "reasoning": 25.00,
    },
    "claude-opus-4-5-thinking-high": {
        "input": 15.00,
        "output": 25.00,
        "cache_creation": 6.25,
        "cache_read": 0.50,
        "reasoning": 25.00,
    },
}


# Model name mapping for LiteLLM compatibility
# Maps our model IDs to possible LiteLLM model name variations
_LITELLM_MODEL_MAP = {
    "claude-sonnet-4-5": [
        "claude-sonnet-4-5",
        "anthropic.claude-sonnet-4-5",
        "claude-3-5-sonnet-20241022",
    ],
    "claude-opus-4-5": [
        "claude-opus-4-5",
        "anthropic.claude-opus-4-5",
    ],
    "claude-haiku-4-5": [
        "claude-haiku-4-5",
        "anthropic.claude-haiku-4-5",
    ],
    "gemini-3-flash": [
        "gemini-3-flash",
        "google/gemini-3-flash",
        "gemini-flash",
    ],
    "gemini-3-pro": [
        "gemini-3-pro",
        "google/gemini-3-pro",
        "gemini-pro",
    ],
}


def _get_pricing_from_litellm(model_id: str) -> dict[str, float] | None:
    """Try to get pricing from LiteLLM package.

    This function attempts to fetch pricing data from the LiteLLM library,
    which maintains pricing for 100+ LLM models. This is used as a fallback
    when a model is not found in the local MODEL_PRICING dictionary.

    Args:
        model_id: Model identifier to look up

    Returns:
        Dictionary with pricing per million tokens in the format:
        {
            "input": float,
            "output": float,
            "cache_creation": float,
            "cache_read": float,
            "reasoning": float,
        }
        Returns None if:
        - LiteLLM is not installed
        - Model is not found in LiteLLM's database
        - An error occurs during lookup
    """
    try:
        # Import LiteLLM - may fail if not installed as optional dependency
        from litellm import model_cost

        # Try direct lookup and mapped variations
        model_names_to_try = [model_id]
        if model_id in _LITELLM_MODEL_MAP:
            model_names_to_try.extend(_LITELLM_MODEL_MAP[model_id])

        for model_name in model_names_to_try:
            if model_name in model_cost:
                litellm_pricing = model_cost[model_name]

                # Convert LiteLLM's per-token cost to our per-million-tokens format
                # LiteLLM uses values like 3e-06 for $0.000003 per token
                # We need to multiply by 1,000,000 to get per-million cost
                pricing = {
                    "input": litellm_pricing.get("input_cost_per_token", 0) * 1_000_000,
                    "output": litellm_pricing.get("output_cost_per_token", 0) * 1_000_000,
                    "cache_creation": litellm_pricing.get("cache_creation_input_token_cost", 0)
                    * 1_000_000,
                    "cache_read": litellm_pricing.get("cache_read_input_token_cost", 0) * 1_000_000,
                    "reasoning": litellm_pricing.get("output_cost_per_token", 0) * 1_000_000,
                }

                if pricing["input"] > 0 or pricing["output"] > 0:
                    return pricing

        return None

    except ImportError:
        return None
    except Exception:
        return None


def get_model_pricing(model_id: str) -> dict[str, float] | None:
    """Get pricing dictionary for a model.

    Args:
        model_id: Model identifier

    Returns:
        Pricing dictionary with keys: input, output, cache_creation, cache_read, reasoning
        Returns None if model not found
    """
    if model_id in MODEL_PRICING:
        return MODEL_PRICING[model_id]
    elif litellm_pricing := _get_pricing_from_litellm(model_id):
        return litellm_pricing
    return None


def calculate_cost(
    model_id: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> float:
    """Calculate cost for a model based on token usage.

    Uses a 3-tier fallback system:
    1. Local MODEL_PRICING dictionary (highest priority)
    2. LiteLLM pricing package (if installed and model found)
    3. Claude Sonnet 4.5 pricing (ultimate fallback)

    Args:
        model_id: Model identifier (e.g., "claude-sonnet-4-5")
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cache_creation_tokens: Number of tokens written to cache
        cache_read_tokens: Number of tokens read from cache
        reasoning_tokens: Number of reasoning tokens (for extended thinking models)

    Returns:
        Total cost in USD
    """
    if model_id in MODEL_PRICING:
        pricing = MODEL_PRICING[model_id]
    elif model_id and (litellm_pricing := _get_pricing_from_litellm(model_id)):
        pricing = litellm_pricing
    else:
        pricing = MODEL_PRICING["claude-sonnet-4-5"]

    cost = (
        (input_tokens / 1_000_000 * pricing["input"])
        + (output_tokens / 1_000_000 * pricing["output"])
        + (cache_creation_tokens / 1_000_000 * pricing["cache_creation"])
        + (cache_read_tokens / 1_000_000 * pricing["cache_read"])
        + (reasoning_tokens / 1_000_000 * pricing["reasoning"])
    )

    return cost
