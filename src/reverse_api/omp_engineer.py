"""Oh My Pi CLI integration for API reverse engineering."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .base_engineer import BaseEngineer
from .runtime_commands import resolve_windows_command


def _extract_omp_json_text(stdout: bytes) -> str:
    """Return only the final assistant text from OMP's JSON event stream."""
    final_text = ""
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "message_end":
            continue
        message = event.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        content = message.get("content")
        final_text = (
            "\n".join(
                block["text"]
                for block in content
                if isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            ).strip()
            if isinstance(content, list)
            else ""
        )
    return final_text


class OMPEngineer(BaseEngineer):
    """Run code generation through the user's configured Oh My Pi CLI."""

    def __init__(self, *args: Any, omp_model: str | None = None, **kwargs: Any) -> None:
        kwargs.setdefault("sdk", "omp")
        super().__init__(*args, **kwargs)
        self.har_path = Path(self.har_path).resolve()
        self.scripts_dir = self.scripts_dir.resolve()
        if self.existing_client_path is not None:
            self.existing_client_path = self.existing_client_path.resolve()
        self.omp_model = omp_model.strip() if isinstance(omp_model, str) else ""

    async def _run_omp(
        self,
        system_prompt: str,
        user_message: str,
        mcp_servers: dict[str, Any] | None = None,
    ) -> bool:
        executable = shutil.which("omp")
        if executable is None:
            self.ui.error("Oh My Pi CLI not found in PATH. Install OMP and configure its provider credentials first.")
            return False

        temp_workspace = tempfile.TemporaryDirectory(prefix="rae-omp-") if mcp_servers else None
        workspace = temp_workspace.name if temp_workspace else str(self.scripts_dir.parent.parent)
        process = None
        try:
            if mcp_servers:
                mcp_config = Path(workspace) / ".omp" / "mcp.json"
                mcp_config.parent.mkdir(parents=True)
                mcp_config.write_text(json.dumps({"mcpServers": mcp_servers}), encoding="utf-8")
            args = [
                executable,
                "--print",
                "--no-session",
                "--mode",
                "json",
                "--cwd",
                workspace,
            ]
            if mcp_servers:
                args.extend(["--add-dir", str(self.scripts_dir.parent.parent)])
            args.extend(["--system-prompt", system_prompt])
            if self.omp_model:
                args.extend(["--model", self.omp_model])
            args.append(user_message)
            args = resolve_windows_command(args)

            process = await asyncio.create_subprocess_exec(
                *args,
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=600)
        except asyncio.CancelledError:
            if process is not None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
            raise
        except TimeoutError:
            if process is not None:
                process.kill()
                await process.wait()
            self.ui.error("OMP session timed out after 10 minutes")
            self.message_store.save_error("OMP session timed out")
            return False
        except (OSError, ValueError) as exc:
            error_message = str(exc)
            self.ui.error(f"Could not start OMP: {error_message}")
            self.message_store.save_error(error_message)
            return False
        finally:
            if temp_workspace:
                temp_workspace.cleanup()

        output = _extract_omp_json_text(stdout)
        if output:
            self.ui.thinking(output)
            self.message_store.save_thinking(output)
        if process.returncode:
            error = stderr.decode("utf-8", errors="replace").strip() or f"OMP exited with status {process.returncode}"
            self.ui.error(error)
            self.message_store.save_error(error)
            return False
        return True

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        self.ui.header(self.run_id, self.prompt, self.omp_model or "OMP configured model", self.sdk, mode="engineer")
        self.ui.start_analysis()
        system_prompt, user_message = self._build_prompts()
        self.message_store.save_prompt(user_message)
        if not await self._run_omp(system_prompt, user_message):
            return None

        script_file = self.scripts_dir / self._get_client_filename()
        if not script_file.is_file():
            error_message = f"OMP exited successfully but generated client file was not found: {script_file}"
            self.ui.error(error_message)
            self.message_store.save_error(error_message)
            return None

        script_path = str(script_file)
        result = {"script_path": script_path, "usage": self.usage_metadata}
        self.ui.success(script_path, str(self.local_scripts_dir / self._get_client_filename()) if self.local_scripts_dir else None)
        self.message_store.save_result(result)
        return result
