"""Tests for pricing.py - Model pricing and cost calculations."""

from unittest.mock import MagicMock, patch

import pytest

from reverse_api.pricing import (
    MODEL_PRICING,
    _LITELLM_MODEL_MAP,
    _get_pricing_from_litellm,
    calculate_cost,
    get_model_pricing,
)


class TestModelPricing:
    """Test MODEL_PRICING dictionary."""

    def test_has_claude_models(self):
        """All Claude models are in pricing."""
        assert "claude-sonnet-4-5" in MODEL_PRICING
        assert "claude-opus-4-5" in MODEL_PRICING
        assert "claude-haiku-4-5" in MODEL_PRICING

    def test_has_gemini_models(self):
        """All Gemini models are in pricing."""
        assert "gemini-3-flash" in MODEL_PRICING
        assert "gemini-3-pro" in MODEL_PRICING
        assert "gemini-3-pro-low" in MODEL_PRICING
        assert "gemini-3-pro-high" in MODEL_PRICING

    def test_has_thinking_models(self):
        """Thinking model variants are in pricing."""
        assert "claude-sonnet-4-5-thinking-low" in MODEL_PRICING
        assert "claude-sonnet-4-5-thinking-medium" in MODEL_PRICING
        assert "claude-sonnet-4-5-thinking-high" in MODEL_PRICING
        assert "claude-opus-4-5-thinking-low" in MODEL_PRICING
        assert "claude-opus-4-5-thinking-medium" in MODEL_PRICING
        assert "claude-opus-4-5-thinking-high" in MODEL_PRICING

    def test_pricing_keys(self):
        """Each model has required pricing keys."""
        required_keys = {"input", "output", "cache_creation", "cache_read", "reasoning"}
        for model_id, pricing in MODEL_PRICING.items():
            assert set(pricing.keys()) == required_keys, f"Model {model_id} missing keys"

    def test_pricing_values_positive(self):
        """All pricing values are positive."""
        for model_id, pricing in MODEL_PRICING.items():
            for key, value in pricing.items():
                assert value >= 0, f"Model {model_id} has negative {key}: {value}"

    def test_opus_more_expensive_than_sonnet(self):
        """Opus should be more expensive than Sonnet."""
        assert MODEL_PRICING["claude-opus-4-5"]["input"] > MODEL_PRICING["claude-sonnet-4-5"]["input"]
        assert MODEL_PRICING["claude-opus-4-5"]["output"] > MODEL_PRICING["claude-sonnet-4-5"]["output"]

    def test_haiku_cheapest_claude(self):
        """Haiku should be cheapest Claude model."""
        assert MODEL_PRICING["claude-haiku-4-5"]["input"] < MODEL_PRICING["claude-sonnet-4-5"]["input"]
        assert MODEL_PRICING["claude-haiku-4-5"]["output"] < MODEL_PRICING["claude-sonnet-4-5"]["output"]


class TestGetModelPricing:
    """Test get_model_pricing function."""

    def test_known_model(self):
        """Returns pricing for known model."""
        pricing = get_model_pricing("claude-sonnet-4-5")
        assert pricing is not None
        assert pricing["input"] == 3.00
        assert pricing["output"] == 15.00

    def test_unknown_model_no_litellm(self):
        """Returns None for unknown model when litellm not available."""
        with patch("reverse_api.pricing._get_pricing_from_litellm", return_value=None):
            pricing = get_model_pricing("unknown-model-xyz")
            assert pricing is None

    def test_falls_back_to_litellm(self):
        """Falls back to litellm pricing when model not local."""
        mock_pricing = {"input": 1.0, "output": 2.0, "cache_creation": 0, "cache_read": 0, "reasoning": 2.0}
        with patch("reverse_api.pricing._get_pricing_from_litellm", return_value=mock_pricing):
            pricing = get_model_pricing("some-litellm-model")
            assert pricing == mock_pricing


class TestGetPricingFromLitellm:
    """Test _get_pricing_from_litellm function."""

    def test_litellm_not_installed(self):
        """Returns None when litellm is not installed."""
        with patch.dict("sys.modules", {"litellm": None}):
            result = _get_pricing_from_litellm("any-model")
            # Will fail import, return None
            assert result is None

    def test_litellm_with_direct_match(self):
        """Returns pricing for direct model match."""
        mock_model_cost = {
            "claude-sonnet-4-5": {
                "input_cost_per_token": 3e-06,
                "output_cost_per_token": 15e-06,
                "cache_creation_input_token_cost": 3.75e-06,
                "cache_read_input_token_cost": 0.3e-06,
            }
        }
        mock_litellm = MagicMock()
        mock_litellm.model_cost = mock_model_cost
        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            result = _get_pricing_from_litellm("claude-sonnet-4-5")
            assert result is not None
            assert abs(result["input"] - 3.0) < 0.01
            assert abs(result["output"] - 15.0) < 0.01

    def test_litellm_with_mapped_model(self):
        """Returns pricing via model name mapping."""
        mock_model_cost = {
            "anthropic.claude-sonnet-4-5": {
                "input_cost_per_token": 3e-06,
                "output_cost_per_token": 15e-06,
                "cache_creation_input_token_cost": 3.75e-06,
                "cache_read_input_token_cost": 0.3e-06,
            }
        }
        mock_litellm = MagicMock()
        mock_litellm.model_cost = mock_model_cost
        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            result = _get_pricing_from_litellm("claude-sonnet-4-5")
            assert result is not None

    def test_litellm_model_not_found(self):
        """Returns None when model not in litellm."""
        mock_litellm = MagicMock()
        mock_litellm.model_cost = {}
        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            result = _get_pricing_from_litellm("unknown-model")
            assert result is None

    def test_litellm_zero_pricing_skipped(self):
        """Returns None when litellm pricing is all zeros."""
        mock_model_cost = {
            "zero-model": {
                "input_cost_per_token": 0,
                "output_cost_per_token": 0,
            }
        }
        mock_litellm = MagicMock()
        mock_litellm.model_cost = mock_model_cost
        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            result = _get_pricing_from_litellm("zero-model")
            assert result is None

    def test_litellm_exception_returns_none(self):
        """Returns None on any exception."""
        mock_litellm = MagicMock()
        # Make model_cost a property that raises when accessed
        type(mock_litellm).model_cost = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            result = _get_pricing_from_litellm("any-model")
            assert result is None

    def test_litellm_import_error(self):
        """Returns None on ImportError (litellm not installed)."""
        # Patch the import to raise ImportError directly
        with patch("builtins.__import__", side_effect=ImportError("no litellm")):
            result = _get_pricing_from_litellm("any-model")
            assert result is None


class TestLitellmModelMap:
    """Test _LITELLM_MODEL_MAP structure."""

    def test_map_has_claude_models(self):
        """Map includes Claude model variations."""
        assert "claude-sonnet-4-5" in _LITELLM_MODEL_MAP
        assert "claude-opus-4-5" in _LITELLM_MODEL_MAP
        assert "claude-haiku-4-5" in _LITELLM_MODEL_MAP

    def test_map_has_gemini_models(self):
        """Map includes Gemini model variations."""
        assert "gemini-3-flash" in _LITELLM_MODEL_MAP
        assert "gemini-3-pro" in _LITELLM_MODEL_MAP

    def test_map_values_are_lists(self):
        """Each map entry is a list of alternative names."""
        for key, value in _LITELLM_MODEL_MAP.items():
            assert isinstance(value, list)
            assert len(value) >= 1


class TestCalculateCost:
    """Test calculate_cost function."""

    def test_known_model_basic(self):
        """Calculate cost for a known model with basic tokens."""
        cost = calculate_cost(
            model_id="claude-sonnet-4-5",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        # Input: 1M * $3/M = $3, Output: 1M * $15/M = $15 = $18
        assert abs(cost - 18.0) < 0.01

    def test_zero_tokens(self):
        """Zero tokens gives zero cost."""
        cost = calculate_cost(model_id="claude-sonnet-4-5")
        assert cost == 0.0

    def test_cache_tokens(self):
        """Cache tokens are included in cost."""
        cost = calculate_cost(
            model_id="claude-sonnet-4-5",
            cache_creation_tokens=1_000_000,
            cache_read_tokens=1_000_000,
        )
        # Cache creation: 1M * $3.75/M = $3.75, Cache read: 1M * $0.30/M = $0.30
        assert abs(cost - 4.05) < 0.01

    def test_reasoning_tokens(self):
        """Reasoning tokens are included in cost."""
        cost = calculate_cost(
            model_id="claude-sonnet-4-5",
            reasoning_tokens=1_000_000,
        )
        # Reasoning: 1M * $15/M = $15
        assert abs(cost - 15.0) < 0.01

    def test_all_token_types(self):
        """All token types contribute to cost."""
        cost = calculate_cost(
            model_id="claude-sonnet-4-5",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cache_creation_tokens=1_000_000,
            cache_read_tokens=1_000_000,
            reasoning_tokens=1_000_000,
        )
        expected = 3.0 + 15.0 + 3.75 + 0.30 + 15.0  # = 37.05
        assert abs(cost - expected) < 0.01

    def test_unknown_model_falls_back_to_sonnet(self):
        """Unknown model uses Claude Sonnet 4.5 pricing."""
        with patch("reverse_api.pricing._get_pricing_from_litellm", return_value=None):
            cost = calculate_cost(
                model_id="unknown-model",
                input_tokens=1_000_000,
            )
            # Should use Sonnet pricing: 1M * $3/M = $3
            assert abs(cost - 3.0) < 0.01

    def test_none_model_falls_back_to_sonnet(self):
        """None model uses Claude Sonnet 4.5 pricing."""
        cost = calculate_cost(
            model_id=None,
            input_tokens=1_000_000,
        )
        assert abs(cost - 3.0) < 0.01

    def test_litellm_fallback(self):
        """Falls back to litellm when model not local."""
        litellm_pricing = {
            "input": 1.0,
            "output": 2.0,
            "cache_creation": 0.5,
            "cache_read": 0.1,
            "reasoning": 2.0,
        }
        with patch("reverse_api.pricing._get_pricing_from_litellm", return_value=litellm_pricing):
            cost = calculate_cost(
                model_id="custom-litellm-model",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
            )
            assert abs(cost - 3.0) < 0.01  # 1.0 + 2.0

    def test_small_token_counts(self):
        """Small token counts give proportional costs."""
        cost = calculate_cost(
            model_id="claude-sonnet-4-5",
            input_tokens=1000,
            output_tokens=500,
        )
        expected = (1000 / 1_000_000 * 3.0) + (500 / 1_000_000 * 15.0)
        assert abs(cost - expected) < 0.0001

    def test_haiku_cheaper(self):
        """Haiku model should be cheaper for same tokens."""
        sonnet_cost = calculate_cost("claude-sonnet-4-5", input_tokens=1_000_000, output_tokens=1_000_000)
        haiku_cost = calculate_cost("claude-haiku-4-5", input_tokens=1_000_000, output_tokens=1_000_000)
        assert haiku_cost < sonnet_cost
