"""Action recording infrastructure for manual browser sessions."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class RecordedAction:
    """A single recorded browser action."""

    type: str  # "click", "fill", "navigate", "press"
    selector: Optional[str] = None
    value: Optional[str] = None
    url: Optional[str] = None
    timestamp: float = 0.0
    metadata: Optional[dict] = None


class ActionRecorder:
    """Records browser actions during manual sessions."""

    def __init__(self):
        self.actions: List[RecordedAction] = []

    def add_action(self, action: RecordedAction) -> None:
        """Add an action to the recording."""
        self.actions.append(action)

    def get_actions(self) -> List[RecordedAction]:
        """Get all recorded actions."""
        return self.actions

    def save(self, path: Path) -> None:
        """Save actions to a JSON file."""
        data = [asdict(action) for action in self.actions]
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "ActionRecorder":
        """Load actions from a JSON file."""
        recorder = cls()
        if path.exists():
            with open(path) as f:
                data = json.load(f)
                for item in data:
                    recorder.add_action(RecordedAction(**item))
        return recorder

