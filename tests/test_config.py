"""Tests for config.py - ConfigManager."""

import json
from pathlib import Path

import pytest

from reverse_api.config import DEFAULT_CONFIG, ConfigManager


class TestConfigManagerInit:
    """Test ConfigManager initialization."""

    def test_default_config(self, config_path):
        """ConfigManager starts with default config when no file exists."""
        cm = ConfigManager(config_path)
        assert cm.config == DEFAULT_CONFIG

    def test_loads_existing_config(self, config_path):
        """ConfigManager loads config from existing file."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"sdk": "opencode", "claude_code_model": "claude-opus-4-5"}))
        cm = ConfigManager(config_path)
        assert cm.get("sdk") == "opencode"
        assert cm.get("claude_code_model") == "claude-opus-4-5"

    def test_ignores_invalid_keys(self, config_path):
        """ConfigManager ignores keys not in DEFAULT_CONFIG."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"sdk": "claude", "unknown_key": "value"}))
        cm = ConfigManager(config_path)
        assert "unknown_key" not in cm.config

    def test_corrupted_json_falls_back_to_defaults(self, config_path):
        """ConfigManager uses defaults when config file has invalid JSON."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("not valid json {{{")
        cm = ConfigManager(config_path)
        assert cm.config == DEFAULT_CONFIG

    def test_empty_file_falls_back_to_defaults(self, config_path):
        """ConfigManager uses defaults for empty file."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("")
        cm = ConfigManager(config_path)
        assert cm.config == DEFAULT_CONFIG


class TestConfigMigration:
    """Test backward compatibility migrations."""

    def test_migrate_model_to_claude_code_model(self, config_path):
        """Old 'model' key migrates to 'claude_code_model'."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"model": "claude-opus-4-5"}))
        cm = ConfigManager(config_path)
        assert cm.get("claude_code_model") == "claude-opus-4-5"

    def test_no_migrate_if_claude_code_model_exists(self, config_path):
        """Migration skipped if 'claude_code_model' already set."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"model": "old", "claude_code_model": "new"}))
        cm = ConfigManager(config_path)
        assert cm.get("claude_code_model") == "new"

    def test_migrate_agent_model_to_browser_use_model(self, config_path):
        """Old 'agent_model' migrates to 'browser_use_model' for browser-use provider."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"agent_model": "openai/gpt-4", "agent_provider": "browser-use"}))
        cm = ConfigManager(config_path)
        assert cm.get("browser_use_model") == "openai/gpt-4"

    def test_migrate_agent_model_to_stagehand_model(self, config_path):
        """Old 'agent_model' migrates to 'stagehand_model' for stagehand provider."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"agent_model": "openai/cu-preview", "agent_provider": "stagehand"}))
        cm = ConfigManager(config_path)
        assert cm.get("stagehand_model") == "openai/cu-preview"

    def test_migrate_agent_model_default_provider(self, config_path):
        """Old 'agent_model' defaults to browser-use migration."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"agent_model": "bu-llm"}))
        cm = ConfigManager(config_path)
        assert cm.get("browser_use_model") == "bu-llm"

    def test_no_migrate_agent_model_if_target_exists(self, config_path):
        """Migration skipped if target key already exists."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({"agent_model": "old", "browser_use_model": "new"}))
        cm = ConfigManager(config_path)
        assert cm.get("browser_use_model") == "new"


class TestConfigManagerOperations:
    """Test get/set/update/save operations."""

    def test_get_existing_key(self, config_path):
        """Get returns value for existing key."""
        cm = ConfigManager(config_path)
        assert cm.get("sdk") == "claude"

    def test_get_missing_key_returns_default(self, config_path):
        """Get returns default for missing key."""
        cm = ConfigManager(config_path)
        assert cm.get("nonexistent", "fallback") == "fallback"

    def test_get_missing_key_returns_none(self, config_path):
        """Get returns None by default for missing key."""
        cm = ConfigManager(config_path)
        assert cm.get("nonexistent") is None

    def test_set_saves_to_disk(self, config_path):
        """Set persists value to config file."""
        cm = ConfigManager(config_path)
        cm.set("sdk", "opencode")
        assert cm.get("sdk") == "opencode"

        # Verify it was saved to disk
        with open(config_path) as f:
            data = json.load(f)
        assert data["sdk"] == "opencode"

    def test_update_multiple_keys(self, config_path):
        """Update persists multiple values."""
        cm = ConfigManager(config_path)
        cm.update({"sdk": "opencode", "claude_code_model": "claude-haiku-4-5"})
        assert cm.get("sdk") == "opencode"
        assert cm.get("claude_code_model") == "claude-haiku-4-5"

        # Verify on disk
        with open(config_path) as f:
            data = json.load(f)
        assert data["sdk"] == "opencode"

    def test_save_creates_parent_dirs(self, tmp_path):
        """Save creates parent directories if they don't exist."""
        config_path = tmp_path / "nested" / "dir" / "config.json"
        cm = ConfigManager(config_path)
        cm.save()
        assert config_path.exists()

    def test_save_format(self, config_path):
        """Saved config has indented JSON."""
        cm = ConfigManager(config_path)
        cm.save()
        content = config_path.read_text()
        # Check it's indented (not compact)
        assert "\n" in content
        assert "    " in content


class TestDefaultConfig:
    """Test DEFAULT_CONFIG has expected keys."""

    def test_has_required_keys(self):
        """DEFAULT_CONFIG contains all expected keys."""
        expected_keys = {
            "agent_provider",
            "browser_use_model",
            "claude_code_model",
            "collector_model",
            "opencode_model",
            "opencode_provider",
            "output_dir",
            "output_language",
            "real_time_sync",
            "sdk",
            "stagehand_model",
        }
        assert set(DEFAULT_CONFIG.keys()) == expected_keys

    def test_default_values(self):
        """DEFAULT_CONFIG has expected default values."""
        assert DEFAULT_CONFIG["sdk"] == "claude"
        assert DEFAULT_CONFIG["output_dir"] is None
        assert DEFAULT_CONFIG["output_language"] == "python"
        assert DEFAULT_CONFIG["real_time_sync"] is True
