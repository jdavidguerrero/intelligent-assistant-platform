"""Cost calculation for LLM generation calls.

Computes USD cost from (model, input_tokens, output_tokens) using a
prefix-matched pricing table. Returns 0.0 for unknown models.

This module is core/ pure: no I/O, no network, no env vars.
Pricing table is static (update as provider pricing changes).

Pricing source (2025-Q1):
  OpenAI:    https://openai.com/api/pricing/
  Anthropic: https://www.anthropic.com/pricing
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Pricing table
# ---------------------------------------------------------------------------

# Each entry: (model_prefix, input_usd_per_million, output_usd_per_million)
# Prefix matching — robust against model version suffixes like "-2024-11-20".
# More specific prefixes MUST come before more general ones (gpt-4o-mini before gpt-4o).
_COST_TABLE: list[tuple[str, float, float]] = [
    # OpenAI (gpt-4o-mini must precede gpt-4o)
    ("gpt-4o-mini", 0.15, 0.60),
    ("gpt-4.1-mini", 0.40, 1.60),
    ("gpt-4.1-nano", 0.10, 0.40),
    ("gpt-4.1", 2.00, 8.00),
    ("gpt-4o", 2.50, 10.00),
    ("o1-mini", 1.10, 4.40),
    ("o1", 15.00, 60.00),
    ("o3-mini", 1.10, 4.40),
    # Anthropic (haiku before sonnet before opus)
    ("claude-haiku", 0.80, 4.00),
    ("claude-sonnet", 3.00, 15.00),
    ("claude-opus", 15.00, 75.00),
    # Local / free models
    ("llama", 0.00, 0.00),
    ("mistral", 0.00, 0.00),
    ("phi", 0.00, 0.00),
    ("qwen", 0.00, 0.00),
    ("gemma", 0.00, 0.00),
]


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate the USD cost for a generation call.

    Uses prefix matching to find the pricing tier for a model identifier.
    The first matching prefix in the table wins, so more specific prefixes
    must appear earlier (e.g. "gpt-4o-mini" before "gpt-4o").

    Args:
        model:         Model identifier string from GenerationResponse.model
                       (e.g. "gpt-4o-mini-2024-07-18", "claude-haiku-4-20250514").
        input_tokens:  Number of prompt / input tokens consumed.
        output_tokens: Number of completion / output tokens generated.

    Returns:
        Cost in USD, rounded to 8 decimal places.
        Returns 0.0 if the model does not match any known prefix.

    Raises:
        ValueError: If input_tokens or output_tokens are negative.
    """
    if input_tokens < 0:
        raise ValueError(f"input_tokens must be >= 0, got {input_tokens}")
    if output_tokens < 0:
        raise ValueError(f"output_tokens must be >= 0, got {output_tokens}")

    model_lower = model.lower()
    for prefix, input_rate, output_rate in _COST_TABLE:
        if model_lower.startswith(prefix):
            cost = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
            return round(cost, 8)

    # Unknown model — return 0.0 (don't crash the pipeline)
    return 0.0


def format_cost(cost_usd: float) -> str:
    """Format a cost value for display.

    Examples:
        0.00042 → "$0.000420"
        0.0     → "$0.000000"
        0.1234  → "$0.123400"

    Args:
        cost_usd: Cost in USD.

    Returns:
        Formatted string with 6 decimal places.
    """
    return f"${cost_usd:.6f}"
