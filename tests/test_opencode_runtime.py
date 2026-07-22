"""Tests for managed OpenCode server startup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from reverse_api import opencode_runtime


@pytest.fixture(autouse=True)
def reset_runtime_state():
    opencode_runtime._PROCESS = None
    opencode_runtime._PROCESS_URL = None
    yield
    opencode_runtime._PROCESS = None
    opencode_runtime._PROCESS_URL = None


def _health_response(version: str = "1.18.4") -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"healthy": True, "version": version}
    return response


@pytest.mark.asyncio
async def test_reuses_healthy_server():
    client = AsyncMock()
    client.get = AsyncMock(return_value=_health_response())

    status = await opencode_runtime.ensure_opencode_server(client, base_url="http://127.0.0.1:4096")

    assert status.health["version"] == "1.18.4"
    assert status.started is False


@pytest.mark.asyncio
async def test_starts_latest_package_and_waits_for_health(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENCODE_SERVER_PASSWORD", "secret")
    request = httpx.Request("GET", "http://127.0.0.1:4096/global/health")
    client = AsyncMock()
    client.get = AsyncMock(side_effect=[httpx.ConnectError("refused", request=request), _health_response()])
    process = MagicMock()
    process.poll.return_value = None

    with patch.object(opencode_runtime, "_config_manager_snapshot", return_value={}):
        with patch.object(opencode_runtime.shutil, "which", side_effect=lambda name: f"/bin/{name}"):
            with patch.object(opencode_runtime.subprocess, "Popen", return_value=process) as popen:
                status = await opencode_runtime.ensure_opencode_server(
                    client,
                    base_url="http://127.0.0.1:4096",
                    timeout=1,
                )

    assert status.started is True
    assert status.package == "opencode-ai@latest"
    assert client.get.await_args_list[0].kwargs == {"timeout": 2.0}
    argv = popen.call_args.args[0]
    assert argv == [
        "/bin/npx",
        "-y",
        "opencode-ai@latest",
        "serve",
        "--hostname",
        "127.0.0.1",
        "--port",
        "4096",
    ]
    assert popen.call_args.kwargs["env"]["OPENCODE_SERVER_PASSWORD"] == "secret"


@pytest.mark.asyncio
async def test_disabled_auto_start_has_actionable_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RAE_OPENCODE_AUTO_START", "0")
    request = httpx.Request("GET", "http://127.0.0.1:4096/global/health")
    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("refused", request=request))

    with pytest.raises(opencode_runtime.OpenCodeSetupError, match="disabled"):
        await opencode_runtime.ensure_opencode_server(client, base_url="http://127.0.0.1:4096")


@pytest.mark.asyncio
async def test_refuses_to_auto_start_remote_host():
    request = httpx.Request("GET", "https://opencode.example.com/global/health")
    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("refused", request=request))

    with patch.object(opencode_runtime, "_config_manager_snapshot", return_value={}):
        with pytest.raises(opencode_runtime.OpenCodeSetupError, match="non-loopback"):
            await opencode_runtime.ensure_opencode_server(client, base_url="http://opencode.example.com:4096")


@pytest.mark.asyncio
async def test_start_timeout_stops_managed_child():
    request = httpx.Request("GET", "http://127.0.0.1:4096/global/health")
    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("refused", request=request))
    process = MagicMock()
    process.poll.return_value = None

    with patch.object(opencode_runtime, "_config_manager_snapshot", return_value={}):
        with patch.object(opencode_runtime.shutil, "which", side_effect=lambda name: f"/bin/{name}"):
            with patch.object(opencode_runtime.subprocess, "Popen", return_value=process):
                with patch.object(opencode_runtime.time, "monotonic", side_effect=[0.0, 2.0]):
                    with pytest.raises(opencode_runtime.OpenCodeSetupError, match="Timed out"):
                        await opencode_runtime.ensure_opencode_server(
                            client,
                            base_url="http://127.0.0.1:4096",
                            timeout=1,
                        )

    process.terminate.assert_called_once_with()


def test_runtime_settings_environment_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENCODE_BASE_URL", "http://localhost:7777/")
    monkeypatch.setenv("RAE_OPENCODE_PACKAGE", "opencode-ai@test")
    monkeypatch.setenv("RAE_OPENCODE_AUTO_START", "false")

    assert opencode_runtime.opencode_base_url() == "http://localhost:7777"
    assert opencode_runtime.opencode_npx_package() == "opencode-ai@test"
    assert opencode_runtime.opencode_auto_start() is False


def test_stop_managed_server_terminates_child():
    process = MagicMock()
    process.poll.return_value = None
    opencode_runtime._PROCESS = process
    opencode_runtime._PROCESS_URL = "http://127.0.0.1:4096"

    opencode_runtime.stop_managed_opencode_server()

    process.terminate.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=3)
    assert opencode_runtime._PROCESS is None
