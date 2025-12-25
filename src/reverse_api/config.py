"""Configuration management for reverse-api."""

import json
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG = {
    "model": "claude-sonnet-4-5",
    "output_dir": None,  # None means use ~/.reverse-api/runs
    "sdk": "claude",  # "opencode" or "claude"
    "agent_provider": "browser-use",
    # We support openai & google as model providers
    "agent_model": "bu-llm", # "bu-llm" or "{provider}/{model_name}" (e.g. "openai/gpt-5-mini")
}


class ConfigManager:
    """Handles user settings and persistence."""

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        """Load configuration from disk."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    user_config = json.load(f)
                    # Only keep valid keys
                    valid_config = {k: v for k, v in user_config.items() if k in self.config}
                    self.config.update(valid_config)
            except (json.JSONDecodeError, OSError):
                # Fallback to defaults if file is corrupted
                pass

    def save(self):
        """Save configuration to disk."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self.config, f, indent=4)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        """Set a configuration value and save."""
        self.config[key] = value
        self.save()

    def update(self, settings: Dict[str, Any]):
        """Update multiple settings and save."""
        self.config.update(settings)
        self.save()
