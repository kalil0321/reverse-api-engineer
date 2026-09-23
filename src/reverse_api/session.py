"""Session and history management for reverse-api."""

import json
import tempfile
from pathlib import Path
from typing import Any


class SessionManager:
    """Handles history tracking and persistence of runs."""

    def __init__(self, history_path: Path) -> None:
        self.history_path = history_path
        self.history: list[dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        """Load history from disk."""
        if self.history_path.exists():
            try:
                with open(self.history_path, encoding="utf-8-sig") as f:
                    self.history = json.load(f)
            except (json.JSONDecodeError, UnicodeError, OSError):
                # Fallback to empty history if file is corrupted
                self.history = []

    def save(self) -> None:
        """Save history to disk."""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        # Close the temporary file before replacement (required on Windows),
        # and keep it on the same filesystem for atomic replacement.
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.history_path.parent,
                prefix=f".{self.history_path.name}.", suffix=".tmp", delete=False,
            ) as f:
                temp_path = Path(f.name)
                json.dump(self.history, f, indent=4)
            temp_path.replace(self.history_path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def add_run(self, run_id: str, prompt: str, **kwargs: Any) -> None:
        """Add a new run to history."""
        run_data = {
            "run_id": run_id,
            "prompt": prompt,
            "timestamp": kwargs.get("timestamp"),
            "url": kwargs.get("url"),
            "model": kwargs.get("model"),
            "mode": kwargs.get("mode", "manual"),  # Track which mode was used
            "sdk": kwargs.get("sdk"),
            "output_mode": kwargs.get("output_mode", "client"),  # Track output format (client/docs)
            "usage": kwargs.get("usage", {}),
            "paths": kwargs.get("paths", {}),
        }
        # Avoid duplicates if updating existing run
        self.history = [r for r in self.history if r["run_id"] != run_id]
        self.history.insert(0, run_data)  # Most recent first
        self.save()

    def update_run(self, run_id: str, **kwargs: Any) -> None:
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

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Get data for a specific run."""
        for run in self.history:
            if run["run_id"] == run_id:
                return run
        return None

    def get_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent history."""
        return self.history[:limit]
