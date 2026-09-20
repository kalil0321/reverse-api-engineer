"""The locked dependency stack must start without legacy HTTP clients."""

import subprocess
import sys
import textwrap

import pytest


@pytest.mark.parametrize(
    ("option", "expected"),
    [("--version", "reverse-api-engineer, version"), ("--help", "Commands:")],
)
def test_cli_starts_without_legacy_http_clients(tmp_path, option, expected):
    # A fresh interpreter prevents earlier test imports from hiding the failure.
    # Block legacy clients even if another development tool installed them.
    script = textwrap.dedent(
        """
        import importlib
        import importlib.abc
        import sys
        from pathlib import Path
        from unittest.mock import patch

        class BlockLegacyHttpClients(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split('.')[0] in {'httpx', 'httpx_sse', 'httpcore'}:
                    raise ModuleNotFoundError(
                        f'Legacy HTTP client is unavailable: {fullname}',
                        name=fullname,
                    )

        sys.meta_path.insert(0, BlockLegacyHttpClients())

        with patch('reverse_api.utils.get_app_dir', return_value=Path(sys.argv[1])):
            for module in (
                'reverse_api.auto_engineer',
                'reverse_api.ollama_runtime',
                'reverse_api.opencode_engineer',
                'reverse_api.opencode_runtime',
            ):
                importlib.import_module(module)

            from reverse_api.cli import main

            main([sys.argv[2]], prog_name='reverse-api-engineer')
        """
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(tmp_path), option],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert expected in result.stdout
