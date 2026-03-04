"""Shared test fixtures."""

import json
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory."""
    return tmp_path


@pytest.fixture
def config_path(tmp_path):
    """Provide a temporary config file path."""
    return tmp_path / "config.json"


@pytest.fixture
def history_path(tmp_path):
    """Provide a temporary history file path."""
    return tmp_path / "history.json"


@pytest.fixture
def sample_config():
    """Sample configuration data."""
    return {
        "sdk": "claude",
        "claude_code_model": "claude-sonnet-4-5",
        "opencode_model": "claude-opus-4-5",
        "opencode_provider": "anthropic",
        "output_dir": None,
    }


@pytest.fixture
def sample_har_data():
    """Minimal HAR data for testing."""
    return {
        "log": {
            "version": "1.2",
            "entries": [
                {
                    "request": {
                        "method": "GET",
                        "url": "https://api.example.com/users",
                        "headers": [{"name": "Authorization", "value": "Bearer test123"}],
                    },
                    "response": {
                        "status": 200,
                        "content": {"text": '{"users": []}'},
                    },
                }
            ],
        }
    }


@pytest.fixture
def har_file(tmp_path, sample_har_data):
    """Create a temporary HAR file."""
    har_path = tmp_path / "test.har"
    har_path.write_text(json.dumps(sample_har_data))
    return har_path
