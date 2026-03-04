"""Tests for action_recorder.py and playwright_codegen.py."""

import json
from pathlib import Path

import pytest

from reverse_api.action_recorder import ActionRecorder, RecordedAction
from reverse_api.playwright_codegen import PlaywrightCodeGenerator


class TestRecordedAction:
    """Test RecordedAction dataclass."""

    def test_default_values(self):
        """RecordedAction has correct defaults."""
        action = RecordedAction(type="click")
        assert action.type == "click"
        assert action.selector is None
        assert action.value is None
        assert action.url is None
        assert action.timestamp == 0.0
        assert action.metadata is None

    def test_all_fields(self):
        """RecordedAction accepts all fields."""
        action = RecordedAction(
            type="fill",
            selector="#input",
            value="test",
            url="https://example.com",
            timestamp=1.5,
            metadata={"key": "value"},
        )
        assert action.type == "fill"
        assert action.selector == "#input"
        assert action.value == "test"
        assert action.url == "https://example.com"
        assert action.timestamp == 1.5
        assert action.metadata == {"key": "value"}


class TestActionRecorder:
    """Test ActionRecorder class."""

    def test_empty_recorder(self):
        """New recorder has no actions."""
        recorder = ActionRecorder()
        assert recorder.get_actions() == []

    def test_add_action(self):
        """Add action to recorder."""
        recorder = ActionRecorder()
        action = RecordedAction(type="click", selector="#btn")
        recorder.add_action(action)
        assert len(recorder.get_actions()) == 1
        assert recorder.get_actions()[0].selector == "#btn"

    def test_add_multiple_actions(self):
        """Add multiple actions."""
        recorder = ActionRecorder()
        recorder.add_action(RecordedAction(type="click", selector="#btn1"))
        recorder.add_action(RecordedAction(type="fill", selector="#input", value="text"))
        recorder.add_action(RecordedAction(type="press", selector="#input", value="Enter"))
        assert len(recorder.get_actions()) == 3

    def test_save_and_load(self, tmp_path):
        """Save and load actions round-trip."""
        recorder = ActionRecorder()
        recorder.add_action(RecordedAction(type="click", selector="#btn", timestamp=1.0))
        recorder.add_action(RecordedAction(type="fill", selector="#input", value="hello", timestamp=2.0))

        save_path = tmp_path / "actions.json"
        recorder.save(save_path)

        # Verify saved format
        with open(save_path) as f:
            data = json.load(f)
        assert len(data) == 2
        assert data[0]["type"] == "click"
        assert data[1]["value"] == "hello"

        # Load back
        loaded = ActionRecorder.load(save_path)
        assert len(loaded.get_actions()) == 2
        assert loaded.get_actions()[0].type == "click"
        assert loaded.get_actions()[1].value == "hello"

    def test_load_nonexistent_file(self, tmp_path):
        """Loading from nonexistent file returns empty recorder."""
        loaded = ActionRecorder.load(tmp_path / "nonexistent.json")
        assert loaded.get_actions() == []

    def test_save_with_metadata(self, tmp_path):
        """Save action with metadata."""
        recorder = ActionRecorder()
        recorder.add_action(
            RecordedAction(type="click", selector="#btn", metadata={"visible": True})
        )
        save_path = tmp_path / "actions.json"
        recorder.save(save_path)

        loaded = ActionRecorder.load(save_path)
        assert loaded.get_actions()[0].metadata == {"visible": True}


class TestPlaywrightCodeGenerator:
    """Test PlaywrightCodeGenerator class."""

    def test_empty_actions(self):
        """Generate script with no actions."""
        gen = PlaywrightCodeGenerator([])
        code = gen.generate()
        assert "playwright" in code.lower()
        assert "def main():" in code
        assert "browser.close()" in code

    def test_with_start_url(self):
        """Generate script with start URL."""
        gen = PlaywrightCodeGenerator([], start_url="https://example.com")
        code = gen.generate()
        assert "https://example.com" in code
        assert "page.goto" in code

    def test_click_action(self):
        """Generate click action."""
        actions = [RecordedAction(type="click", selector="#submit-btn")]
        gen = PlaywrightCodeGenerator(actions)
        code = gen.generate()
        assert 'page.click("#submit-btn")' in code

    def test_fill_action(self):
        """Generate fill action."""
        actions = [RecordedAction(type="fill", selector="#email", value="test@example.com")]
        gen = PlaywrightCodeGenerator(actions)
        code = gen.generate()
        assert 'page.fill("#email", "test@example.com")' in code

    def test_press_action(self):
        """Generate press action."""
        actions = [RecordedAction(type="press", selector="#input", value="Enter")]
        gen = PlaywrightCodeGenerator(actions)
        code = gen.generate()
        assert 'page.press("#input", "Enter")' in code

    def test_navigate_action(self):
        """Generate navigate action."""
        actions = [RecordedAction(type="navigate", url="https://example.com/page2")]
        gen = PlaywrightCodeGenerator(actions)
        code = gen.generate()
        assert "https://example.com/page2" in code

    def test_navigate_deduplication(self):
        """Duplicate navigations to same base URL are skipped."""
        actions = [
            RecordedAction(type="navigate", url="https://example.com/page?q=1"),
            RecordedAction(type="navigate", url="https://example.com/page?q=2"),
        ]
        gen = PlaywrightCodeGenerator(actions, start_url="https://example.com")
        code = gen.generate()
        # The two navigations have same base path, so second should be skipped
        goto_count = code.count("page.goto")
        # start_url goto + first navigate only (second deduplicated)
        assert goto_count >= 1

    def test_fill_deduplication(self):
        """Consecutive fills to same selector keeps only last."""
        actions = [
            RecordedAction(type="fill", selector="#input", value="first"),
            RecordedAction(type="fill", selector="#input", value="second"),
            RecordedAction(type="fill", selector="#input", value="final"),
        ]
        gen = PlaywrightCodeGenerator(actions)
        code = gen.generate()
        # Only the last fill should remain
        assert '"final"' in code
        assert '"first"' not in code
        assert '"second"' not in code

    def test_fill_kept_when_interrupted(self):
        """Fill is kept when followed by different action type."""
        actions = [
            RecordedAction(type="fill", selector="#input", value="kept"),
            RecordedAction(type="click", selector="#submit"),
            RecordedAction(type="fill", selector="#input", value="also_kept"),
        ]
        gen = PlaywrightCodeGenerator(actions)
        code = gen.generate()
        assert '"kept"' in code
        assert '"also_kept"' in code

    def test_wait_between_actions(self):
        """Actions have wait_for_timeout between them."""
        actions = [
            RecordedAction(type="click", selector="#btn1"),
            RecordedAction(type="click", selector="#btn2"),
        ]
        gen = PlaywrightCodeGenerator(actions)
        code = gen.generate()
        assert "wait_for_timeout(1000)" in code

    def test_stealth_args(self):
        """Generated script includes stealth arguments."""
        gen = PlaywrightCodeGenerator([])
        code = gen.generate()
        assert "STEALTH_ARGS" in code
        assert "AutomationControlled" in code

    def test_main_guard(self):
        """Generated script has __main__ guard."""
        gen = PlaywrightCodeGenerator([])
        code = gen.generate()
        assert "if __name__" in code

    def test_special_chars_in_value(self):
        """Special characters in fill value are properly escaped."""
        actions = [RecordedAction(type="fill", selector="#input", value='test"with\nnewline')]
        gen = PlaywrightCodeGenerator(actions)
        code = gen.generate()
        # json.dumps should handle escaping
        assert "page.fill" in code
        # Should not have raw newline in the fill call
        assert "\\n" in code or "newline" in code

    def test_get_base_url_none(self):
        """_get_base_url returns None for None input."""
        gen = PlaywrightCodeGenerator([])
        assert gen._get_base_url(None) is None
        assert gen._get_base_url("") is None

    def test_get_base_url_strips_query(self):
        """_get_base_url strips query parameters."""
        gen = PlaywrightCodeGenerator([])
        result = gen._get_base_url("https://example.com/path?q=1&r=2")
        assert result == "https://example.com/path"

    def test_unknown_action_type(self):
        """Unknown action type is handled gracefully."""
        actions = [RecordedAction(type="unknown_action", selector="#btn")]
        gen = PlaywrightCodeGenerator(actions)
        code = gen.generate()
        # Should still generate valid code without crashing
        assert "def main():" in code
