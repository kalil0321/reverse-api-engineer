"""Regression tests for OMP agent mode MCP workspace setup."""

import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from reverse_api.auto_engineer import OMPAutoEngineer


@pytest.mark.asyncio
async def test_omp_agent_registers_browser_mcp_and_cleans_temporary_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "output"
    engineer = OMPAutoEngineer(
        run_id="run-1",
        prompt="Inspect the site",
        output_dir=str(output_dir),
        verbose=False,
    )
    assert engineer.sdk == "omp"

    browser_config = {
        "type": "stdio",
        "command": "npx",
        "args": ["rae-playwright-mcp@latest", "run-mcp-server", "--run-id", "run-1"],
    }
    captured: dict[str, Any] = {}

    monkeypatch.setattr("reverse_api.omp_engineer.shutil.which", lambda _: "/usr/bin/omp")

    async def fake_create_subprocess_exec(*args: str, **kwargs: Any) -> SimpleNamespace:
        captured["args"] = args
        captured["kwargs"] = kwargs
        workspace = Path(kwargs["cwd"])
        config_path = workspace / ".omp" / "mcp.json"
        captured["config_text"] = config_path.read_text(encoding="utf-8")
        captured["config_path"] = config_path
        return SimpleNamespace(
            communicate=lambda: asyncio.sleep(0, result=(b"", b"")),
            returncode=0,
        )

    monkeypatch.setattr(
        "reverse_api.omp_engineer.asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )

    assert await engineer._run_omp("system", "user", {"playwright": browser_config})

    args = captured["args"]
    workspace = Path(captured["kwargs"]["cwd"])
    assert captured["config_text"] == json.dumps({"mcpServers": {"playwright": browser_config}})
    assert args[args.index("--add-dir") + 1] == str(engineer.scripts_dir.parent.parent)
    assert args[args.index("--cwd") + 1] == str(workspace)
    assert workspace != output_dir
    assert not workspace.exists()


@pytest.mark.asyncio
async def test_omp_auto_uses_native_browser_and_rejects_success_without_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engineer = OMPAutoEngineer(
        run_id="run-3",
        prompt="Inspect https://example.com",
        output_dir=str(tmp_path / "output"),
        verbose=False,
    )
    captured: dict[str, Any] = {}

    async def fake_run_omp(
        system_prompt: str,
        user_message: str,
        mcp_servers: dict[str, dict[str, Any]] | None = None,
    ) -> bool:
        captured["system_prompt"] = system_prompt
        captured["user_message"] = user_message
        captured["mcp_servers"] = mcp_servers
        return True

    monkeypatch.setattr(engineer, "_run_omp", fake_run_omp)

    assert await engineer.analyze_and_generate() is None
    assert captured["mcp_servers"] is None
    assert "OMP Eval browser facade" in captured["system_prompt"]
    assert "without an `app` or `app.target` option" in captured["user_message"]
    assert "app: { relay: false, tern: false }" not in captured["user_message"]
    assert "timeout: 120" in captured["user_message"]
    assert str(engineer.har_path) in captured["user_message"]
    assert str(engineer.scripts_dir / engineer._get_client_filename()) in captured["user_message"]



@pytest.mark.parametrize(
    ("agent_provider", "har_content", "accepted"),
    [
        ("auto", "not json", False),
        ("auto", '{"log":{"entries":[]}}', False),
        ("auto", '{"log":{"entries":[{"request":{"url":"https://example.com/"}}]}}', True),
        ("chrome-mcp", None, True),
    ],
)
@pytest.mark.asyncio
async def test_omp_auto_accepts_only_valid_capture_except_chrome(
    agent_provider: str,
    har_content: str | None,
    accepted: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engineer = OMPAutoEngineer(
        run_id="run-4",
        prompt="Inspect https://example.com",
        output_dir=str(tmp_path / "output"),
        agent_provider=agent_provider,
        verbose=False,
    )
    captured: dict[str, Any] = {}

    async def fake_run_omp(
        system_prompt: str,
        user_message: str,
        mcp_servers: dict[str, dict[str, Any]] | None = None,
    ) -> bool:
        captured["mcp_servers"] = mcp_servers
        script = engineer.scripts_dir / "api_client.py"
        script.write_text("print('ok')", encoding="utf-8")
        if har_content is not None:
            engineer.har_path.parent.mkdir(parents=True, exist_ok=True)
            engineer.har_path.write_text(har_content, encoding="utf-8")
        return True

    monkeypatch.setattr(engineer, "_run_omp", fake_run_omp)

    result = await engineer.analyze_and_generate()

    assert (result is not None) is accepted
    if agent_provider == "chrome-mcp":
        assert captured["mcp_servers"] == {
            "chrome-devtools": {
                "type": "stdio",
                "command": "npx",
                "args": [
                    "-y",
                    "chrome-devtools-mcp@latest",
                    "--no-usage-statistics",
                    "--autoConnect",
                ],
            },
        }
    else:
        assert captured["mcp_servers"] is None


def test_omp_json_output_keeps_only_final_assistant_text() -> None:
    from reverse_api.omp_engineer import _extract_omp_json_text

    events = [
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "intermediate text"}],
            },
        },
        {
            "type": "message_end",
            "message": {
                "role": "toolResult",
                "content": [{"type": "text", "text": "tool result"}],
            },
        },
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "toolCall", "name": "eval", "arguments": {"code": "private"}},
                    {"type": "text", "text": "final text"},
                ],
            },
        },
    ]
    output = "\n".join(json.dumps(event) for event in events)
    result = _extract_omp_json_text(output.encode())
    assert result == "final text"
    assert "tool result" not in result
    assert "private" not in result


@pytest.mark.parametrize(
    ("omp_model", "expected_model"),
    [
        ("", None),
        ("  provider/model  ", "provider/model"),
    ],
)
@pytest.mark.asyncio
async def test_omp_uses_configured_model_by_default_and_optional_override(
    omp_model: str,
    expected_model: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reverse_api.omp_engineer import OMPEngineer

    engineer = OMPEngineer(
        run_id="model-selection",
        har_path=tmp_path / "recording.har",
        prompt="Inspect the site",
        output_dir=str(tmp_path / "output"),
        omp_model=omp_model,
        verbose=False,
    )
    captured: dict[str, Any] = {}
    monkeypatch.setattr("reverse_api.omp_engineer.shutil.which", lambda _: "/usr/bin/omp")

    async def fake_create_subprocess_exec(*args: str, **kwargs: Any) -> SimpleNamespace:
        captured["args"] = args
        return SimpleNamespace(
            communicate=lambda: asyncio.sleep(0, result=(b"", b"")),
            returncode=0,
        )

    monkeypatch.setattr(
        "reverse_api.omp_engineer.asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )

    assert await engineer._run_omp("system", "user")
    args = captured["args"]
    if expected_model is None:
        assert "--model" not in args
    else:
        assert args[args.index("--model") + 1] == expected_model


@pytest.mark.asyncio
async def test_omp_engineer_without_mcp_uses_output_workspace_without_add_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverse_api.omp_engineer import OMPEngineer

    engineer = OMPEngineer(
        run_id="run-2",
        har_path=tmp_path / "recording.har",
        prompt="Inspect the site",
        output_dir=str(tmp_path / "output"),
        verbose=False,
    )
    captured: dict[str, Any] = {}

    monkeypatch.setattr("reverse_api.omp_engineer.shutil.which", lambda _: "/usr/bin/omp")

    async def fake_create_subprocess_exec(*args: str, **kwargs: Any) -> SimpleNamespace:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            communicate=lambda: asyncio.sleep(0, result=(b"", b"")),
            returncode=0,
        )

    monkeypatch.setattr(
        "reverse_api.omp_engineer.asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )

    assert await engineer._run_omp("system", "user")

    args = captured["args"]
    output_workspace = engineer.scripts_dir.parent.parent
    assert args[args.index("--cwd") + 1] == str(output_workspace)
    assert captured["kwargs"]["cwd"] == str(output_workspace)
    assert args[args.index("--mode") + 1] == "json"
    assert "--add-dir" not in args

@pytest.mark.asyncio
async def test_omp_cancellation_reaps_process_before_cleaning_mcp_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverse_api.omp_engineer import OMPEngineer

    engineer = OMPEngineer(
        run_id="cancelled",
        har_path=tmp_path / "recording.har",
        prompt="Inspect the site",
        output_dir=str(tmp_path / "output"),
        verbose=False,
    )
    events: list[str] = []
    started = asyncio.Event()
    process: Any

    class FakeProcess:
        returncode: int | None = None

        async def communicate(self) -> tuple[bytes, bytes]:
            started.set()
            await asyncio.Event().wait()
            return b"", b""

        def kill(self) -> None:
            events.append("kill")
            self.returncode = -9

        async def wait(self) -> int:
            events.append("wait")
            return -9

    process = FakeProcess()  # type: ignore[assignment]
    real_temporary_directory = tempfile.TemporaryDirectory

    class TrackedTemporaryDirectory:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.directory = real_temporary_directory(*args, **kwargs)
            self.name = self.directory.name

        def cleanup(self) -> None:
            events.append("cleanup")
            self.directory.cleanup()

    monkeypatch.setattr(
        "reverse_api.omp_engineer.tempfile.TemporaryDirectory", TrackedTemporaryDirectory
    )
    monkeypatch.setattr("reverse_api.omp_engineer.shutil.which", lambda _: "/usr/bin/omp")
    monkeypatch.setattr(
        "reverse_api.omp_engineer.asyncio.create_subprocess_exec",
        lambda *args, **kwargs: asyncio.sleep(0, result=process),
    )

    task = asyncio.create_task(engineer._run_omp("system", "user", {"playwright": {}}))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert events == ["kill", "wait", "cleanup"]


@pytest.mark.asyncio
async def test_omp_engineer_does_not_report_success_without_client_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverse_api.omp_engineer import OMPEngineer

    engineer = OMPEngineer(
        run_id="missing-client",
        har_path=tmp_path / "recording.har",
        prompt="Inspect the site",
        output_dir=str(tmp_path / "output"),
        verbose=False,
    )

    async def successful_omp_run(*args: Any, **kwargs: Any) -> bool:
        return True

    monkeypatch.setattr(engineer, "_run_omp", successful_omp_run)

    assert await engineer.analyze_and_generate() is None


@pytest.mark.asyncio
async def test_omp_resolves_relative_har_and_output_paths_for_temp_mcp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverse_api.omp_engineer import OMPEngineer

    monkeypatch.chdir(tmp_path)
    engineer = OMPEngineer(
        run_id="relative",
        har_path=Path("relative-output/har/relative/recording.har"),
        prompt="Inspect the site",
        output_dir="relative-output",
        verbose=False,
    )
    _, user_message = engineer._build_prompts()
    assert str(engineer.har_path) in user_message
    assert str(engineer.scripts_dir) in user_message
    captured: dict[str, Any] = {}

    monkeypatch.setattr("reverse_api.omp_engineer.shutil.which", lambda _: "/usr/bin/omp")

    async def fake_create_subprocess_exec(*args: str, **kwargs: Any) -> SimpleNamespace:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            communicate=lambda: asyncio.sleep(0, result=(b"", b"")),
            returncode=0,
        )

    monkeypatch.setattr(
        "reverse_api.omp_engineer.asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )

    assert await engineer._run_omp("system", "user", {"playwright": {}})
    args = captured["args"]
    assert engineer.har_path.is_absolute()
    assert engineer.scripts_dir.is_absolute()
    assert Path(args[args.index("--add-dir") + 1]) == engineer.scripts_dir.parent.parent
    assert Path(args[args.index("--cwd") + 1]).is_absolute()


@pytest.mark.asyncio
async def test_omp_resolves_windows_command_before_subprocess_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reverse_api.omp_engineer import OMPEngineer

    engineer = OMPEngineer(
        run_id="windows-launch",
        har_path=tmp_path / "recording.har",
        prompt="Inspect the site",
        output_dir=str(tmp_path / "output"),
        verbose=False,
    )
    calls: list[list[str]] = []
    launch_args: list[str] = []

    def resolve_command(args: list[str]) -> list[str]:
        calls.append(args)
        return ["resolved-omp", *args[1:]]

    monkeypatch.setattr(
        "reverse_api.omp_engineer.resolve_windows_command", resolve_command, raising=False
    )
    monkeypatch.setattr("reverse_api.omp_engineer.shutil.which", lambda _: "/usr/bin/omp")

    async def fake_create_subprocess_exec(*args: str, **kwargs: Any) -> SimpleNamespace:
        launch_args.extend(args)
        return SimpleNamespace(
            communicate=lambda: asyncio.sleep(0, result=(b"", b"")),
            returncode=0,
        )

    monkeypatch.setattr(
        "reverse_api.omp_engineer.asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )

    assert await engineer._run_omp("system", "user")
    assert calls and calls[0][0] == "/usr/bin/omp"
    assert launch_args[0] == "resolved-omp"
