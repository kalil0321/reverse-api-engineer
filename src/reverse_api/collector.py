import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from .collector_ui import CollectorUI
from .messages import MessageStore
from .pricing import calculate_cost
from .utils import generate_folder_name, get_collected_dir

# Suppress claude_agent_sdk logs
logging.getLogger("claude_agent_sdk").setLevel(logging.WARNING)
logging.getLogger("claude_agent_sdk._internal.transport.subprocess_cli").setLevel(logging.WARNING)


class Collector:
    """AI-powered web data collector using Claude Agent SDK.

    Uses Claude's built-in tools (WebFetch, Write) to collect data.
    The agent writes collected items to a JSONL file which is then
    processed into JSON + CSV output.
    """

    def __init__(
        self,
        run_id: str,
        prompt: str,
        model: str,
        output_dir: str | None = None,
    ):
        """Initialize collector.

        Args:
            run_id: Unique run identifier
            prompt: Natural language prompt describing data to collect
            model: Claude model to use
            output_dir: Optional custom output directory
        """
        self.run_id = run_id
        self.prompt = prompt
        self.model = model
        self.output_dir = output_dir

        self.ui = CollectorUI()
        self.message_store = MessageStore(run_id, output_dir)

        self._folder_name: str | None = None
        self._collected_dir: Path | None = None
        self.usage_metadata: dict[str, Any] = {}

    async def run(self) -> dict[str, Any] | None:
        """Run the collector agent loop.

        Returns:
            Result dict with output_path and collected_items, or None on error
        """
        self.ui.header(self.run_id, self.prompt, self.model)
        self.ui.start_collecting()

        self._folder_name = generate_folder_name(self.prompt)
        self._collected_dir = get_collected_dir(self._folder_name)

        self.items_path = self._collected_dir / "items.jsonl"

        self.message_store.save_prompt(self._build_collector_prompt())

        result = await self._agent_loop()

        if result and not result.get("error"):
            return self._finalize_collection()

        return result

    def _build_collector_prompt(self) -> str:
        """Build system prompt for collector agent."""
        return f"""You are a web data collection agent.

<mission>
{self.prompt}
</mission>

<output>
Save collected items to: {self.items_path}
Format: JSONL (one JSON object per line, append mode)
</output>

## Guidelines

- Use WebFetch or WebSearch to find relevant sources
- Extract structured data with consistent field names across items
- Include source_url in each item when possible
- Save items incrementally as you find them
- Aim for complete data, but partial items are still valuable

## Output Format

Each item should be a single-line JSON object:
```
{{"name": "...", "website": "...", "description": "...", "source_url": "..."}}
```

When complete, briefly summarize what was collected.
"""

    async def _agent_loop(self) -> dict[str, Any] | None:
        """Run Claude Agent SDK loop."""
        options = ClaudeAgentOptions(
            permission_mode="bypassPermissions",
            allowed_tools=[
                "Read",
                "Write",
                "Bash",
                "WebFetch",
                "WebSearch",
            ],
            cwd=str(self._collected_dir),
            model=self.model,
        )

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(self._build_collector_prompt())

                async for message in client.receive_response():
                    # Track usage
                    if hasattr(message, "usage"):
                        usage = message.usage
                        if isinstance(usage, dict):
                            for key, value in usage.items():
                                if isinstance(key, str) and isinstance(value, (int, float)):
                                    current = self.usage_metadata.get(key, 0)
                                    if isinstance(current, (int, float)):
                                        self.usage_metadata[key] = current + value

                    if isinstance(message, AssistantMessage):
                        last_tool_name = None
                        for block in message.content:
                            if isinstance(block, ToolUseBlock):
                                last_tool_name = block.name
                                tool_input = block.input if isinstance(block.input, dict) else {}
                                self.ui.tool_start(block.name, tool_input)
                                self.message_store.save_tool_start(block.name, tool_input)

                                # Track item saves
                                if block.name == "Write":
                                    file_path = tool_input.get("file_path", "")
                                    if "items.jsonl" in file_path:
                                        content = tool_input.get("content", "")
                                        self.ui.item_saved(content[:50])

                            elif isinstance(block, ToolResultBlock):
                                is_error = block.is_error if block.is_error else False
                                tool_name = last_tool_name or "Tool"
                                self.ui.tool_result(tool_name, is_error)
                                self.message_store.save_tool_result(tool_name, is_error)
                            elif isinstance(block, TextBlock):
                                self.ui.thinking(block.text)
                                self.message_store.save_thinking(block.text)

                    elif isinstance(message, ResultMessage):
                        if message.is_error:
                            self.ui.error(message.result or "Unknown error")
                            self.message_store.save_error(message.result or "Unknown error")
                            return {"error": message.result}
                        else:
                            return {"success": True}

        except Exception as e:
            error_msg = str(e)
            self.ui.error(error_msg)
            self.message_store.save_error(error_msg)
            return {"error": error_msg}

        return {"success": True}

    def _finalize_collection(self) -> dict[str, Any]:
        """Post-process collected items and export to JSON/CSV."""
        if not self._collected_dir:
            return {"error": "No collection directory"}

        items_path = self._collected_dir / "items.jsonl"

        # Parse collected items from JSONL
        collected_items: list[dict[str, Any]] = []
        sources: set[str] = set()

        if items_path.exists():
            with open(items_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            item = json.loads(line)
                            if isinstance(item, dict):
                                collected_items.append(item)
                                # Track sources
                                if "source_url" in item:
                                    sources.add(item["source_url"])
                                elif "url" in item:
                                    sources.add(item["url"])
                        except json.JSONDecodeError:
                            continue

        if not collected_items:
            self.ui.error("No items were collected. Check if the agent saved data correctly.")
            return {"error": "No items collected", "items": []}

        # Export JSON
        json_path = self._collected_dir / "data.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(collected_items, f, indent=2)

        # Export CSV
        csv_path = self._collected_dir / "data.csv"
        self._export_csv(csv_path, collected_items)

        # Update README with final stats
        readme_path = self._collected_dir / "README.md"
        self._export_readme(readme_path, collected_items, sources)

        # Calculate cost
        if self.usage_metadata:
            input_tokens = self.usage_metadata.get("input_tokens", 0)
            output_tokens = self.usage_metadata.get("output_tokens", 0)
            cache_creation = self.usage_metadata.get("cache_creation_input_tokens", 0)
            cache_read = self.usage_metadata.get("cache_read_input_tokens", 0)

            cost = calculate_cost(
                model_id=self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_creation_tokens=cache_creation,
                cache_read_tokens=cache_read,
            )
            self.usage_metadata["estimated_cost_usd"] = cost

        # Show completion
        self.ui.collection_complete(len(collected_items), str(self._collected_dir))
        if self.usage_metadata:
            self.ui.usage_summary(self.usage_metadata)

        result = {
            "output_path": str(self._collected_dir),
            "items_collected": len(collected_items),
            "files": {
                "json": str(json_path),
                "csv": str(csv_path),
                "readme": str(readme_path),
            },
            "usage": self.usage_metadata,
        }
        self.message_store.save_result(result)
        return result

    def _export_csv(self, csv_path: Path, items: list[dict[str, Any]]) -> None:
        """Export items to CSV with auto-flattened columns."""
        if not items:
            return

        # Collect all unique keys
        all_keys: set[str] = set()
        for item in items:
            all_keys.update(item.keys())

        # Sort keys for consistent column order
        fieldnames = sorted(all_keys)

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for item in items:
                # Convert non-string values to strings, filter out keys not in fieldnames
                row = {k: str(v) if v is not None else "" for k, v in item.items() if k in fieldnames}
                writer.writerow(row)

    def _export_readme(self, readme_path: Path, items: list[dict[str, Any]], sources: set[str]) -> None:
        """Generate README with collection metadata."""
        folder_name = self._folder_name or "collection"
        readme_content = f"""# {folder_name.replace('_', ' ').title()}

## Query
{self.prompt}

## Metadata
- **Run ID**: {self.run_id}
- **Items Collected**: {len(items)}
- **Sources**: {len(sources)}
- **Collected At**: {datetime.now().isoformat()}

## Files
- `data.json` - All collected items in JSON format
- `data.csv` - All collected items in CSV format

## Schema
"""
        # Add field schema
        if items:
            all_keys: set[str] = set()
            for item in items:
                all_keys.update(item.keys())

            for key in sorted(all_keys):
                readme_content += f"- `{key}`\n"

        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme_content)
