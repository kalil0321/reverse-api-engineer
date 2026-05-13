"""Cursor Agent SDK (TypeScript) via a Node subprocess bridge."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .base_engineer import BaseEngineer

_BRIDGE_DIR = Path(__file__).resolve().parent / "cursor_bridge"
_BRIDGE_SCRIPT = _BRIDGE_DIR / "run.mjs"
_SDK_MARKER = _BRIDGE_DIR / "node_modules" / "@cursor" / "sdk"


def _ensure_cursor_bridge_deps() -> str | None:
    """Install npm dependencies for the bridge if missing. Returns error message or None."""
    if not _BRIDGE_SCRIPT.is_file():
        return "cursor bridge script missing (package incomplete)"
    if _SDK_MARKER.is_dir():
        return None
    npm = shutil.which("npm")
    if not npm:
        return "npm not found in PATH (required to install @cursor/sdk for sdk=cursor)"
    try:
        subprocess.run(
            [npm, "install", "--no-fund", "--no-audit"],
            cwd=str(_BRIDGE_DIR),
            check=True,
            timeout=600,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or e.stdout or "")[-2000:]
        return f"npm install in cursor_bridge failed: {tail or e}"
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"npm install in cursor_bridge failed: {e}"
    if not _SDK_MARKER.is_dir():
        return "@cursor/sdk did not install under cursor_bridge/node_modules"
    return None


class CursorEngineer(BaseEngineer):
    """Reverse engineering using Cursor's TypeScript agent SDK (Node subprocess)."""

    def __init__(
        self,
        run_id: str,
        har_path: Any,
        prompt: str,
        model: str | None = None,
        cursor_model: str | None = None,
        **kwargs: Any,
    ):
        cm = cursor_model or model or "composer-2"
        super().__init__(run_id=run_id, har_path=har_path, prompt=prompt, model=cm, **kwargs)
        self.cursor_model = cm

    def _workspace_cwd(self) -> str:
        return str(self.scripts_dir.parent.parent)

    def _merge_usage_from_bridge(self, usage: dict[str, Any] | None) -> None:
        if not usage:
            return
        for key in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
            if key in usage and isinstance(usage[key], (int, float)):
                self.usage_metadata[key] = self.usage_metadata.get(key, 0) + int(usage[key])

    async def _dispatch_stream_event(self, event: dict[str, Any]) -> None:
        et = event.get("type")
        if et == "thinking" and event.get("text"):
            t = str(event["text"])
            self.ui.thinking(t)
            self.message_store.save_thinking(t)
        elif et == "assistant" and event.get("text"):
            t = str(event["text"])
            self.ui.thinking(t)
            self.message_store.save_thinking(t)
        elif et == "tool_call":
            name = str(event.get("name") or "tool")
            status = event.get("status")
            if status == "running":
                args = event.get("args") if isinstance(event.get("args"), dict) else {}
                self.ui.tool_start(name, args)
                self.message_store.save_tool_start(name, args)
            else:
                is_err = status == "error"
                res = event.get("result")
                out = str(res) if res is not None else None
                self.ui.tool_result(name, is_err, out)
                self.message_store.save_tool_result(name, is_err, out)

    async def _one_turn(
        self,
        prompt: str,
        *,
        mcp_servers: dict[str, Any] | None,
        resume_agent_id: str | None,
    ) -> dict[str, Any]:
        api_key = os.environ.get("CURSOR_API_KEY", "")
        req: dict[str, Any] = {
            "cwd": self._workspace_cwd(),
            "modelId": self.cursor_model,
            "prompt": prompt,
        }
        if api_key:
            req["apiKey"] = api_key
        if mcp_servers:
            req["mcpServers"] = mcp_servers
        if resume_agent_id:
            req["resumeAgentId"] = resume_agent_id

        pre = _ensure_cursor_bridge_deps()
        if pre:
            return {"error": pre}

        node_exe = shutil.which("node")
        if not node_exe:
            return {"error": "node not found in PATH"}

        proc = await asyncio.create_subprocess_exec(
            node_exe,
            str(_BRIDGE_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(_BRIDGE_DIR),
            env=os.environ.copy(),
        )

        if proc.stdin:
            proc.stdin.write(json.dumps(req).encode("utf-8"))
            await proc.stdin.drain()
            proc.stdin.close()

        assistant_chunks: list[str] = []
        assert proc.stdout is not None
        while True:
            line_b = await proc.stdout.readline()
            if not line_b:
                break
            line = line_b.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = obj.get("type")
            if t == "stream" and isinstance(obj.get("event"), dict):
                ev = obj["event"]
                await self._dispatch_stream_event(ev)
                if ev.get("type") == "assistant" and ev.get("text"):
                    assistant_chunks.append(str(ev["text"]))
            elif t == "agent":
                pass
            elif t == "done":
                run_result = obj.get("runResult") or {}
                if run_result.get("status") == "error":
                    await proc.wait()
                    return {"error": str(run_result.get("result") or "run error")}
                self._merge_usage_from_bridge(obj.get("usage"))
                rr = run_result.get("result")
                if isinstance(rr, str) and rr.strip() and not assistant_chunks:
                    self.ui.thinking(rr)
                    self.message_store.save_thinking(rr)
                code = await proc.wait()
                stderr_b = await proc.stderr.read() if proc.stderr else b""
                if code != 0:
                    err_t = stderr_b.decode("utf-8", errors="replace").strip()
                    return {"error": err_t or f"cursor bridge exited {code}"}
                return {"ok": True, "agentId": obj.get("agentId")}
            elif t == "error":
                msg = str(obj.get("message") or "bridge error")
                if proc.stderr:
                    extra = (await proc.stderr.read()).decode("utf-8", errors="replace").strip()
                    if extra:
                        msg = f"{msg}\n{extra}"
                await proc.wait()
                return {"error": msg}

        stderr_b = await proc.stderr.read() if proc.stderr else b""
        code = await proc.wait()
        err_t = stderr_b.decode("utf-8", errors="replace").strip()
        return {"error": err_t or f"empty bridge output (exit {code})"}

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        self.ui.header(self.run_id, self.prompt, self.cursor_model, self.sdk, mode="engineer")
        self.ui.start_analysis()

        dep_err = _ensure_cursor_bridge_deps()
        if dep_err:
            self.ui.error(dep_err)
            self.message_store.save_error(dep_err)
            self.ui.console.print("\n[dim]Set CURSOR_API_KEY and ensure Node.js 18+ and npm are installed.[/dim]")
            return None

        if not os.environ.get("CURSOR_API_KEY"):
            msg = "CURSOR_API_KEY is not set"
            self.ui.error(msg)
            self.message_store.save_error(msg)
            self.ui.console.print("\n[dim]Create an API key at https://cursor.com/dashboard/integrations[/dim]")
            return None

        system_prompt, user_message = self._build_prompts()
        self.message_store.save_prompt(user_message)
        combined = f"{system_prompt}\n\n{user_message}"

        agent_id: str | None = None
        last_result: dict[str, Any] | None = None
        turn_prompt: str = combined

        try:
            while True:
                res = await self._one_turn(
                    turn_prompt,
                    mcp_servers=None,
                    resume_agent_id=agent_id,
                )
                if res.get("error"):
                    self.ui.error(str(res["error"]))
                    self.message_store.save_error(str(res["error"]))
                    return None

                aid = res.get("agentId")
                if isinstance(aid, str) and aid:
                    agent_id = aid

                script_path = str(self.scripts_dir / self._get_client_filename())
                local_path = str(self.local_scripts_dir / self._get_client_filename()) if self.local_scripts_dir else None
                self.ui.success(script_path, local_path)

                self.usage_metadata.setdefault("estimated_cost_usd", 0.0)
                self.ui.console.print("  [dim]Usage (Cursor SDK): see dashboard — token counts are best-effort[/dim]")
                it = self.usage_metadata.get("input_tokens", 0)
                ot = self.usage_metadata.get("output_tokens", 0)
                if it or ot:
                    self.ui.console.print(f"  [dim]  input: {it:,} / output: {ot:,} tokens (approx.)[/dim]")

                last_result = {
                    "script_path": script_path,
                    "usage": self.usage_metadata,
                }
                self.message_store.save_result(last_result)

                if not self.interactive:
                    return last_result

                follow = await self._prompt_follow_up()
                if not follow:
                    return last_result
                turn_prompt = follow
                self.message_store.save_prompt(turn_prompt)
        except KeyboardInterrupt:
            self.ui.console.print("\n  [dim]run aborted[/dim]")
            return last_result


class CursorAutoEngineer(CursorEngineer):
    """Agent + capture using Cursor SDK with MCP browser servers."""

    def __init__(
        self,
        run_id: str,
        prompt: str,
        output_dir: str | None = None,
        agent_provider: str = "auto",
        **kwargs: Any,
    ):
        headless = kwargs.pop("headless", False)
        from .utils import get_har_dir

        har_dir = get_har_dir(run_id, output_dir)
        har_path = har_dir / "recording.har"

        super().__init__(
            run_id=run_id,
            har_path=har_path,
            prompt=prompt,
            output_dir=output_dir,
            **kwargs,
        )
        self.mcp_run_id = run_id
        self.agent_provider = agent_provider
        self.headless = headless

    def _cursor_mcp_servers(self) -> dict[str, Any]:
        if self.agent_provider == "chrome-mcp":
            args = ["-y", "chrome-devtools-mcp@latest", "--no-usage-statistics"]
            if self.headless:
                args.append("--headless")
            else:
                args.append("--autoConnect")
            return {
                "chrome-devtools": {
                    "type": "stdio",
                    "command": "npx",
                    "args": args,
                },
            }
        playwright_args = [
            "-y",
            "rae-playwright-mcp@latest",
            "run-mcp-server",
            "--run-id",
            self.mcp_run_id,
        ]
        if self.headless:
            playwright_args.append("--headless")
        return {
            "playwright": {
                "type": "stdio",
                "command": "npx",
                "args": playwright_args,
            },
        }

    async def analyze_and_generate(self) -> dict[str, Any] | None:
        from .auto_engineer import ClaudeAutoEngineer

        self.ui.header(self.run_id, self.prompt, self.cursor_model, self.sdk, mode="agent")
        self.ui.start_analysis()

        dep_err = _ensure_cursor_bridge_deps()
        if dep_err:
            self.ui.error(dep_err)
            self.message_store.save_error(dep_err)
            return None

        if not os.environ.get("CURSOR_API_KEY"):
            msg = "CURSOR_API_KEY is not set"
            self.ui.error(msg)
            self.message_store.save_error(msg)
            self.ui.console.print("\n[dim]Create an API key at https://cursor.com/dashboard/integrations[/dim]")
            return None

        system_prompt, user_message = ClaudeAutoEngineer._build_auto_prompts(self)
        self.message_store.save_prompt(user_message)
        combined = f"{system_prompt}\n\n{user_message}"

        mcp = self._cursor_mcp_servers()
        agent_id: str | None = None
        last_result: dict[str, Any] | None = None
        turn_prompt: str = combined

        try:
            while True:
                res = await self._one_turn(
                    turn_prompt,
                    mcp_servers=mcp,
                    resume_agent_id=agent_id,
                )
                if res.get("error"):
                    self.ui.error(str(res["error"]))
                    self.message_store.save_error(str(res["error"]))
                    return None

                aid = res.get("agentId")
                if isinstance(aid, str) and aid:
                    agent_id = aid

                script_path = str(self.scripts_dir / self._get_client_filename())
                local_path = str(self.local_scripts_dir / self._get_client_filename()) if self.local_scripts_dir else None
                self.ui.success(script_path, local_path)
                self.usage_metadata.setdefault("estimated_cost_usd", 0.0)

                last_result = {"script_path": script_path, "usage": self.usage_metadata}
                self.message_store.save_result(last_result)

                if not self.interactive:
                    return last_result

                fu = await self._prompt_follow_up()
                if not fu:
                    return last_result
                turn_prompt = fu
                self.message_store.save_prompt(turn_prompt)
        except KeyboardInterrupt:
            self.ui.console.print("\n  [dim]run aborted[/dim]")
            return last_result
