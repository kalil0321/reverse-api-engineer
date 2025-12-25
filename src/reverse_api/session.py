"""Session and history management for reverse-api."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class SessionManager:
    """Handles history tracking and persistence of runs."""

    def __init__(self, history_path: Path):
        self.history_path = history_path
        self.history: List[Dict[str, Any]] = []
        self.load()

    def load(self):
        """Load history from disk."""
        if self.history_path.exists():
            try:
                with open(self.history_path, "r") as f:
                    self.history = json.load(f)
            except (json.JSONDecodeError, OSError):
                # Fallback to empty history if file is corrupted
                self.history = []

    def save(self):
        """Save history to disk."""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_path, "w") as f:
            json.dump(self.history, f, indent=4)

    def add_run(self, run_id: str, prompt: str, **kwargs):
        """Add a new run to history."""
        run_data = {
            "run_id": run_id,
            "prompt": prompt,
            "timestamp": kwargs.get("timestamp"),
            "url": kwargs.get("url"),
            "model": kwargs.get("model"),
            "mode": kwargs.get("mode", "manual"),  # Track which mode was used
            "usage": kwargs.get("usage", {}),
            "paths": kwargs.get("paths", {}),
        }
        # Avoid duplicates if updating existing run
        self.history = [r for r in self.history if r["run_id"] != run_id]
        self.history.insert(0, run_data)  # Most recent first
        self.save()

    def update_run(self, run_id: str, **kwargs):
        """Update an existing run with more data (e.g., usage after engineer)."""
        for run in self.history:
            if run["run_id"] == run_id:
                if "usage" in kwargs:
                    run["usage"].update(kwargs["usage"])
                if "paths" in kwargs:
                    run["paths"].update(kwargs["paths"])
                for key, value in kwargs.items():
                    if key not in ("usage", "paths"):
                        run[key] = value
                break
        self.save()

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get data for a specific run."""
        for run in self.history:
            if run["run_id"] == run_id:
                return run
        return None

    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent history."""
        return self.history[:limit]
