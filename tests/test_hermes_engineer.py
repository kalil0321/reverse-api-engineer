"""Tests for the Hermes CLI backend (mocked subprocess, no real model call)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from reverse_api.hermes_engineer import (
    HERMES_BIN_ENV,
    HermesEngineer,
    hermes_binary,
    parse_event,
)


@pytest.fixture
def har_path(tmp_path: Path) -> Path:
    p = tmp_path / "recording.har"
    p.write_text('{"log":{"entries":[]}}')
    return p


class FakeStdin:
    """Swallows the prompt the backend writes to the CLI."""

    def __init__(self) -> None:
        self.written = b""

    def write(self, data: bytes) -> None:
        self.written += data

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None


class FakeStream:
    """A stdout/stderr stand-in: queued lines for readline, empty for read."""

    def __init__(self, lines: list[bytes] | None = None) -> None:
        self._lines = list(lines or [])

    async def readline(self) -> bytes:
        return self._lines.pop(0) if self._lines else b""

    async def read(self, _size: int) -> bytes:
        return b""


class FakeProc:
    def __init__(self, lines: list[bytes], returncode: int = 0) -> None:
        self.stdout = FakeStream(lines)
        self.stderr = FakeStream()
        self.stdin = FakeStdin()
        self.returncode = returncode
        self.terminated = False

    async def wait(self) -> int:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True


def events(*items: dict[str, Any]) -> list[bytes]:
    return [(json.dumps(item) + "\n").encode() for item in items]


def make_engineer(har_path: Path, tmp_path: Path, **kwargs: Any) -> HermesEngineer:
    return HermesEngineer(
        run_id="run123",
        har_path=har_path,
        prompt="fetch the products with prices",
        output_dir=str(tmp_path),
        sdk="hermes",
        interactive=False,
        verbose=False,
        **kwargs,
    )


# --------------------------------------------------------------------- helpers


def test_parse_event_skips_banner_and_broken_lines() -> None:
    assert parse_event("  \n") is None
    assert parse_event("Welcome to Hermes") is None
    assert parse_event("{not json}") is None
    assert parse_event("[1, 2]") is None
    assert parse_event('{"type": "text", "text": "hi"}') == {"type": "text", "text": "hi"}


def test_hermes_binary_honours_the_override(tmp_path: Path) -> None:
    binary = tmp_path / "hermes"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    with patch.dict("os.environ", {HERMES_BIN_ENV: str(binary)}):
        assert hermes_binary() == str(binary)
    with patch.dict("os.environ", {HERMES_BIN_ENV: str(tmp_path / "missing")}):
        assert hermes_binary() is None


def test_argv_carries_the_run_contract(har_path: Path, tmp_path: Path) -> None:
    eng = make_engineer(har_path, tmp_path, hermes_model="deepseek-v4.1-flash", hermes_provider="ollama-cloud", hermes_max_turns=12)
    with patch("reverse_api.hermes_engineer.hermes_binary", return_value="/usr/local/bin/hermes"):
        argv = eng._argv(None)
        assert argv[:6] == ["/usr/local/bin/hermes", "chat", "--query-file", "-", "--oneshot", "--format"]
        # The prompt arrives on stdin, so nothing the model sees is shell-parsed.
        assert "--in" in argv and argv[argv.index("--in") + 1] == str(eng.scripts_dir)
        assert "--ignore-rules" in argv
        assert argv[argv.index("--max-turns") + 1] == "12"
        assert argv[argv.index("-m") + 1] == "deepseek-v4.1-flash"
        assert argv[argv.index("--provider") + 1] == "ollama-cloud"
        assert "--resume" not in argv

        resumed = eng._argv("20261110_005231_8fc4f2")
        assert resumed[resumed.index("--resume") + 1] == "20261110_005231_8fc4f2"


def test_argv_without_model_lets_hermes_choose(har_path: Path, tmp_path: Path) -> None:
    eng = make_engineer(har_path, tmp_path)
    with patch("reverse_api.hermes_engineer.hermes_binary", return_value="/usr/bin/hermes"):
        argv = eng._argv(None)
    assert "-m" not in argv and "--provider" not in argv


def test_argv_reports_a_missing_cli(har_path: Path, tmp_path: Path) -> None:
    eng = make_engineer(har_path, tmp_path)
    with patch("reverse_api.hermes_engineer.hermes_binary", return_value=None):
        with pytest.raises(RuntimeError, match="not found"):
            eng._argv(None)


# ------------------------------------------------------------------ end to end


@pytest.mark.asyncio
async def test_run_writes_the_client_and_reports_usage(har_path: Path, tmp_path: Path) -> None:
    eng = make_engineer(har_path, tmp_path, hermes_model="claude-sonnet-4-6")
    client = eng.scripts_dir / eng._get_client_filename()
    client.parent.mkdir(parents=True, exist_ok=True)
    client.write_text("# generated client\n")

    proc = FakeProc(
        events(
            {"type": "system", "subtype": "init", "model": "claude-sonnet-4-6", "session_id": "sess-1"},
            {"type": "text", "text": "reading the HAR"},
            {"type": "tool_use", "name": "Read", "input": {"path": "recording.har"}},
            {"type": "tool_result", "name": "Read", "output": "{}", "is_error": False},
            {"type": "text", "text": " client written"},
            {
                "type": "result",
                "session_id": "sess-1",
                "exit_code": 0,
                "text": "done",
                "tokens": {"input": 1000, "output": 500, "total": 1600, "cache_read": 100, "cache_write": 0},
            },
        )
    )
    with (
        patch("reverse_api.hermes_engineer.hermes_binary", return_value="/usr/bin/hermes"),
        patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)),
    ):
        out = await eng.analyze_and_generate()

    # The prompt travels on stdin, never through the shell.
    assert b"fetch the products with prices" in proc.stdin.written
    assert out is not None
    assert out["script_path"] == str(client)
    assert out["session_id"] == "sess-1"
    usage = out["usage"]
    assert usage["input_tokens"] == 1000
    assert usage["output_tokens"] == 500
    assert usage["cache_read_input_tokens"] == 100
    # claude-sonnet-4-6 pricing: 3.00 in / 15.00 out / 0.30 cache read per million tokens.
    assert usage["estimated_cost_usd"] == pytest.approx((1000 * 3.00 + 500 * 15.00 + 100 * 0.30) / 1_000_000, rel=1e-6)
    saved = eng.message_store.load()
    assert any(m["type"] == "tool_start" and m["content"]["name"] == "Read" for m in saved)
    assert any(m["type"] == "thinking" and "client written" in m["content"] for m in saved)


@pytest.mark.asyncio
async def test_run_prices_an_unknown_model_at_zero(har_path: Path, tmp_path: Path) -> None:
    eng = make_engineer(har_path, tmp_path, hermes_model="some-local-model")
    client = eng.scripts_dir / eng._get_client_filename()
    client.parent.mkdir(parents=True, exist_ok=True)
    client.write_text("# client\n")
    proc = FakeProc(
        events(
            {"type": "system", "subtype": "init", "session_id": "s2"},
            {"type": "result", "session_id": "s2", "exit_code": 0, "tokens": {"input": 10, "output": 10}},
        )
    )
    with (
        patch("reverse_api.hermes_engineer.hermes_binary", return_value="/usr/bin/hermes"),
        patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)),
    ):
        out = await eng.analyze_and_generate()

    assert out is not None
    assert out["usage"]["estimated_cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_a_failing_result_event_stops_the_run(har_path: Path, tmp_path: Path) -> None:
    eng = make_engineer(har_path, tmp_path)
    proc = FakeProc(
        events(
            {"type": "system", "subtype": "init", "session_id": "s3"},
            {"type": "result", "session_id": "s3", "exit_code": 1, "text": "provider refused the run"},
            {"type": "text", "text": "this must never be dispatched"},
        ),
        returncode=1,
    )
    with (
        patch("reverse_api.hermes_engineer.hermes_binary", return_value="/usr/bin/hermes"),
        patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)),
    ):
        out = await eng.analyze_and_generate()

    assert out is None
    saved = eng.message_store.load()
    errors = [m["content"] for m in saved if m["type"] == "error"]
    assert any("provider refused the run" in str(e) for e in errors)
    assert not any(m["type"] == "thinking" and "must never be dispatched" in str(m["content"]) for m in saved)


@pytest.mark.asyncio
async def test_a_run_that_writes_no_client_is_an_error(har_path: Path, tmp_path: Path) -> None:
    eng = make_engineer(har_path, tmp_path)
    proc = FakeProc(
        events(
            {"type": "system", "subtype": "init", "session_id": "s4"},
            {"type": "result", "session_id": "s4", "exit_code": 0, "tokens": {"input": 1, "output": 1}},
        )
    )
    with (
        patch("reverse_api.hermes_engineer.hermes_binary", return_value="/usr/bin/hermes"),
        patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)),
    ):
        out = await eng.analyze_and_generate()

    assert out is None


@pytest.mark.asyncio
async def test_a_missing_cli_is_reported_without_starting_a_process(har_path: Path, tmp_path: Path) -> None:
    eng = make_engineer(har_path, tmp_path)
    with (
        patch("reverse_api.hermes_engineer.hermes_binary", return_value=None),
        patch("asyncio.create_subprocess_exec", new=AsyncMock()) as spawn,
    ):
        out = await eng.analyze_and_generate()

    assert out is None
    spawn.assert_not_called()


@pytest.mark.asyncio
async def test_a_run_without_a_result_event_is_an_error(har_path: Path, tmp_path: Path) -> None:
    """A stream that ends without the closing event did not finish, even at exit 0 with a client on disk."""
    eng = make_engineer(har_path, tmp_path)
    client = eng.scripts_dir / eng._get_client_filename()
    client.parent.mkdir(parents=True, exist_ok=True)
    client.write_text("# left by an earlier turn\n")
    proc = FakeProc(events({"type": "system", "subtype": "init", "session_id": "s5"}, {"type": "text", "text": "half a run"}))
    with (
        patch("reverse_api.hermes_engineer.hermes_binary", return_value="/usr/bin/hermes"),
        patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)),
    ):
        out = await eng.analyze_and_generate()

    assert out is None
    assert any("without a result event" in str(m["content"]) for m in eng.message_store.load() if m["type"] == "error")


@pytest.mark.asyncio
async def test_a_nonzero_exit_fails_even_after_a_successful_turn(har_path: Path, tmp_path: Path) -> None:
    """Previous turns' usage must not excuse a nonzero exit."""
    eng = make_engineer(har_path, tmp_path)
    client = eng.scripts_dir / eng._get_client_filename()
    client.parent.mkdir(parents=True, exist_ok=True)
    client.write_text("# client\n")
    eng.usage_metadata["input_tokens"] = 999  # what an earlier turn would have left behind
    proc = FakeProc(
        events({"type": "result", "session_id": "s6", "exit_code": 0, "tokens": {"input": 5, "output": 5}}),
        returncode=2,
    )
    with (
        patch("reverse_api.hermes_engineer.hermes_binary", return_value="/usr/bin/hermes"),
        patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)),
    ):
        out = await eng.analyze_and_generate()

    assert out is None


def test_a_relative_output_dir_becomes_absolute(har_path: Path, tmp_path: Path) -> None:
    """The CLI changes into the workspace, so the paths it receives must not be relative."""
    eng = HermesEngineer(
        run_id="run123",
        har_path=har_path,
        prompt="fetch products",
        output_dir=str(tmp_path / "rel"),
        sdk="hermes",
        interactive=False,
        verbose=False,
    )
    with patch("reverse_api.hermes_engineer.hermes_binary", return_value="/usr/bin/hermes"):
        argv = eng._argv(None)
    assert eng.scripts_dir.is_absolute()
    assert eng.har_path.is_absolute()
    assert Path(argv[argv.index("--in") + 1]).is_absolute()


def test_usage_counts_each_turn_and_keeps_cost_per_invocation(har_path: Path, tmp_path: Path) -> None:
    eng = make_engineer(har_path, tmp_path, hermes_model="claude-sonnet-4-6")
    eng.cost_before = 1.0  # an earlier resume's spend, which the shared code adds itself
    eng._apply_usage({"tokens": {"input": 1000, "output": 0}})
    first = dict(eng.usage_metadata)
    eng._apply_usage({"tokens": {"input": 1000, "output": 0}})
    assert eng.usage_metadata["input_tokens"] == 2000
    assert eng.usage_metadata["estimated_cost_usd"] == pytest.approx(first["estimated_cost_usd"] * 2, rel=1e-6)
    assert eng.usage_metadata["estimated_cost_usd"] < eng.usage_metadata["cost"] + eng.cost_before
