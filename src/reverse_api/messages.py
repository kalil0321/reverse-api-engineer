"""Message persistence for engineer runs."""

import json
from datetime import datetime
from typing import Any

from .utils import get_messages_path


class MessageStore:
    """Handles saving and loading messages for engineer runs."""

    def __init__(self, run_id: str, output_dir: str | None = None):
        self.run_id = run_id
        self.messages_path = get_messages_path(run_id, output_dir)
        self.messages_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now().isoformat()

    def append(self, msg_type: str, content: Any, **kwargs) -> None:
        """Append a message to the JSONL file."""
        message = {
            "timestamp": self._get_timestamp(),
            "type": msg_type,
            "content": content,
            **kwargs,
        }
        with open(self.messages_path, "a") as f:
            f.write(json.dumps(message) + "\n")

    def save_prompt(self, prompt: str) -> None:
        """Save the initial prompt."""
        self.append("prompt", prompt)

    def save_tool_start(self, tool_name: str, tool_input: dict) -> None:
        """Save a tool start event."""
        self.append("tool_start", {"name": tool_name, "input": tool_input})

    def save_tool_result(
        self, tool_name: str, is_error: bool = False, output: str | None = None
    ) -> None:
        """Save a tool result event."""
        self.append(
            "tool_result",
            {"name": tool_name, "is_error": is_error, "output": output},
        )

    def save_thinking(self, text: str) -> None:
        """Save Claude's thinking/response text."""
        self.append("thinking", text)

    def save_error(self, error: str) -> None:
        """Save an error event."""
        self.append("error", error)

    def save_result(self, result: dict[str, Any]) -> None:
        """Save the final result."""
        self.append("result", result)

    def load(self) -> list[dict[str, Any]]:
        """Load all messages from the JSONL file."""
        if not self.messages_path.exists():
            return []
        messages = []
        with open(self.messages_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return messages

    @classmethod
    def exists(cls, run_id: str, output_dir: str | None = None) -> bool:
        """Check if messages exist for a run."""
        from .utils import get_messages_path

        return get_messages_path(run_id, output_dir).exists()
