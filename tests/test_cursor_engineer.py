"""Tests for Cursor SDK bridge integration (mocked, no real API calls)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reverse_api.cursor_engineer import CursorEngineer, _ensure_cursor_bridge_deps


@pytest.fixture
def har_path(tmp_path: Path) -> Path:
    p = tmp_path / "recording.har"
    p.write_text('{"log":{"entries":[]}}')
    return p


@pytest.mark.asyncio
async def test_cursor_engineer_analyze_missing_api_key(har_path: Path) -> None:
    with patch.dict("os.environ", {"CURSOR_API_KEY": ""}):
        with patch("reverse_api.cursor_engineer._ensure_cursor_bridge_deps", return_value=None):
            eng = CursorEngineer(
                run_id="abc123",
                har_path=har_path,
                prompt="test",
                cursor_model="composer-2",
                sdk="cursor",
                interactive=False,
                verbose=False,
            )
            out = await eng.analyze_and_generate()
    assert out is None


@pytest.mark.asyncio
async def test_cursor_engineer_one_turn_error(har_path: Path) -> None:
    with patch.dict("os.environ", {"CURSOR_API_KEY": "test-key"}):
        with patch("reverse_api.cursor_engineer._ensure_cursor_bridge_deps", return_value=None):
            eng = CursorEngineer(
                run_id="abc123",
                har_path=har_path,
                prompt="test",
                cursor_model="composer-2",
                sdk="cursor",
                interactive=False,
                verbose=False,
            )
            with patch.object(eng, "_one_turn", new=AsyncMock(return_value={"error": "simulated"})):
                out = await eng.analyze_and_generate()
    assert out is None


@pytest.mark.asyncio
async def test_cursor_engineer_success_non_interactive(har_path: Path) -> None:
    with patch.dict("os.environ", {"CURSOR_API_KEY": "test-key"}):
        with patch("reverse_api.cursor_engineer._ensure_cursor_bridge_deps", return_value=None):
            eng = CursorEngineer(
                run_id="abc123",
                har_path=har_path,
                prompt="test",
                cursor_model="composer-2",
                sdk="cursor",
                interactive=False,
                verbose=False,
            )
            with patch.object(
                eng,
                "_one_turn",
                new=AsyncMock(return_value={"ok": True, "agentId": "agent-xyz"}),
            ):
                with patch.object(eng.ui, "success", MagicMock()):
                    with patch.object(eng.ui.console, "print", MagicMock()):
                        out = await eng.analyze_and_generate()
    assert out is not None
    assert out.get("script_path", "").endswith("api_client.py")


def test_ensure_bridge_missing_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import reverse_api.cursor_engineer as ce

    monkeypatch.setattr(ce, "_BRIDGE_SCRIPT", tmp_path / "nonexistent.mjs")
    err = _ensure_cursor_bridge_deps()
    assert err is not None
