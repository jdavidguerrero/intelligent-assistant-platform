"""Tests for core/routing/costs.py — cost calculation.

Tests cover:
- Known model costs against manual calculations
- Prefix matching (version suffixes are handled)
- Unknown model returns 0.0 (no crash)
- Negative token counts raise ValueError
- format_cost() formatting
- calculate_cost() is pure (same input → same output)
"""

from __future__ import annotations

import pytest

from core.routing.costs import calculate_cost, format_cost


class TestCalculateCostKnownModels:
    def test_gpt4o_mini_input_cost(self) -> None:
        """gpt-4o-mini: $0.15 per 1M input tokens."""
        cost = calculate_cost("gpt-4o-mini", input_tokens=1_000_000, output_tokens=0)
        assert abs(cost - 0.15) < 1e-7

    def test_gpt4o_mini_output_cost(self) -> None:
        """gpt-4o-mini: $0.60 per 1M output tokens."""
        cost = calculate_cost("gpt-4o-mini", input_tokens=0, output_tokens=1_000_000)
        assert abs(cost - 0.60) < 1e-7

    def test_gpt4o_input_cost(self) -> None:
        """gpt-4o: $2.50 per 1M input tokens."""
        cost = calculate_cost("gpt-4o", input_tokens=1_000_000, output_tokens=0)
        assert abs(cost - 2.50) < 1e-7

    def test_gpt4o_output_cost(self) -> None:
        """gpt-4o: $10.00 per 1M output tokens."""
        cost = calculate_cost("gpt-4o", input_tokens=0, output_tokens=1_000_000)
        assert abs(cost - 10.00) < 1e-7

    def test_claude_haiku_cost(self) -> None:
        """claude-haiku: $0.80/$4.00 per M tokens."""
        cost = calculate_cost(
            "claude-haiku-4-20250514", input_tokens=1_000_000, output_tokens=1_000_000
        )
        expected = 0.80 + 4.00
        assert abs(cost - expected) < 1e-6

    def test_claude_sonnet_cost(self) -> None:
        """claude-sonnet: $3.00/$15.00 per M tokens."""
        cost = calculate_cost(
            "claude-sonnet-4-20250514", input_tokens=1_000_000, output_tokens=1_000_000
        )
        expected = 3.00 + 15.00
        assert abs(cost - expected) < 1e-6

    def test_zero_tokens_zero_cost(self) -> None:
        cost = calculate_cost("gpt-4o", input_tokens=0, output_tokens=0)
        assert cost == 0.0

    def test_small_query_cost_realistic(self) -> None:
        """500 input + 300 output tokens with gpt-4o-mini — realistic query cost."""
        cost = calculate_cost("gpt-4o-mini", input_tokens=500, output_tokens=300)
        # (500 * 0.15 + 300 * 0.60) / 1_000_000 = (75 + 180) / 1_000_000 = 0.000000255
        expected = (500 * 0.15 + 300 * 0.60) / 1_000_000
        assert abs(cost - expected) < 1e-10


class TestPrefixMatching:
    def test_gpt4o_mini_not_matched_as_gpt4o(self) -> None:
        """gpt-4o-mini must be cheaper than gpt-4o (prefix ordering is correct)."""
        cost_mini = calculate_cost("gpt-4o-mini", input_tokens=1_000_000, output_tokens=0)
        cost_full = calculate_cost("gpt-4o", input_tokens=1_000_000, output_tokens=0)
        assert cost_mini < cost_full

    def test_version_suffix_handled(self) -> None:
        """Model identifiers with version suffixes are matched correctly."""
        cost_bare = calculate_cost("gpt-4o-mini", input_tokens=100, output_tokens=50)
        cost_versioned = calculate_cost(
            "gpt-4o-mini-2024-07-18", input_tokens=100, output_tokens=50
        )
        assert cost_bare == cost_versioned

    def test_claude_haiku_version_suffix(self) -> None:
        """claude-haiku-4-20250514 matches the haiku prefix."""
        cost = calculate_cost("claude-haiku-4-20250514", input_tokens=1_000_000, output_tokens=0)
        assert abs(cost - 0.80) < 1e-7

    def test_case_insensitive_matching(self) -> None:
        """Model names are matched case-insensitively."""
        cost_lower = calculate_cost("gpt-4o-mini", input_tokens=500, output_tokens=300)
        cost_upper = calculate_cost("GPT-4O-MINI", input_tokens=500, output_tokens=300)
        assert cost_lower == cost_upper


class TestUnknownModels:
    def test_unknown_model_returns_zero(self) -> None:
        cost = calculate_cost("totally-unknown-model-v99", input_tokens=1_000, output_tokens=500)
        assert cost == 0.0

    def test_empty_model_string_returns_zero(self) -> None:
        cost = calculate_cost("", input_tokens=1_000, output_tokens=500)
        assert cost == 0.0

    def test_local_llama_is_free(self) -> None:
        """Local Ollama llama models have zero cost."""
        cost = calculate_cost("llama3.2", input_tokens=1_000_000, output_tokens=1_000_000)
        assert cost == 0.0


class TestValidation:
    def test_negative_input_tokens_raises(self) -> None:
        with pytest.raises(ValueError, match="input_tokens"):
            calculate_cost("gpt-4o-mini", input_tokens=-1, output_tokens=0)

    def test_negative_output_tokens_raises(self) -> None:
        with pytest.raises(ValueError, match="output_tokens"):
            calculate_cost("gpt-4o-mini", input_tokens=0, output_tokens=-1)


class TestFormatCost:
    def test_format_small_cost(self) -> None:
        assert format_cost(0.00042) == "$0.000420"

    def test_format_zero_cost(self) -> None:
        assert format_cost(0.0) == "$0.000000"

    def test_format_larger_cost(self) -> None:
        assert format_cost(0.1234) == "$0.123400"

    def test_format_starts_with_dollar(self) -> None:
        assert format_cost(0.001).startswith("$")


class TestCostSavingsProjection:
    """Verify the routing cost model meets the >40% savings goal.

    With distribution: 60% factual (gpt-4o-mini), 35% creative (gpt-4o), 5% realtime (haiku).
    Baseline: always gpt-4o.
    Uses 500 input / 300 output tokens per query.
    """

    INPUT_TOKENS = 500
    OUTPUT_TOKENS = 300
    N_FACTUAL = 30
    N_CREATIVE = 17
    N_REALTIME = 3
    TOTAL = N_FACTUAL + N_CREATIVE + N_REALTIME  # 50

    def _query_cost(self, model: str) -> float:
        return calculate_cost(model, self.INPUT_TOKENS, self.OUTPUT_TOKENS)

    def test_routing_saves_over_40_percent_vs_always_standard(self) -> None:
        """Projected savings with routing must exceed 40% over always-gpt-4o."""
        baseline_cost = self.TOTAL * self._query_cost("gpt-4o")

        routing_cost = (
            self.N_FACTUAL * self._query_cost("gpt-4o-mini")
            + self.N_CREATIVE * self._query_cost("gpt-4o")
            + self.N_REALTIME * self._query_cost("claude-haiku-4-20250514")
        )

        savings_pct = (baseline_cost - routing_cost) / baseline_cost
        assert savings_pct > 0.40, (
            f"Routing saves only {savings_pct:.1%} — expected >40%.\n"
            f"Baseline: ${baseline_cost:.6f}, Routing: ${routing_cost:.6f}"
        )
