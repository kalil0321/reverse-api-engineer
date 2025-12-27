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
        "output": 75.00,
        "cache_creation": 18.75,
        "cache_read": 1.50,
        "reasoning": 75.00,
    },
    "claude-haiku-4-5": {
        "input": 1.00,
        "output": 5.00,
        "cache_creation": 1.25,
        "cache_read": 0.10,
        "reasoning": 5.00,
    },
    "google-gemini-3-flash": {
        "input": 0.00015,
        "output": 0.0006,
    },
    "google-gemini-3-pro": {
        "input": 0.0003,
        "output": 0.0012,
    },
}


def calculate_cost(
    model_id: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> float:
    """Calculate cost for a model based on token usage.

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
    # default to sonnet if unknown as this is the most common model
    pricing = MODEL_PRICING.get(model_id, MODEL_PRICING["claude-sonnet-4-5"])

    cost = (
        (input_tokens / 1_000_000 * pricing["input"])
        + (output_tokens / 1_000_000 * pricing["output"])
        + (cache_creation_tokens / 1_000_000 * pricing["cache_creation"])
        + (cache_read_tokens / 1_000_000 * pricing["cache_read"])
        + (reasoning_tokens / 1_000_000 * pricing["reasoning"])
    )

    return cost
