"""Tests for Ollama model selection in CLI settings."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from reverse_api import cli
from reverse_api.ollama_runtime import OllamaModel, OllamaStatus


def _model(name: str, *, size: int = 100) -> OllamaModel:
    return OllamaModel(
        name=name,
        size=size,
        capabilities=("completion", "tools"),
        context_length=131_072,
        parameter_size="20B",
    )


def test_single_compatible_model_is_selected_without_prompt():
    status = OllamaStatus(base_url="http://127.0.0.1:11434", models=(_model("only:model"),))

    with patch("reverse_api.ollama_runtime.ensure_ollama_models", new=AsyncMock(return_value=status)):
        with patch.object(cli.questionary, "select") as select:
            selected = cli._select_ollama_model_for_settings()

    assert selected == "only:model"
    select.assert_not_called()


def test_multiple_compatible_models_show_picker():
    status = OllamaStatus(
        base_url="http://127.0.0.1:11434",
        models=(_model("local:model", size=2_000_000_000), _model("cloud:model")),
    )
    prompt = MagicMock()
    prompt.ask.return_value = "cloud:model"

    with patch("reverse_api.ollama_runtime.ensure_ollama_models", new=AsyncMock(return_value=status)):
        with patch.object(cli.questionary, "select", return_value=prompt) as select:
            selected = cli._select_ollama_model_for_settings()

    assert selected == "cloud:model"
    choices = select.call_args.kwargs["choices"]
    assert "1.9 GB" in choices[0].title
    assert "cloud" in choices[1].title


def test_live_opencode_picker_always_offers_ollama():
    """Ollama can bootstrap itself even when it is absent from OpenCode's current catalog."""
    catalog = {"default": {}, "providers": []}
    provider_prompt = MagicMock()
    provider_prompt.ask.return_value = "ollama"

    with patch.object(
        cli,
        "_load_opencode_catalog_for_settings",
        new=AsyncMock(return_value=catalog),
    ):
        with patch.object(cli.questionary, "select", return_value=provider_prompt) as select:
            with patch.object(cli, "_select_ollama_model_for_settings", return_value="qwen3:8b"):
                selected = cli._select_opencode_pair_for_settings()

    assert selected == ("ollama", "qwen3:8b")
    choices = select.call_args.kwargs["choices"]
    assert [choice.value for choice in choices] == ["ollama", "back"]
