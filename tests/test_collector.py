"""Tests for collector.py - Collector class."""

import csv
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reverse_api.collector import Collector


class TestCollectorInit:
    """Test Collector initialization."""

    def test_init(self):
        """Collector initializes correctly."""
        with patch("reverse_api.collector.MessageStore"):
            with patch("reverse_api.collector.CollectorUI"):
                collector = Collector(
                    run_id="test123",
                    prompt="collect startup data",
                    model="claude-sonnet-4-5",
                )
                assert collector.run_id == "test123"
                assert collector.prompt == "collect startup data"
                assert collector.model == "claude-sonnet-4-5"
                assert collector.usage_metadata == {}

    def test_init_with_output_dir(self):
        """Collector initializes with custom output dir."""
        with patch("reverse_api.collector.MessageStore"):
            with patch("reverse_api.collector.CollectorUI"):
                collector = Collector(
                    run_id="test123",
                    prompt="test",
                    model="claude-sonnet-4-5",
                    output_dir="/custom/output",
                )
                assert collector.output_dir == "/custom/output"


class TestCollectorBuildPrompt:
    """Test prompt building."""

    def test_build_collector_prompt(self):
        """Build collector prompt includes mission."""
        with patch("reverse_api.collector.MessageStore"):
            with patch("reverse_api.collector.CollectorUI"):
                collector = Collector(
                    run_id="test123",
                    prompt="collect Y Combinator startups",
                    model="claude-sonnet-4-5",
                )
                collector._collected_dir = Path("/tmp/test")
                collector.items_path = Path("/tmp/test/items.jsonl")
                prompt = collector._build_collector_prompt()
                assert "Y Combinator startups" in prompt
                assert "items.jsonl" in prompt
                assert "JSONL" in prompt


class TestCollectorRun:
    """Test run method."""

    @pytest.mark.asyncio
    async def test_run_success(self, tmp_path):
        """Run executes agent loop and finalizes."""
        with patch("reverse_api.collector.MessageStore") as mock_ms:
            with patch("reverse_api.collector.CollectorUI") as mock_ui_cls:
                mock_ui = MagicMock()
                mock_ui_cls.return_value = mock_ui

                collector = Collector(
                    run_id="test123",
                    prompt="collect startups",
                    model="claude-sonnet-4-5",
                )

                collected_dir = tmp_path / "collected"
                collected_dir.mkdir()

                # Create items file
                items_path = collected_dir / "items.jsonl"
                items_path.write_text(json.dumps({"name": "Test"}) + "\n")

                with patch("reverse_api.collector.generate_folder_name", return_value="test_collection"):
                    with patch("reverse_api.collector.get_collected_dir", return_value=collected_dir):
                        async def mock_agent_loop():
                            return {"success": True}

                        with patch.object(collector, "_agent_loop", new=mock_agent_loop):
                            collector._folder_name = "test_collection"
                            result = await collector.run()
                            assert result is not None
                            assert "items_collected" in result

    @pytest.mark.asyncio
    async def test_run_error(self, tmp_path):
        """Run returns error result from agent loop."""
        with patch("reverse_api.collector.MessageStore"):
            with patch("reverse_api.collector.CollectorUI"):
                collector = Collector(
                    run_id="test123",
                    prompt="collect stuff",
                    model="claude-sonnet-4-5",
                )

                with patch("reverse_api.collector.generate_folder_name", return_value="test"):
                    with patch("reverse_api.collector.get_collected_dir", return_value=tmp_path):
                        async def mock_agent_loop():
                            return {"error": "API failed"}

                        with patch.object(collector, "_agent_loop", new=mock_agent_loop):
                            result = await collector.run()
                            assert result is not None
                            assert "error" in result

    @pytest.mark.asyncio
    async def test_run_none_result(self, tmp_path):
        """Run returns None result from agent loop."""
        with patch("reverse_api.collector.MessageStore"):
            with patch("reverse_api.collector.CollectorUI"):
                collector = Collector(
                    run_id="test123",
                    prompt="collect stuff",
                    model="claude-sonnet-4-5",
                )

                with patch("reverse_api.collector.generate_folder_name", return_value="test"):
                    with patch("reverse_api.collector.get_collected_dir", return_value=tmp_path):
                        async def mock_agent_loop():
                            return None

                        with patch.object(collector, "_agent_loop", new=mock_agent_loop):
                            result = await collector.run()
                            assert result is None


class TestCollectorAgentLoop:
    """Test _agent_loop method."""

    @pytest.mark.asyncio
    async def test_agent_loop_exception(self, tmp_path):
        """Agent loop handles SDK exception."""
        with patch("reverse_api.collector.MessageStore") as mock_ms:
            with patch("reverse_api.collector.CollectorUI") as mock_ui_cls:
                mock_ui = MagicMock()
                mock_ui_cls.return_value = mock_ui

                collector = Collector(
                    run_id="test123",
                    prompt="test",
                    model="claude-sonnet-4-5",
                )
                collector._collected_dir = tmp_path

                with patch("reverse_api.collector.ClaudeSDKClient") as mock_sdk:
                    mock_sdk.return_value.__aenter__ = AsyncMock(side_effect=Exception("SDK error"))
                    mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

                    result = await collector._agent_loop()
                    assert result is not None
                    assert "error" in result

    @pytest.mark.asyncio
    async def test_agent_loop_result_error(self, tmp_path):
        """Agent loop handles ResultMessage with error."""
        with patch("reverse_api.collector.MessageStore") as mock_ms:
            with patch("reverse_api.collector.CollectorUI") as mock_ui_cls:
                mock_ui = MagicMock()
                mock_ui_cls.return_value = mock_ui

                collector = Collector(
                    run_id="test123",
                    prompt="test",
                    model="claude-sonnet-4-5",
                )
                collector._collected_dir = tmp_path
                collector.items_path = tmp_path / "items.jsonl"

                from claude_agent_sdk import ResultMessage
                mock_result = MagicMock(spec=ResultMessage)
                mock_result.is_error = True
                mock_result.result = "Collection failed"

                mock_client = AsyncMock()
                mock_client.query = AsyncMock()

                async def mock_receive():
                    yield mock_result

                mock_client.receive_response = mock_receive

                with patch("reverse_api.collector.ClaudeSDKClient") as mock_sdk:
                    mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

                    result = await collector._agent_loop()
                    assert result is not None
                    assert "error" in result

    @pytest.mark.asyncio
    async def test_agent_loop_result_success(self, tmp_path):
        """Agent loop handles ResultMessage with success."""
        with patch("reverse_api.collector.MessageStore") as mock_ms:
            with patch("reverse_api.collector.CollectorUI") as mock_ui_cls:
                mock_ui = MagicMock()
                mock_ui_cls.return_value = mock_ui

                collector = Collector(
                    run_id="test123",
                    prompt="test",
                    model="claude-sonnet-4-5",
                )
                collector._collected_dir = tmp_path
                collector.items_path = tmp_path / "items.jsonl"

                from claude_agent_sdk import ResultMessage
                mock_result = MagicMock(spec=ResultMessage)
                mock_result.is_error = False
                mock_result.result = "Done"

                mock_client = AsyncMock()
                mock_client.query = AsyncMock()

                async def mock_receive():
                    yield mock_result

                mock_client.receive_response = mock_receive

                with patch("reverse_api.collector.ClaudeSDKClient") as mock_sdk:
                    mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

                    result = await collector._agent_loop()
                    assert result == {"success": True}


class TestCollectorExportCsv:
    """Test CSV export."""

    def test_export_csv_basic(self, tmp_path):
        """Export items to CSV."""
        with patch("reverse_api.collector.MessageStore"):
            with patch("reverse_api.collector.CollectorUI"):
                collector = Collector(
                    run_id="test123",
                    prompt="test",
                    model="claude-sonnet-4-5",
                )
                items = [
                    {"name": "Acme", "url": "https://acme.com"},
                    {"name": "Beta", "url": "https://beta.com"},
                ]
                csv_path = tmp_path / "data.csv"
                collector._export_csv(csv_path, items)

                assert csv_path.exists()
                with open(csv_path) as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    assert len(rows) == 2
                    assert rows[0]["name"] == "Acme"
                    assert rows[1]["url"] == "https://beta.com"

    def test_export_csv_mixed_keys(self, tmp_path):
        """Export items with different keys."""
        with patch("reverse_api.collector.MessageStore"):
            with patch("reverse_api.collector.CollectorUI"):
                collector = Collector(
                    run_id="test123",
                    prompt="test",
                    model="claude-sonnet-4-5",
                )
                items = [
                    {"name": "Acme", "category": "tech"},
                    {"name": "Beta", "funding": "$10M"},
                ]
                csv_path = tmp_path / "data.csv"
                collector._export_csv(csv_path, items)

                with open(csv_path) as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    assert len(rows) == 2
                    assert set(reader.fieldnames) == {"category", "funding", "name"}

    def test_export_csv_empty(self, tmp_path):
        """Export with no items does nothing."""
        with patch("reverse_api.collector.MessageStore"):
            with patch("reverse_api.collector.CollectorUI"):
                collector = Collector(
                    run_id="test123",
                    prompt="test",
                    model="claude-sonnet-4-5",
                )
                csv_path = tmp_path / "data.csv"
                collector._export_csv(csv_path, [])
                assert not csv_path.exists()

    def test_export_csv_none_values(self, tmp_path):
        """None values become empty strings."""
        with patch("reverse_api.collector.MessageStore"):
            with patch("reverse_api.collector.CollectorUI"):
                collector = Collector(
                    run_id="test123",
                    prompt="test",
                    model="claude-sonnet-4-5",
                )
                items = [{"name": "Acme", "value": None}]
                csv_path = tmp_path / "data.csv"
                collector._export_csv(csv_path, items)

                with open(csv_path) as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    assert rows[0]["value"] == ""


class TestCollectorExportReadme:
    """Test README export."""

    def test_export_readme(self, tmp_path):
        """Export README with metadata."""
        with patch("reverse_api.collector.MessageStore"):
            with patch("reverse_api.collector.CollectorUI"):
                collector = Collector(
                    run_id="test123",
                    prompt="collect startups",
                    model="claude-sonnet-4-5",
                )
                collector._folder_name = "startups"

                items = [
                    {"name": "Acme", "url": "https://acme.com"},
                    {"name": "Beta", "url": "https://beta.com"},
                ]
                sources = {"https://ycombinator.com", "https://techcrunch.com"}

                readme_path = tmp_path / "README.md"
                collector._export_readme(readme_path, items, sources)

                content = readme_path.read_text()
                assert "Startups" in content
                assert "collect startups" in content
                assert "test123" in content
                assert "2" in content
                assert "`name`" in content
                assert "`url`" in content

    def test_export_readme_no_folder_name(self, tmp_path):
        """Export README with None folder name uses default."""
        with patch("reverse_api.collector.MessageStore"):
            with patch("reverse_api.collector.CollectorUI"):
                collector = Collector(
                    run_id="test123",
                    prompt="test",
                    model="claude-sonnet-4-5",
                )
                collector._folder_name = None

                readme_path = tmp_path / "README.md"
                collector._export_readme(readme_path, [{"a": 1}], set())

                content = readme_path.read_text()
                assert "Collection" in content


class TestCollectorFinalizeCollection:
    """Test _finalize_collection method."""

    def test_finalize_no_dir(self):
        """Finalize with no collection dir returns error."""
        with patch("reverse_api.collector.MessageStore"):
            with patch("reverse_api.collector.CollectorUI"):
                collector = Collector(
                    run_id="test123",
                    prompt="test",
                    model="claude-sonnet-4-5",
                )
                collector._collected_dir = None
                result = collector._finalize_collection()
                assert result["error"] == "No collection directory"

    def test_finalize_no_items(self, tmp_path):
        """Finalize with no items returns error."""
        with patch("reverse_api.collector.MessageStore"):
            with patch("reverse_api.collector.CollectorUI") as mock_ui:
                collector = Collector(
                    run_id="test123",
                    prompt="test",
                    model="claude-sonnet-4-5",
                )
                collector._collected_dir = tmp_path
                collector._folder_name = "test"
                (tmp_path / "items.jsonl").write_text("")
                result = collector._finalize_collection()
                assert "error" in result

    def test_finalize_no_items_file(self, tmp_path):
        """Finalize with no items file returns error."""
        with patch("reverse_api.collector.MessageStore"):
            with patch("reverse_api.collector.CollectorUI"):
                collector = Collector(
                    run_id="test123",
                    prompt="test",
                    model="claude-sonnet-4-5",
                )
                collector._collected_dir = tmp_path
                collector._folder_name = "test"
                # Don't create items.jsonl
                result = collector._finalize_collection()
                assert "error" in result

    def test_finalize_with_items(self, tmp_path):
        """Finalize with items creates all output files."""
        with patch("reverse_api.collector.MessageStore") as mock_ms:
            with patch("reverse_api.collector.CollectorUI") as mock_ui_cls:
                mock_ui = MagicMock()
                mock_ui_cls.return_value = mock_ui

                collector = Collector(
                    run_id="test123",
                    prompt="test",
                    model="claude-sonnet-4-5",
                )
                collector._collected_dir = tmp_path
                collector._folder_name = "test"

                items = [
                    {"name": "Acme", "source_url": "https://acme.com"},
                    {"name": "Beta", "url": "https://beta.com"},
                ]
                with open(tmp_path / "items.jsonl", "w") as f:
                    for item in items:
                        f.write(json.dumps(item) + "\n")

                result = collector._finalize_collection()
                assert "output_path" in result
                assert result["items_collected"] == 2
                assert (tmp_path / "data.json").exists()
                assert (tmp_path / "data.csv").exists()
                assert (tmp_path / "README.md").exists()

    def test_finalize_with_usage(self, tmp_path):
        """Finalize calculates cost from usage."""
        with patch("reverse_api.collector.MessageStore") as mock_ms:
            with patch("reverse_api.collector.CollectorUI") as mock_ui_cls:
                mock_ui = MagicMock()
                mock_ui_cls.return_value = mock_ui

                collector = Collector(
                    run_id="test123",
                    prompt="test",
                    model="claude-sonnet-4-5",
                )
                collector._collected_dir = tmp_path
                collector._folder_name = "test"
                collector.usage_metadata = {
                    "input_tokens": 1000,
                    "output_tokens": 500,
                }

                with open(tmp_path / "items.jsonl", "w") as f:
                    f.write(json.dumps({"name": "test"}) + "\n")

                result = collector._finalize_collection()
                assert "estimated_cost_usd" in collector.usage_metadata

    def test_finalize_with_cache_usage(self, tmp_path):
        """Finalize includes cache tokens in cost."""
        with patch("reverse_api.collector.MessageStore"):
            with patch("reverse_api.collector.CollectorUI") as mock_ui_cls:
                mock_ui_cls.return_value = MagicMock()

                collector = Collector(
                    run_id="test123",
                    prompt="test",
                    model="claude-sonnet-4-5",
                )
                collector._collected_dir = tmp_path
                collector._folder_name = "test"
                collector.usage_metadata = {
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "cache_creation_input_tokens": 200,
                    "cache_read_input_tokens": 100,
                }

                with open(tmp_path / "items.jsonl", "w") as f:
                    f.write(json.dumps({"name": "test"}) + "\n")

                result = collector._finalize_collection()
                assert collector.usage_metadata["estimated_cost_usd"] > 0

    def test_finalize_skips_invalid_json_lines(self, tmp_path):
        """Finalize skips invalid JSON lines in items file."""
        with patch("reverse_api.collector.MessageStore"):
            with patch("reverse_api.collector.CollectorUI") as mock_ui_cls:
                mock_ui = MagicMock()
                mock_ui_cls.return_value = mock_ui

                collector = Collector(
                    run_id="test123",
                    prompt="test",
                    model="claude-sonnet-4-5",
                )
                collector._collected_dir = tmp_path
                collector._folder_name = "test"

                with open(tmp_path / "items.jsonl", "w") as f:
                    f.write(json.dumps({"name": "valid"}) + "\n")
                    f.write("not valid json\n")
                    f.write(json.dumps({"name": "also_valid"}) + "\n")

                result = collector._finalize_collection()
                assert result["items_collected"] == 2

    def test_finalize_skips_non_dict_items(self, tmp_path):
        """Finalize skips non-dict JSON items."""
        with patch("reverse_api.collector.MessageStore"):
            with patch("reverse_api.collector.CollectorUI") as mock_ui_cls:
                mock_ui = MagicMock()
                mock_ui_cls.return_value = mock_ui

                collector = Collector(
                    run_id="test123",
                    prompt="test",
                    model="claude-sonnet-4-5",
                )
                collector._collected_dir = tmp_path
                collector._folder_name = "test"

                with open(tmp_path / "items.jsonl", "w") as f:
                    f.write(json.dumps({"name": "valid"}) + "\n")
                    f.write(json.dumps("just a string") + "\n")
                    f.write(json.dumps([1, 2, 3]) + "\n")

                result = collector._finalize_collection()
                assert result["items_collected"] == 1
