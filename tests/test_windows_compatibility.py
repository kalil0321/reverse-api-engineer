"""Locale regressions runnable on every OS, including Windows CI."""

import builtins
import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from reverse_api.config import ConfigManager
from reverse_api.messages import MessageStore
from reverse_api.opencode_engineer import OpenCodeEngineer
from reverse_api.prompts import load
from reverse_api.session import SessionManager
from reverse_api.utils import OUTPUT_LANGUAGE_EXTENSIONS, extract_domain_from_har

UNICODE_TEXT = "guidelines — 中文 café 🐍"


@pytest.fixture(params=["gbk", "cp1252"])
def legacy_locale(request, monkeypatch):
    """Model Python's legacy text-file defaults without requiring that OS locale."""

    def wrap(real_open):
        def legacy_open(file, mode="r", buffering=-1, encoding=None, *args, **kwargs):
            if "b" not in mode and encoding in (None, "locale"):
                encoding = request.param
            return real_open(file, mode, buffering, encoding, *args, **kwargs)

        return legacy_open

    monkeypatch.setattr(builtins, "open", wrap(builtins.open))
    monkeypatch.setattr(io, "open", wrap(io.open))


@pytest.mark.parametrize("language", OUTPUT_LANGUAGE_EXTENSIONS)
def test_manual_prompts_under_legacy_locale(tmp_path, legacy_locale, language):
    engineer = OpenCodeEngineer(
        run_id="locale-test",
        har_path=tmp_path / "recording.har",
        prompt=UNICODE_TEXT,
        output_dir=str(tmp_path),
        output_language=language,
        interactive=False,
        verbose=False,
    )
    system, user = engineer._build_prompts()
    assert UNICODE_TEXT in user
    assert "{include:" not in system
    assert engineer._get_language_name() in system


def test_nested_prompt_includes_under_legacy_locale(tmp_path, legacy_locale, monkeypatch):
    import reverse_api.prompts as prompts

    monkeypatch.setattr(prompts, "_PROMPTS_DIR", tmp_path)
    monkeypatch.setattr(prompts, "_PARTIALS_DIR", tmp_path)
    (tmp_path / "main.md").write_text("{include:first} {value}", encoding="utf-8")
    (tmp_path / "first.md").write_text("{include:second}", encoding="utf-8")
    (tmp_path / "second.md").write_text(UNICODE_TEXT, encoding="utf-8")
    assert load("main", value="done") == f"{UNICODE_TEXT} done"


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig"])
def test_unicode_persistence_under_legacy_locale(tmp_path, legacy_locale, encoding):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"agent_browser_notes": UNICODE_TEXT}, ensure_ascii=False), encoding=encoding)
    config = ConfigManager(config_path)
    assert config.get("agent_browser_notes") == UNICODE_TEXT
    config.save()
    assert ConfigManager(config_path).get("agent_browser_notes") == UNICODE_TEXT

    history_path = tmp_path / "history.json"
    history_path.write_text(json.dumps([{"run_id": "test", "prompt": UNICODE_TEXT}], ensure_ascii=False), encoding=encoding)
    session = SessionManager(history_path)
    assert session.get_run("test")["prompt"] == UNICODE_TEXT
    session.save()
    assert SessionManager(history_path).get_run("test")["prompt"] == UNICODE_TEXT

    store = MessageStore("test", str(tmp_path))
    store.messages_path.write_text(json.dumps({"type": "prompt", "content": UNICODE_TEXT}, ensure_ascii=False) + "\n", encoding="utf-8")
    store.save_thinking(UNICODE_TEXT)
    assert [m["content"] for m in store.load()] == [UNICODE_TEXT, UNICODE_TEXT]


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig"])
def test_har_unicode_and_windows_bom(tmp_path, legacy_locale, encoding):
    har = tmp_path / "recording.har"
    har.write_text(
        json.dumps(
            {"log": {"entries": [{"request": {"url": "https://example.com/中文"}, "response": {"content": {"text": UNICODE_TEXT}}}]}},
            ensure_ascii=False,
        ),
        encoding=encoding,
    )
    assert extract_domain_from_har(har) == "example.com"


def test_invalid_utf8_config_and_history_recover(tmp_path):
    path = tmp_path / "broken.json"
    path.write_bytes(b"\xff")
    assert ConfigManager(path).get("sdk") == "claude"
    assert SessionManager(path).history == []


def test_corrupt_message_record_preserves_surrounding_history(tmp_path):
    store = MessageStore("mixed-history", str(tmp_path))
    first = json.dumps({"type": "prompt", "content": "中文"}, ensure_ascii=False).encode()
    last = json.dumps({"type": "thinking", "content": "🐍"}, ensure_ascii=False).encode()
    store.messages_path.write_bytes(first + b'\n{"content":"caf\xe9"}\ninvalid json\n' + last + b"\n")
    assert [message["content"] for message in store.load()] == ["中文", "🐍"]


@pytest.mark.parametrize(
    ("platform", "env", "relative"),
    [
        ("win32", "LOCALAPPDATA", "Google/Chrome/User Data"),
        ("linux", "XDG_CONFIG_HOME", "google-chrome"),
        ("linux", "CHROME_CONFIG_HOME", "google-chrome"),
        ("darwin", None, "Library/Application Support/Google/Chrome"),
    ],
)
def test_chrome_profile_discovery(tmp_path, monkeypatch, platform, env, relative):
    pytest.importorskip("playwright")
    from reverse_api import browser

    for key in ("LOCALAPPDATA", "XDG_CONFIG_HOME", "CHROME_CONFIG_HOME"):
        monkeypatch.delenv(key, raising=False)
    root = tmp_path / "User Name 中文"
    profile = root / relative
    profile.mkdir(parents=True)
    if env:
        monkeypatch.setenv(env, str(root))
    with patch.object(Path, "home", return_value=root), patch.object(browser.sys, "platform", platform):
        assert browser.get_chrome_profile_dir() == profile
        profile.rmdir()
        assert browser.get_chrome_profile_dir() is None


def test_node_diagnostic_probe_decodes_utf8_under_gbk(monkeypatch):
    from reverse_api.agent_browser import _probe_help_argv

    monkeypatch.setattr(subprocess, "_text_encoding", lambda: "gbk")
    error = _probe_help_argv([sys.executable, "-c", "import sys; sys.stderr.buffer.write('中文 — 🐍'.encode('utf-8')); sys.exit(1)"])
    assert "中文 — 🐍" in error


@pytest.mark.parametrize("language", ["python", "javascript"])
def test_run_json_real_unicode_output(tmp_path, monkeypatch, language):
    """Exercise actual child pipes under a legacy locale, including a spaced path."""
    import venv

    from click.testing import CliRunner

    from reverse_api import cli

    output_dir = tmp_path / "User Name 中文"
    scripts = output_dir / "scripts" / "unicode-run"
    scripts.mkdir(parents=True)
    if language == "python":
        script = scripts / "api_client.py"
        script.write_text("import sys\nprint('中文 — café 🐍')\nprint('erreur — 中文', file=sys.stderr)\n", encoding="utf-8")
        venv.EnvBuilder(with_pip=False).create(output_dir / ".venv")
    else:
        script = scripts / "api_client.js"
        script.write_text("console.log('中文 — café 🐍'); console.error('erreur — 中文');", encoding="utf-8")
    config = ConfigManager(tmp_path / "config.json")
    config.set("output_dir", str(output_dir))
    session = SessionManager(tmp_path / "history.json")
    session.add_run("unicode-run", "unicode output", paths={"script_path": str(script)})
    monkeypatch.setattr(cli, "config_manager", config)
    monkeypatch.setattr(cli, "session_manager", session)
    monkeypatch.setattr(subprocess, "_text_encoding", lambda: "gbk")
    # Configuring the parent decoder alone would still leave the child using GBK.
    monkeypatch.setenv("PYTHONIOENCODING", "gbk")

    result = CliRunner().invoke(cli.main, ["run", "unicode-run", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["stdout"] == "中文 — café 🐍\n"
    assert payload["stderr"] == "erreur — 中文\n"


def test_interactive_dependency_retry_preserves_unicode(tmp_path, monkeypatch):
    import venv

    from click.testing import CliRunner

    from reverse_api import cli

    scripts = tmp_path / "scripts" / "retry-run"
    scripts.mkdir(parents=True)
    script = scripts / "api_client.py"
    script.write_text("import rae_locale_dep\nprint('中文 — 🐍')\n", encoding="utf-8")
    venv.EnvBuilder(with_pip=False).create(tmp_path / ".venv")
    config = ConfigManager(tmp_path / "config.json")
    config.set("output_dir", str(tmp_path))
    session = SessionManager(tmp_path / "history.json")
    session.add_run("retry-run", "retry output", paths={"script_path": str(script)})
    monkeypatch.setattr(cli, "config_manager", config)
    monkeypatch.setattr(cli, "session_manager", session)
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252")
    real_run = subprocess.run
    executions = []

    def run_with_local_install(cmd, **kwargs):
        if "install" in cmd:
            assert cmd[-1] == "rae_locale_dep"
            (scripts / "rae_locale_dep.py").write_text("", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0)
        completed = real_run(cmd, stdout=subprocess.PIPE, **kwargs)
        executions.append(completed)
        return completed

    monkeypatch.setattr(subprocess, "run", run_with_local_install)
    result = CliRunner().invoke(cli.main, ["run", "retry-run", "--auto-install"])
    assert result.exit_code == 0, result.output
    assert [execution.returncode for execution in executions] == [1, 0]
    assert executions[-1].stdout.decode("utf-8").strip() == "中文 — 🐍"


def test_windows_probe_resolves_cmd_launcher(monkeypatch):
    from reverse_api import agent_browser

    launcher = r"C:\Program Files\nodejs\npx.cmd"
    monkeypatch.setattr(agent_browser.shutil, "which", lambda _: launcher)
    with patch.object(sys, "platform", "win32"), patch.object(subprocess, "run") as run:
        run.return_value.returncode = 0
        assert agent_browser._probe_help_argv(["npx", "-y", "agent-browser@0"]) is None
    assert run.call_args.args[0] == [launcher, "-y", "agent-browser@0", "--help"]
    assert not run.call_args.kwargs.get("shell", False)


@pytest.mark.parametrize("machine", [False, True])
def test_windows_script_run_resolves_cmd_launcher(tmp_path, monkeypatch, machine):
    from reverse_api import cli

    launcher = r"C:\Program Files\nodejs\npx.cmd"
    script = tmp_path / "api_client.ts"
    script.touch()
    monkeypatch.setattr("shutil.which", lambda _: launcher)
    monkeypatch.setattr(cli, "resolve_run", lambda *args, **kwargs: {"run_id": "test"})
    monkeypatch.setattr(cli, "discover_scripts", lambda *args, **kwargs: [script])
    with patch.object(sys, "platform", "win32"), patch.object(subprocess, "run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, stdout="ok", stderr="")
        if machine:
            payload = cli._run_script_machine_payload(
                identifier="test",
                script_args=(),
                file_name=None,
                list_scripts=False,
                auto_install=False,
                emit_event=lambda *args, **kwargs: None,
            )
            assert payload["status"] == "ok"
        else:
            with pytest.raises(SystemExit) as exit_info:
                cli._run_non_python_script(script, ())
            assert exit_info.value.code == 0
    assert run.call_args.args[0][0] == launcher
    assert not run.call_args.kwargs.get("shell", False)


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows CreateProcess and PATHEXT")
def test_native_windows_cmd_probe(tmp_path, monkeypatch):
    from reverse_api.agent_browser import _probe_help_argv

    launcher = tmp_path / "probe.cmd"
    launcher.write_bytes(b"@echo off\r\necho help\r\nexit /b 0\r\n")
    monkeypatch.setenv("PATH", str(tmp_path))
    assert _probe_help_argv(["probe"]) is None


@pytest.mark.parametrize("machine", [False, True])
def test_windows_batch_rejection_is_configuration_error(tmp_path, monkeypatch, machine):
    import click

    from reverse_api import cli

    script = tmp_path / "api_client.ts"
    script.touch()
    monkeypatch.setattr("shutil.which", lambda _: "custom.cmd")
    monkeypatch.setattr(cli, "resolve_run", lambda *args, **kwargs: {"run_id": "test"})
    monkeypatch.setattr(cli, "discover_scripts", lambda *args, **kwargs: [script])
    with patch.object(sys, "platform", "win32"), patch.object(subprocess, "run") as run:
        if machine:
            payload = cli._run_script_machine_payload(
                identifier="test", script_args=("a&b",), file_name=None,
                list_scripts=False, auto_install=False, emit_event=lambda *a, **kw: None,
            )
            assert payload["error_kind"] == "config_invalid"
            assert "Cannot safely" in payload["error"]
        else:
            with pytest.raises(click.ClickException, match="Cannot safely"):
                cli._run_non_python_script(script, ("a&b",))
        run.assert_not_called()


@pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows batch execution")
@pytest.mark.parametrize("machine", [False, True])
def test_windows_maven_uses_relative_pom_in_special_directory(tmp_path, monkeypatch, machine):
    from reverse_api import cli

    project = tmp_path / "dev (ops) %PATH% !name! & 中文"
    project.mkdir()
    script = project / "api_client.java"
    script.touch()
    (project / "pom.xml").write_text("<project/>", encoding="utf-8")
    launcher = tmp_path / "mvn.cmd"
    # A real batch process verifies argv and the working directory without a
    # Maven dependency download; this is a launcher contract, not a Java build.
    launcher.write_bytes(
        b'@echo off\r\nif not exist pom.xml exit /b 98\r\n'
        b'if not "%~3"=="pom.xml" exit /b 99\r\necho relative-pom-ok\r\nexit /b 0\r\n'
    )
    monkeypatch.setattr("shutil.which", lambda command: str(launcher) if command == "mvn" else None)
    monkeypatch.setattr(cli, "resolve_run", lambda *args, **kwargs: {"run_id": "test"})
    monkeypatch.setattr(cli, "discover_scripts", lambda *args, **kwargs: [script])
    if machine:
        payload = cli._run_script_machine_payload(
            identifier="test", script_args=(), file_name=None,
            list_scripts=False, auto_install=False, emit_event=lambda *a, **kw: None,
        )
        assert payload["status"] == "ok", payload
        assert payload["stdout"].strip() == "relative-pom-ok"
    else:
        with pytest.raises(SystemExit) as exit_info:
            cli._run_non_python_script(script, ())
        assert exit_info.value.code == 0
