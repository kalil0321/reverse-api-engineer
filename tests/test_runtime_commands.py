"""Keep Windows batch syntax out of user-supplied client arguments."""

import json
import shutil
import subprocess
import sys
from unittest.mock import patch

import pytest

from reverse_api.runtime_commands import decode_process_output, resolve_windows_command


def test_utf8_output_preferred_over_legacy_locale(monkeypatch):
    monkeypatch.setattr("locale.getencoding", lambda: "gbk")
    assert decode_process_output("中文 — 🐍\r\n".encode()) == "中文 — 🐍\n"


def test_native_output_falls_back_to_legacy_locale(monkeypatch):
    monkeypatch.setattr("locale.getencoding", lambda: "cp1252")
    assert decode_process_output("café\r\n".encode("cp1252")) == "café\n"


@pytest.mark.parametrize("argument", ["a&b", "a|b", "%PATH%", "!PATH!", "(a)", "a^b", 'a"b', "a\nb", "a>b", "a<b"])
def test_batch_fallback_refuses_metacharacters(argument):
    with patch.object(sys, "platform", "win32"), patch("shutil.which", return_value=None):
        with pytest.raises(ValueError, match="Cannot safely"):
            resolve_windows_command(["tool.cmd", argument])


def test_native_npx_receives_arguments_verbatim(tmp_path, monkeypatch):
    root = tmp_path / "Node & Tools"
    entrypoint = root / "node_modules/npm/bin/npx-cli.js"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.touch()
    node = str(root / "node.exe")
    monkeypatch.setattr(shutil, "which", lambda command: node if command == "node" else None)
    args = ["https://example.com/?a=1&b=2|three", "%PATH%", '!literal!', 'quoted"text']
    with patch.object(sys, "platform", "win32"):
        result = resolve_windows_command([str(root / "npx.cmd"), *args])
    assert result == [node, str(entrypoint), *args]


def test_batch_fallback_keeps_spaces_and_rejects_unsafe_launcher_path():
    with patch.object(sys, "platform", "win32"), patch("shutil.which", return_value=None):
        assert resolve_windows_command(["Maven Tools/mvn.cmd", "plain path/pom.xml"]) == ["Maven Tools/mvn.cmd", "plain path/pom.xml"]
        with pytest.raises(ValueError, match="Cannot safely"):
            resolve_windows_command(["Tools&More/mvn.cmd", "compile"])


@pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows process argument parsing")
def test_native_node_preserves_shell_characters(tmp_path):
    node = shutil.which("node")
    assert node, "Node.js must be available on Windows CI"
    entrypoint = tmp_path / "node_modules/npm/bin/npx-cli.js"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text("console.log(JSON.stringify(process.argv.slice(2)))", encoding="utf-8")
    launcher = tmp_path / "npx.cmd"
    # If the batch path runs, the test must fail rather than executing user input.
    launcher.write_text("@exit /b 99\n", encoding="ascii")
    arguments = ["https://example.com/?a=1&b=2|three", "%PATH%", "!literal!", 'quoted"text', "中文", "a path with spaces"]
    argv = resolve_windows_command([str(launcher), *arguments])
    result = subprocess.run(argv, capture_output=True, encoding="utf-8", check=True)
    assert json.loads(result.stdout) == arguments


@pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows npm argument forwarding")
def test_real_npx_preserves_client_arguments(tmp_path):
    npx = shutil.which("npx")
    assert npx, "npx must be available on Windows CI"
    script = tmp_path / "echo-args.js"
    script.write_text("#!/usr/bin/env node\nconsole.log(JSON.stringify(process.argv.slice(2)))", encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "rae-argument-fixture", "version": "1.0.0",
        "bin": {"rae-echo": "echo-args.js"},
    }), encoding="utf-8")
    arguments = ["https://example.com/?a=1&b=2|three", "%PATH%", "!literal!", 'quoted"text', "中文"]
    # A local dependency-free fixture avoids relying on cached registry metadata.
    argv = resolve_windows_command([npx, "--offline", "--yes", "--package", str(tmp_path), "rae-echo", *arguments])
    assert argv[0].lower().endswith("node.exe"), "must bypass the batch shim"
    result = subprocess.run(argv, capture_output=True, encoding="utf-8", check=True, timeout=30)
    assert json.loads(result.stdout) == arguments
