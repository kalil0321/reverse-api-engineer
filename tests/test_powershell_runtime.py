"""Exercise the generated-module runner using a real PowerShell process."""

import json
import os
import shutil
import subprocess

import pytest

from reverse_api.utils import build_script_commands


@pytest.fixture
def module_path(tmp_path):
    directory = tmp_path / "client space é $literal"
    directory.mkdir()
    module = directory / "api_client.psm1"
    module.write_text(
        "function Get-Result { [CmdletBinding()] param(); "
        "[PSCustomObject]@{ value = 'café'; count = 2 } }; "
        "Export-ModuleMember -Function Get-Result\n",
        encoding="utf-8",
    )
    (directory / "Example.ps1").write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "Import-Module (Join-Path $PSScriptRoot 'api_client.psm1') -Force -ErrorAction Stop\n"
        "Get-Result | ConvertTo-Json -Depth 20\n",
        encoding="utf-8",
    )
    return module


@pytest.fixture
def pwsh():
    executable = shutil.which("pwsh")
    if executable is None:
        if os.environ.get("RAE_REQUIRE_PWSH") == "1":
            pytest.fail("PowerShell 7+ is required for this test job")
        pytest.skip("PowerShell 7+ is not installed")
    return executable


def test_powershell_runs_from_other_directory(module_path, tmp_path, pwsh):
    commands, _ = build_script_commands(module_path)
    commands[0][0] = pwsh
    result = subprocess.run(commands[0], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"value": "café", "count": 2}


def test_powershell_failure_is_nonzero(module_path, pwsh):
    module_path.write_text(
        "function Get-Result { [CmdletBinding()] param(); "
        "try { throw 'request failed' } catch { throw } }; "
        "Export-ModuleMember -Function Get-Result\n",
        encoding="utf-8",
    )
    commands, _ = build_script_commands(module_path)
    commands[0][0] = pwsh
    result = subprocess.run(commands[0], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode != 0
    assert "request failed" in result.stderr


def test_powershell_rejects_silently_ignored_arguments(module_path):
    with pytest.raises(ValueError, match="script arguments are not supported"):
        build_script_commands(module_path, ("-Value", "requested"))


def test_powershell_rejects_unrelated_module(module_path):
    other = module_path.with_name("other.psm1")
    other.write_text("throw 'wrong module'", encoding="utf-8")
    with pytest.raises(ValueError, match="only supports api_client.psm1"):
        build_script_commands(other)


def test_powershell_reports_missing_example(module_path):
    module_path.with_name("Example.ps1").unlink()
    with pytest.raises(ValueError, match="companion Example.ps1 is missing"):
        build_script_commands(module_path)
