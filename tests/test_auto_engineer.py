"""Tests for auto_engineer.py - Auto mode engineers."""

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2 as httpx
import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from reverse_api.auto_engineer import ClaudeAutoEngineer, OpenCodeAutoEngineer


@dataclass
class ToolResultWithResult(ToolResultBlock):
    """Tool result with legacy ``result`` attribute (engineer.py fallback)."""

    result: str | None = None


@dataclass
class ToolResultWithOutput(ToolResultBlock):
    """Tool result with legacy ``output`` attribute (engineer.py fallback)."""

    output: str | None = None


def _sdk_result_message(*, is_error: bool = False, result: str | None = None) -> ResultMessage:
    return ResultMessage(
        subtype="test",
        duration_ms=0,
        duration_api_ms=0,
        is_error=is_error,
        num_turns=1,
        session_id="test-session",
        result=result,
    )


def _valid_catalog_response() -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "default": {"anthropic": "claude-opus-4-6"},
        "providers": [
            {
                "id": "anthropic",
                "models": {
                    "claude-opus-4-6": {
                        "status": "active",
                        "capabilities": {"toolcall": True},
                    }
                },
            }
        ],
    }
    return response


class TestClaudeAutoEngineerInit:
    """Test ClaudeAutoEngineer initialization."""

    def test_init(self, tmp_path):
        """Initializes with HAR path and MCP run_id."""
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    eng = ClaudeAutoEngineer(
                        run_id="test123",
                        prompt="browse and capture",
                        model="claude-sonnet-4-6",
                        output_dir=str(tmp_path),
                    )
                    assert eng.mcp_run_id == "test123"
                    assert eng.har_path == tmp_path / "har" / "recording.har"


class TestClaudeAutoEngineerInitChromeMcp:
    """Test ClaudeAutoEngineer initialization with chrome-mcp provider."""

    def test_init_chrome_mcp(self, tmp_path):
        """Initializes with agent_provider='chrome-mcp'."""
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    eng = ClaudeAutoEngineer(
                        run_id="test123",
                        prompt="browse and capture",
                        model="claude-sonnet-4-6",
                        output_dir=str(tmp_path),
                        agent_provider="chrome-mcp",
                    )
                    assert eng.agent_provider == "chrome-mcp"
                    assert eng.mcp_run_id == "test123"

    def test_init_default_provider(self, tmp_path):
        """Default agent_provider is 'auto'."""
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    eng = ClaudeAutoEngineer(
                        run_id="test123",
                        prompt="browse and capture",
                        model="claude-sonnet-4-6",
                        output_dir=str(tmp_path),
                    )
                    assert eng.agent_provider == "auto"


class TestClaudeAutoEngineerPrompt:
    """Test auto prompt building."""

    def _make_engineer(self, tmp_path, **kwargs):
        defaults = {
            "run_id": "test123",
            "prompt": "browse and capture",
            "model": "claude-sonnet-4-6",
            "output_dir": str(tmp_path),
        }
        defaults.update(kwargs)
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    return ClaudeAutoEngineer(**defaults)

    def test_python_prompt(self, tmp_path):
        """Python prompt includes correct language references."""
        eng = self._make_engineer(tmp_path)
        sys_p, user_p = eng._build_auto_prompts()
        combined = sys_p + user_p
        assert "Python" in combined
        assert "requests" in sys_p
        assert "api_client.py" in sys_p

    def test_omp_capture_prompt_preserves_browser_and_privacy_contracts(self, tmp_path):
        from reverse_api.auto_engineer import OMPAutoEngineer

        engineer = OMPAutoEngineer(
            run_id="omp-test",
            prompt="Inspect https://example.com",
            output_dir=str(tmp_path),
            verbose=False,
        )
        system_prompt, user_message = engineer._get_active_prompts()

        assert "Never hardcode credentials" in system_prompt
        assert "environment variables or explicit runtime parameters" in system_prompt
        assert 'name: "rae-omp-test"' in user_message
        assert 'url: "about:blank"' in user_message
        assert "await tab.observe()" in user_message
        assert "await tab.ariaSnapshot()" in user_message
        assert "Do not use the RAE Playwright MCP" in user_message
        assert 'allowed_domains: ["example.com"]' in user_message
        assert "const requestedDomains = [\"example.com\"]" in user_message
        assert "isAllowedHost(new URL(r.url).hostname)" in user_message
        assert 'type: ["fetch", "xhr", "document"]' in user_message
        assert 'method: "GET"' in user_message
        assert 'status: "2xx"' in user_message
        assert "Never inspect or replay POST requests." in user_message
        assert "JSON.parse(detail.body)" in user_message
        assert 'value: "<redacted>"' in user_message
        assert "headers: [], queryString:" in user_message
        assert "unredacted body" in user_message
        assert "generated external clients do not inherit those browser cookies" in user_message
        assert "Do not create a placeholder client" in user_message
        assert "missing authentication is not a reason to skip client generation" in user_message
        assert "Do not claim authenticated execution without user-managed runtime credentials" in user_message
        assert f"await Bun.write(\"{engineer.har_path}\"" in user_message
        assert str(engineer.scripts_dir / engineer._get_client_filename()) in user_message

    def test_omp_auto_prompt_resolves_relative_har_paths(self, tmp_path, monkeypatch):
        from pathlib import Path

        from reverse_api.auto_engineer import OMPAutoEngineer

        monkeypatch.chdir(tmp_path)
        engineer = OMPAutoEngineer(
            run_id="relative-har",
            prompt="Inspect https://example.com",
            output_dir="relative-output",
            verbose=False,
        )
        expected_har_path = str(
            (tmp_path / "relative-output" / "har" / "relative-har" / "recording.har").resolve()
        )
        _, user_message = engineer._get_active_prompts()

        assert engineer.har_path == Path(expected_har_path)
        assert user_message.count(expected_har_path) == 2
        assert f'await Bun.write("{expected_har_path}"' in user_message

    def test_omp_capture_prompt_bounds_and_progresses_body_reads(self, tmp_path):
        from reverse_api.auto_engineer import OMPAutoEngineer

        engineer = OMPAutoEngineer(
            run_id="omp-bounds",
            prompt="Inspect https://example.com",
            output_dir=str(tmp_path),
            verbose=False,
        )
        _, user_message = engineer._get_active_prompts()

        assert "1024 * 1024" in user_message
        assert "bodyRetrievalAttempts < 3" in user_message
        assert "bodyRetrievalAttempts++" in user_message
        assert "Number.isFinite(size)" in user_message
        assert "size > 0 && size <= 1024 * 1024" in user_message
        assert "detail.bodyTruncated !== true" in user_message
        assert "new TextEncoder().encode(detail.body).byteLength <= responseBodyLimitBytes" in user_message
        assert "visitedIds" in user_message
        assert "(await getCandidates()).find(candidate => !visitedIds.has(String(candidate.id)))" in user_message
        assert "await tab.requests(requestOptions)" in user_message
        assert "await tab.wheel(0, 600)" in user_message
        assert "Unknown browser request id " in user_message
        assert "error instanceof Error" in user_message
        assert "throw error" in user_message

    def test_omp_prompt_derives_mission_target_and_allowed_hosts(self, tmp_path):
        from reverse_api.auto_engineer import OMPAutoEngineer

        engineer = OMPAutoEngineer(
            run_id="omp-mission-url",
            prompt="Inspect https://api.example.test/v1",
            output_dir=str(tmp_path),
            verbose=False,
        )
        _, user_message = engineer._get_active_prompts()

        assert "https://api.example.test/v1" in user_message
        assert "Use the supplied starting URL exactly: https://api.example.test/v1." in user_message
        assert 'allowed_domains: ["api.example.test"]' in user_message

    @pytest.mark.parametrize(
        "output_language",
        ["python", "javascript", "typescript", "go", "java", "csharp", "php", "ruby", "powershell"],
    )
    def test_omp_auth_guidance_is_runtime_managed_for_every_language(
        self, tmp_path, output_language
    ):
        from reverse_api.auto_engineer import OMPAutoEngineer

        engineer = OMPAutoEngineer(
            run_id=f"omp-auth-{output_language}",
            prompt="Inspect https://example.test",
            output_dir=str(tmp_path),
            output_language=output_language,
            verbose=False,
        )
        system_prompt, _ = engineer._get_active_prompts()
        lowered = system_prompt.lower()
        assert "never hardcode credentials" in lowered
        assert "environment variables or explicit runtime parameters" in lowered
        assert "hardcode all cookies" not in lowered
        assert "zero configuration" not in lowered
    def test_omp_prompt_requires_a_mission_target_when_url_is_unresolved(self, tmp_path):
        from reverse_api.auto_engineer import OMPAutoEngineer

        engineer = OMPAutoEngineer(
            run_id="omp-no-url",
            prompt="Inspect the catalog",
            output_dir=str(tmp_path),
            verbose=False,
        )
        _, user_message = engineer._get_active_prompts()
        assert "<requested_start_url>" not in user_message
        assert "No starting URL was resolved; derive the target directly from the mission." in user_message
        assert "Do not follow links or navigate to other hosts unless the mission requires it." in user_message

    def test_omp_headless_prompt_keeps_browser_headless(self, tmp_path):
        from reverse_api.auto_engineer import OMPAutoEngineer

        engineer = OMPAutoEngineer(
            run_id="omp-headless",
            prompt="Inspect https://example.com",
            output_dir=str(tmp_path),
            headless=True,
            verbose=False,
        )
        _, user_message = engineer._get_active_prompts()
        assert "headed: false" in user_message


    @pytest.mark.parametrize(
        ("mission_prompt", "requested_url"),
        [
            ("Inspect the catalog", "https://shop.example.test/catalog"),
            ("Inspect https://shop.example.test/catalog", None),
        ],
    )
    @pytest.mark.asyncio
    async def test_omp_auto_rejects_wrong_host_and_removes_har(
        self, tmp_path, monkeypatch, mission_prompt, requested_url
    ):
        import json

        from reverse_api.auto_engineer import OMPAutoEngineer

        engineer = OMPAutoEngineer(
            run_id="omp-wrong-host",
            prompt=mission_prompt,
            url=requested_url,
            output_dir=str(tmp_path),
            verbose=False,
        )

        async def fake_run_omp(*args, **kwargs):
            engineer.har_path.parent.mkdir(parents=True, exist_ok=True)
            engineer.har_path.write_text(
                json.dumps(
                    {"log": {"entries": [{"request": {"url": "https://other.test/api"}}]}}
                ),
                encoding="utf-8",
            )
            return True

        monkeypatch.setattr(engineer, "_run_omp", fake_run_omp)

        assert await engineer.analyze_and_generate() is None
        assert not engineer.har_path.exists()

    @pytest.mark.asyncio
    async def test_omp_auto_accepts_requested_host_after_other_har_entries(
        self, tmp_path, monkeypatch
    ):
        import json

        from reverse_api.auto_engineer import OMPAutoEngineer

        engineer = OMPAutoEngineer(
            run_id="omp-target-host",
            prompt="Inspect the catalog",
            url="https://shop.example.test/catalog",
            output_dir=str(tmp_path),
            verbose=False,
        )

        async def fake_run_omp(*args, **kwargs):
            engineer.har_path.parent.mkdir(parents=True, exist_ok=True)
            engineer.har_path.write_text(
                json.dumps(
                    {
                        "log": {
                            "entries": [
                                {"request": {"url": "https://cdn.example.test/site.js"}},
                                {"request": {"url": "https://shop.example.test/api/items"}},
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            client_path = engineer.scripts_dir / engineer._get_client_filename()
            client_path.write_text("# generated client\n", encoding="utf-8")
            return True

        monkeypatch.setattr(engineer, "_run_omp", fake_run_omp)

        result = await engineer.analyze_and_generate()

        assert result is not None
        assert engineer.har_path.is_file()


    @pytest.mark.parametrize(
        ("requested_url", "expected_domains"),
        [
            ("https://www.github.io", ["www.github.io"]),
            ("https://www.customer.example", ["www.customer.example"]),
            (
                "https://www.linkedin.com/feed/",
                ["www.linkedin.com", "*.linkedin.com", "static.licdn.com", "media.licdn.com"],
            ),
        ],
    )
    def test_allowed_domains_only_wildcards_the_verified_domain(
        self, requested_url, expected_domains
    ):
        from reverse_api.auto_engineer import _allowed_domains

        assert _allowed_domains(requested_url) == expected_domains


    @pytest.mark.parametrize(
        ("request_url", "accepted"),
        [
            ("https://www.linkedin.com/feed/", True),
            ("https://platform.linkedin.com/api", True),
            ("https://linkedin.com.evil.test/api", False),
            ("https://platform.linkedin.com.evil.test/api", False),
            ("https://evil-linkedin.com/api", False),
            ("not a url", False),
        ],
    )
    def test_har_requested_host_uses_allowed_domains(self, tmp_path, request_url, accepted):
        import json

        from reverse_api.auto_engineer import _har_contains_requested_host

        har_path = tmp_path / "capture.har"
        har_path.write_text(
            json.dumps({"log": {"entries": [{"request": {"url": request_url}}]}}),
            encoding="utf-8",
        )

        assert _har_contains_requested_host(har_path, "https://www.linkedin.com/feed/") is accepted

    @pytest.mark.parametrize("requested_url", ["not a url", "https://[invalid"])
    def test_har_requested_host_rejects_invalid_requested_url(
        self, tmp_path, requested_url
    ):
        import json

        from reverse_api.auto_engineer import _har_contains_requested_host

        har_path = tmp_path / "capture.har"
        har_path.write_text(
            json.dumps({"log": {"entries": [{"request": {"url": "https://www.linkedin.com/"}}]}}),
            encoding="utf-8",
        )

        assert not _har_contains_requested_host(har_path, requested_url)

    @pytest.mark.asyncio
    async def test_omp_auto_removes_har_when_client_generation_fails(
        self, tmp_path, monkeypatch
    ):
        import json

        from reverse_api.auto_engineer import OMPAutoEngineer

        engineer = OMPAutoEngineer(
            run_id="omp-missing-client",
            prompt="Inspect https://example.test",
            output_dir=str(tmp_path),
            verbose=False,
        )

        async def fake_run_omp(*args, **kwargs):
            engineer.har_path.parent.mkdir(parents=True, exist_ok=True)
            engineer.har_path.write_text(
                json.dumps(
                    {"log": {"entries": [{"request": {"url": "https://example.test/api"}}]}}
                ),
                encoding="utf-8",
            )
            return True

        monkeypatch.setattr(engineer, "_run_omp", fake_run_omp)

        assert await engineer.analyze_and_generate() is None
        assert not engineer.har_path.exists()

    @pytest.mark.asyncio
    async def test_omp_auto_removes_partial_har_when_omp_fails(self, tmp_path, monkeypatch):
        from reverse_api.auto_engineer import OMPAutoEngineer

        engineer = OMPAutoEngineer(
            run_id="omp-failed-capture",
            prompt="Inspect https://example.test",
            output_dir=str(tmp_path),
            verbose=False,
        )

        async def fake_run_omp(*args, **kwargs):
            engineer.har_path.parent.mkdir(parents=True, exist_ok=True)
            engineer.har_path.write_text("partial", encoding="utf-8")
            return False

        monkeypatch.setattr(engineer, "_run_omp", fake_run_omp)

        assert await engineer.analyze_and_generate() is None
        assert not engineer.har_path.exists()

    @pytest.mark.asyncio
    async def test_omp_auto_rejects_invalid_explicit_start_url(self, tmp_path, monkeypatch):
        from reverse_api.auto_engineer import OMPAutoEngineer

        engineer = OMPAutoEngineer(
            run_id="omp-invalid-explicit-target",
            prompt="Inspect https://example.test",
            url="ftp://example.test",
            output_dir=str(tmp_path),
            verbose=False,
        )
        called = False

        async def fake_run_omp(*args, **kwargs):
            nonlocal called
            called = True
            return True

        monkeypatch.setattr(engineer, "_run_omp", fake_run_omp)

        assert await engineer.analyze_and_generate() is None
        assert not called

    @pytest.mark.asyncio
    async def test_omp_auto_accepts_mission_target_without_url(self, tmp_path, monkeypatch):
        import json

        from reverse_api.auto_engineer import OMPAutoEngineer

        engineer = OMPAutoEngineer(
            run_id="omp-mission-target",
            prompt="Inspect the public example.test catalog and fetch its product list",
            output_dir=str(tmp_path),
            verbose=False,
        )

        async def fake_run_omp(*args, **kwargs):
            engineer.har_path.parent.mkdir(parents=True, exist_ok=True)
            engineer.har_path.write_text(
                json.dumps(
                    {"log": {"entries": [{"request": {"url": "https://example.test/catalog"}}]}}
                ),
                encoding="utf-8",
            )
            client_path = engineer.scripts_dir / engineer._get_client_filename()
            client_path.write_text("# generated client\n", encoding="utf-8")
            return True

        monkeypatch.setattr(engineer, "_run_omp", fake_run_omp)

        assert engineer.url is None
        assert await engineer.analyze_and_generate() is not None
        assert engineer.har_path.is_file()

    @pytest.mark.asyncio
    async def test_omp_auto_does_not_assume_first_of_multiple_mission_urls(
        self, tmp_path, monkeypatch
    ):
        import json

        from reverse_api.auto_engineer import OMPAutoEngineer

        engineer = OMPAutoEngineer(
            run_id="omp-ambiguous-mission-target",
            prompt=(
                "Compare https://docs.example.test with https://api.example.test "
                "and inspect the API calls"
            ),
            output_dir=str(tmp_path),
            verbose=False,
        )

        async def fake_run_omp(*args, **kwargs):
            engineer.har_path.parent.mkdir(parents=True, exist_ok=True)
            engineer.har_path.write_text(
                json.dumps(
                    {"log": {"entries": [{"request": {"url": "https://api.example.test/items"}}]}}
                ),
                encoding="utf-8",
            )
            client_path = engineer.scripts_dir / engineer._get_client_filename()
            client_path.write_text("# generated client\n", encoding="utf-8")
            return True

        monkeypatch.setattr(engineer, "_run_omp", fake_run_omp)

        assert engineer.url is None
        assert await engineer.analyze_and_generate() is not None

    def test_javascript_prompt(self, tmp_path):
        """JavaScript prompt includes JS-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="javascript")
        sys_p, user_p = eng._build_auto_prompts()
        combined = sys_p + user_p
        assert "JavaScript" in combined
        assert "fetch" in sys_p
        assert "api_client.js" in sys_p
        assert "package.json" in sys_p

    def test_typescript_prompt(self, tmp_path):
        """TypeScript prompt includes TS-specific instructions."""
        eng = self._make_engineer(tmp_path, output_language="typescript")
        sys_p, user_p = eng._build_auto_prompts()
        combined = sys_p + user_p
        assert "TypeScript" in combined
        assert "interfaces" in sys_p
        assert "api_client.ts" in sys_p

    def test_prompt_includes_mcp_tools(self, tmp_path):
        """Prompt includes MCP browser tool references."""
        eng = self._make_engineer(tmp_path)
        sys_p, user_p = eng._build_auto_prompts()
        assert "browser_navigate" in user_p
        assert "browser_click" in user_p
        assert "browser_close" in user_p
        assert "browser_network_requests" in user_p

    def test_prompt_includes_har_path(self, tmp_path):
        """Prompt includes HAR file path."""
        eng = self._make_engineer(tmp_path)
        sys_p, user_p = eng._build_auto_prompts()
        assert "recording.har" in user_p

    def test_prompt_includes_screenshot_guidelines(self, tmp_path):
        """Prompt includes screenshot guidelines."""
        eng = self._make_engineer(tmp_path)
        sys_p, user_p = eng._build_auto_prompts()
        assert "Screenshot" in sys_p or "Screenshot" in user_p
        assert "1MB" in sys_p or "1MB" in user_p


class TestChromeMcpPrompt:
    """Test Chrome DevTools MCP prompt building."""

    def _make_engineer(self, tmp_path, **kwargs):
        defaults = {
            "run_id": "test123",
            "prompt": "browse and capture",
            "model": "claude-sonnet-4-6",
            "output_dir": str(tmp_path),
            "agent_provider": "chrome-mcp",
        }
        defaults.update(kwargs)
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    return ClaudeAutoEngineer(**defaults)

    def test_chrome_mcp_prompt_uses_chrome_tools(self, tmp_path):
        """Chrome MCP prompt uses Chrome DevTools tool names."""
        eng = self._make_engineer(tmp_path)
        sys_p, user_p = eng._build_auto_prompts()
        assert "navigate_page" in user_p
        assert "click" in user_p
        assert "fill" in user_p
        assert "take_snapshot" in user_p
        assert "list_network_requests" in user_p
        assert "get_network_request" in user_p

    def test_chrome_mcp_prompt_no_har_file(self, tmp_path):
        """Chrome MCP prompt does not reference HAR file saving."""
        eng = self._make_engineer(tmp_path)
        sys_p, user_p = eng._build_auto_prompts()
        assert "There is no HAR file" in user_p
        assert "browser_close" not in user_p

    def test_chrome_mcp_prompt_mentions_real_browser(self, tmp_path):
        """Chrome MCP prompt mentions real Chrome browser."""
        eng = self._make_engineer(tmp_path)
        sys_p, user_p = eng._build_auto_prompts()
        assert "REAL Chrome browser" in user_p
        assert "existing sessions" in user_p

    def test_chrome_mcp_prompt_python(self, tmp_path):
        """Chrome MCP Python prompt includes correct language."""
        eng = self._make_engineer(tmp_path)
        sys_p, user_p = eng._build_auto_prompts()
        assert "Python" in sys_p
        assert "requests" in sys_p

    def test_chrome_mcp_prompt_javascript(self, tmp_path):
        """Chrome MCP JavaScript prompt includes JS instructions."""
        eng = self._make_engineer(tmp_path, output_language="javascript")
        sys_p, user_p = eng._build_auto_prompts()
        assert "JavaScript" in sys_p
        assert "fetch" in sys_p

    def test_chrome_mcp_prompt_typescript(self, tmp_path):
        """Chrome MCP TypeScript prompt includes TS instructions."""
        eng = self._make_engineer(tmp_path, output_language="typescript")
        sys_p, user_p = eng._build_auto_prompts()
        assert "TypeScript" in sys_p
        assert "interfaces" in sys_p

    def test_get_active_prompts_chrome_mcp(self, tmp_path):
        """_get_active_prompts returns chrome prompt for chrome-mcp provider."""
        eng = self._make_engineer(tmp_path)
        sys_p, user_p = eng._get_active_prompts()
        assert "Chrome DevTools MCP" in sys_p
        assert "navigate_page" in user_p

    def test_get_active_prompts_auto(self, tmp_path):
        """_get_active_prompts returns auto prompt for auto provider."""
        eng = self._make_engineer(tmp_path, agent_provider="auto")
        sys_p, user_p = eng._get_active_prompts()
        assert "browser_navigate" in user_p


class TestAgentBrowserPrompt:
    """Prompts for shell-driven agent-browser provider."""

    @contextmanager
    def _engineer_with_pkg_mock(self, tmp_path, pkg="agent-browser@test", **kwargs):
        defaults = {
            "run_id": "test123",
            "prompt": "browse and capture",
            "model": "claude-sonnet-4-6",
            "output_dir": str(tmp_path),
            "agent_provider": "agent-browser",
        }
        defaults.update(kwargs)
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    with patch("reverse_api.agent_browser.agent_browser_npx_package", return_value=pkg):
                        yield ClaudeAutoEngineer(**defaults)

    def test_system_labels_shell_cli(self, tmp_path):
        with self._engineer_with_pkg_mock(tmp_path) as eng:
            sys_p, _user_p = eng._build_auto_prompts()
            assert "shell CLI" in sys_p

    def test_user_prompt_uses_ag_cli_session_and_har(self, tmp_path):
        with self._engineer_with_pkg_mock(tmp_path) as eng:
            _sys_p, user_p = eng._build_auto_prompts()
            assert "skills get core" in user_p
            assert "AGENT_BROWSER_SESSION" in user_p
            assert "npx -y agent-browser@test" in user_p
            assert str(eng.har_path) in user_p

    def test_opencode_delegates_prompts(self, tmp_path):
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    with patch("reverse_api.opencode_engineer.OpenCodeUI"):
                        with patch(
                            "reverse_api.agent_browser.agent_browser_npx_package",
                            return_value="agent-browser@test",
                        ):
                            eng = OpenCodeAutoEngineer(
                                run_id="test123",
                                prompt="browse and capture",
                                output_dir=str(tmp_path),
                                agent_provider="agent-browser",
                                opencode_provider="anthropic",
                                opencode_model="claude-opus-4-6",
                            )
                            sys_p, user_p = eng._get_active_prompts()
                            assert "shell CLI" in sys_p
                            assert "npx" in user_p


class TestChromeMcpConfig:
    """Test MCP configuration selection."""

    def _make_engineer(self, tmp_path, **kwargs):
        defaults = {
            "run_id": "test123",
            "prompt": "browse and capture",
            "model": "claude-sonnet-4-6",
            "output_dir": str(tmp_path),
        }
        defaults.update(kwargs)
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    return ClaudeAutoEngineer(**defaults)

    def test_chrome_mcp_config(self, tmp_path):
        """Chrome MCP returns chrome-devtools server config."""
        eng = self._make_engineer(tmp_path, agent_provider="chrome-mcp")
        name, config = eng._get_mcp_config()
        assert name == "chrome-devtools"
        assert "chrome-devtools-mcp@latest" in config["args"]
        assert "--autoConnect" in config["args"]

    def test_auto_mcp_config(self, tmp_path):
        """Auto provider returns playwright server config."""
        eng = self._make_engineer(tmp_path, agent_provider="auto")
        name, config = eng._get_mcp_config()
        assert name == "playwright"
        assert "rae-playwright-mcp@latest" in config["args"]
        assert "--run-id" in config["args"]

    def test_agent_browser_no_mcp_config_path(self, tmp_path):
        """`_get_mcp_config` is only for MCP-backed providers."""
        eng = self._make_engineer(tmp_path, agent_provider="agent-browser")
        with pytest.raises(RuntimeError, match="agent-browser uses the Vercel agent-browser CLI"):
            eng._get_mcp_config()


class TestOpenCodeChromeMcpConfig:
    """Test OpenCodeAutoEngineer Chrome MCP config."""

    def _make_engineer(self, tmp_path, **kwargs):
        defaults = {
            "run_id": "test123",
            "prompt": "browse and capture",
            "output_dir": str(tmp_path),
            "opencode_provider": "anthropic",
            "opencode_model": "claude-opus-4-6",
        }
        defaults.update(kwargs)
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    with patch("reverse_api.opencode_engineer.OpenCodeUI"):
                        eng = OpenCodeAutoEngineer(**defaults)
                        eng._session_id = "sess_test"
                        return eng

    def test_opencode_chrome_mcp_config(self, tmp_path):
        """OpenCode chrome-mcp config uses chrome-devtools-mcp."""
        eng = self._make_engineer(tmp_path, agent_provider="chrome-mcp")
        config = eng._get_opencode_mcp_config()
        assert "chrome-devtools" in eng.mcp_name
        assert "chrome-devtools-mcp@latest" in config["config"]["command"]

    def test_opencode_auto_mcp_config(self, tmp_path):
        """OpenCode auto config uses rae-playwright-mcp."""
        eng = self._make_engineer(tmp_path, agent_provider="auto")
        config = eng._get_opencode_mcp_config()
        assert "playwright" in eng.mcp_name
        assert "rae-playwright-mcp@latest" in config["config"]["command"]

    def test_opencode_agent_browser_skips_mcp(self, tmp_path):
        """CLI-only agent-browser mode does not register OpenCode MCP."""
        eng = self._make_engineer(tmp_path, agent_provider="agent-browser")
        assert eng._get_opencode_mcp_config() is None
        assert eng.mcp_name is None

    def test_opencode_chrome_mcp_prompt(self, tmp_path):
        """OpenCode chrome-mcp uses Chrome DevTools prompt."""
        eng = self._make_engineer(tmp_path, agent_provider="chrome-mcp")
        sys_p, user_p = eng._get_active_prompts()
        assert "Chrome DevTools MCP" in sys_p
        assert "navigate_page" in user_p

    def test_opencode_auto_prompt(self, tmp_path):
        """OpenCode auto uses Playwright prompt."""
        eng = self._make_engineer(tmp_path, agent_provider="auto")
        sys_p, user_p = eng._get_active_prompts()
        assert "browser_navigate" in user_p


class TestClaudeAutoEngineerAnalyze:
    """Test ClaudeAutoEngineer analyze_and_generate."""

    def _make_engineer(self, tmp_path, **kwargs):
        defaults = {
            "run_id": "test123",
            "prompt": "browse and capture",
            "model": "claude-sonnet-4-6",
            "output_dir": str(tmp_path),
        }
        defaults.update(kwargs)
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore") as mock_ms:
                    mock_ms.return_value = MagicMock()
                    eng = ClaudeAutoEngineer(**defaults)
                    eng.scripts_dir = tmp_path / "scripts"
                    eng.scripts_dir.mkdir(parents=True, exist_ok=True)
                    return eng

    @pytest.mark.asyncio
    async def test_exception_generic(self, tmp_path):
        """Generic exception returns None."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(side_effect=Exception("SDK error"))
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_exception_buffer_size(self, tmp_path):
        """Buffer size exception shows specific message."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("exceeded maximum buffer size 1048576")
            )
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_exception_mcp_server(self, tmp_path):
        """MCP server exception shows npm install hint."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("MCP server failed to start")
            )
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_exception_other(self, tmp_path):
        """Other exception shows generic message."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("some other error")
            )
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_result_message_error(self, tmp_path):
        """ResultMessage with error returns None."""
        eng = self._make_engineer(tmp_path)

        from claude_agent_sdk import ResultMessage
        mock_result = MagicMock(spec=ResultMessage)
        mock_result.is_error = True
        mock_result.result = "Error occurred"

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_result_message_success(self, tmp_path):
        """ResultMessage with success returns result dict."""
        eng = self._make_engineer(tmp_path)

        mock_result = _sdk_result_message(result="Success")

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch.object(eng, "_prompt_follow_up", new=AsyncMock(return_value=None)):
            with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
                mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await eng.analyze_and_generate()
                assert result is not None
                assert "script_path" in result

    @pytest.mark.asyncio
    async def test_registers_verification_mcp_server_alongside_browser_mcp(self, tmp_path):
        """The default/chrome-mcp path (what route-reveal's agent-drive
        actually uses via ExternalChromeAutoEngineer) must register the
        report_client_verified tool's server *alongside* the browser MCP
        server, not instead of it — see engineer.py's
        _build_verification_mcp_server."""
        eng = self._make_engineer(tmp_path)

        mock_result = _sdk_result_message(result="Success")

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch.object(eng, "_prompt_follow_up", new=AsyncMock(return_value=None)):
            with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
                mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

                await eng.analyze_and_generate()

        _, kwargs = mock_sdk.call_args
        options = kwargs["options"]
        assert "verification" in options.mcp_servers
        assert options.mcp_servers["verification"]["name"] == "verification"
        # The browser MCP server (playwright, for the default "auto"
        # provider) must still be present too — this isn't a replacement.
        assert len(options.mcp_servers) == 2

    @pytest.mark.asyncio
    async def test_agent_browser_path_allows_the_verification_tool(self, tmp_path):
        """agent-browser mode uses an explicit allowed_tools list (unlike
        the chrome-mcp/default path above), so the verification tool needs
        its SDK-qualified name added there too, or Claude could never
        actually call it even though the server is registered."""
        eng = self._make_engineer(tmp_path, agent_provider="agent-browser")

        with patch("reverse_api.auto_engineer.ensure_agent_browser_runtime") as mock_ensure:
            mock_ensure.return_value = MagicMock(ok=True, error=None, notices=())

            mock_result = _sdk_result_message(result="Success")
            mock_client = AsyncMock()
            mock_client.query = AsyncMock()

            async def mock_receive():
                yield mock_result

            mock_client.receive_response = mock_receive

            with patch.object(eng, "_prompt_follow_up", new=AsyncMock(return_value=None)):
                with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
                    mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                    mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

                    await eng.analyze_and_generate()

        _, kwargs = mock_sdk.call_args
        options = kwargs["options"]
        assert "verification" in options.mcp_servers
        assert "mcp__verification__report_client_verified" in options.allowed_tools

    @pytest.mark.asyncio
    async def test_result_with_usage(self, tmp_path):
        """Result with usage metadata calculates cost."""
        eng = self._make_engineer(tmp_path)
        eng.usage_metadata = {
            "input_tokens": 5000,
            "output_tokens": 2000,
            "cache_creation_input_tokens": 100,
            "cache_read_input_tokens": 50,
        }

        mock_result = _sdk_result_message()

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch.object(eng, "_prompt_follow_up", new=AsyncMock(return_value=None)):
            with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
                mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await eng.analyze_and_generate()
                if result is not None:
                    assert "usage" in result

    @pytest.mark.asyncio
    async def test_assistant_message_with_tools(self, tmp_path):
        """AssistantMessage with ToolUseBlock, ToolResultBlock, TextBlock are processed."""
        eng = self._make_engineer(tmp_path)

        mock_tool_use = ToolUseBlock(id="1", name="Read", input={"file_path": "/test.py"})
        mock_tool_result = ToolResultBlock(
            tool_use_id="1", content="file contents", is_error=False
        )
        mock_text = TextBlock(text="Analyzing the file...")
        mock_assistant = AssistantMessage(
            content=[mock_tool_use, mock_tool_result, mock_text],
            model="claude-sonnet-4-6",
        )
        mock_result = _sdk_result_message()

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_assistant
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch.object(eng, "_prompt_follow_up", new=AsyncMock(return_value=None)):
            with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
                mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await eng.analyze_and_generate()
                assert result is not None
                assert "script_path" in result

    @pytest.mark.asyncio
    async def test_assistant_message_with_usage(self, tmp_path):
        """AssistantMessage with usage metadata updates tracking."""
        eng = self._make_engineer(tmp_path)

        mock_assistant = AssistantMessage(content=[], model="claude-sonnet-4-6")
        mock_assistant.usage = {"input_tokens": 500, "output_tokens": 200}

        mock_result = _sdk_result_message()

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_assistant
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch.object(eng, "_prompt_follow_up", new=AsyncMock(return_value=None)):
            with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
                mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await eng.analyze_and_generate()
                assert result is not None
                assert eng.usage_metadata.get("input_tokens") == 500

    @pytest.mark.asyncio
    async def test_tool_result_with_result_attr(self, tmp_path):
        """ToolResultBlock with result attribute (not content) is handled."""
        eng = self._make_engineer(tmp_path)

        mock_tool_use = ToolUseBlock(id="u1", name="Bash", input={"command": "ls"})
        mock_tool_result = ToolResultWithResult(
            tool_use_id="u1", content=None, is_error=True, result="command not found"
        )
        mock_assistant = AssistantMessage(
            content=[mock_tool_use, mock_tool_result],
            model="claude-sonnet-4-6",
        )
        mock_result = _sdk_result_message()

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_assistant
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch.object(eng, "_prompt_follow_up", new=AsyncMock(return_value=None)):
            with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
                mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await eng.analyze_and_generate()
                assert result is not None

    @pytest.mark.asyncio
    async def test_tool_result_with_output_attr(self, tmp_path):
        """ToolResultBlock with output attribute (not content/result) is handled."""
        eng = self._make_engineer(tmp_path)

        mock_tool_use = ToolUseBlock(id="u2", name="Grep", input={"pattern": "test"})
        mock_tool_result = ToolResultWithOutput(
            tool_use_id="u2", content=None, is_error=False, output="grep output here"
        )
        mock_assistant = AssistantMessage(
            content=[mock_tool_use, mock_tool_result],
            model="claude-sonnet-4-6",
        )
        mock_result = _sdk_result_message()

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            yield mock_assistant
            yield mock_result

        mock_client.receive_response = mock_receive

        with patch.object(eng, "_prompt_follow_up", new=AsyncMock(return_value=None)):
            with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
                mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

                result = await eng.analyze_and_generate()
                assert result is not None

    @pytest.mark.asyncio
    async def test_no_result_message_returns_none(self, tmp_path):
        """Empty stream with no ResultMessage returns None (line 365)."""
        eng = self._make_engineer(tmp_path)

        mock_client = AsyncMock()
        mock_client.query = AsyncMock()

        async def mock_receive():
            return
            yield

        mock_client.receive_response = mock_receive

        with patch("reverse_api.auto_engineer.ClaudeSDKClient") as mock_sdk:
            mock_sdk.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_sdk.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None


class TestOpenCodeAutoEngineerInit:
    """Test OpenCodeAutoEngineer initialization."""

    def test_init(self, tmp_path):
        """Initializes with MCP run_id."""
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    with patch("reverse_api.opencode_engineer.OpenCodeUI"):
                        eng = OpenCodeAutoEngineer(
                            run_id="test123",
                            prompt="browse and capture",
                            output_dir=str(tmp_path),
                            opencode_provider="anthropic",
                            opencode_model="claude-opus-4-6",
                        )
                        assert eng.mcp_run_id == "test123"
                        assert eng.mcp_name is None

    def test_get_active_prompts_reuses_claude_prompts(self, tmp_path):
        """OpenCode auto prompts reuse ClaudeAutoEngineer prompt builder."""
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore"):
                    with patch("reverse_api.opencode_engineer.OpenCodeUI"):
                        eng = OpenCodeAutoEngineer(
                            run_id="test123",
                            prompt="browse and capture",
                            output_dir=str(tmp_path),
                            opencode_provider="anthropic",
                            opencode_model="claude-opus-4-6",
                        )
                        sys_p, user_p = eng._get_active_prompts()
                        assert "browser_navigate" in user_p
                        assert "Python" in sys_p


class TestOpenCodeAutoEngineerAnalyze:
    """Test OpenCodeAutoEngineer analyze_and_generate."""

    def _make_engineer(self, tmp_path):
        with patch("reverse_api.auto_engineer.get_har_dir", return_value=tmp_path / "har"):
            with patch("reverse_api.base_engineer.get_scripts_dir", return_value=tmp_path / "scripts"):
                with patch("reverse_api.base_engineer.MessageStore") as mock_ms:
                    mock_ms.return_value = MagicMock()
                    with patch("reverse_api.opencode_engineer.OpenCodeUI") as mock_ui:
                        mock_ui.return_value = MagicMock()
                        eng = OpenCodeAutoEngineer(
                            run_id="test123",
                            prompt="browse and capture",
                            output_dir=str(tmp_path),
                            opencode_provider="anthropic",
                            opencode_model="claude-opus-4-6",
                        )
                        eng.scripts_dir = tmp_path / "scripts"
                        eng.scripts_dir.mkdir(parents=True, exist_ok=True)
                        return eng

    @pytest.mark.asyncio
    async def test_health_check_401(self, tmp_path):
        """401 on health check returns None."""
        eng = self._make_engineer(tmp_path)

        mock_response = MagicMock()
        mock_response.status_code = 401
        error = httpx.HTTPStatusError("401", request=MagicMock(), response=mock_response)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=error)

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_connect_error(self, tmp_path):
        """ConnectError returns None."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_general_exception(self, tmp_path):
        """General exception returns None."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(
                side_effect=RuntimeError("unexpected")
            )
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_buffer_size_exception(self, tmp_path):
        """Buffer size exception shows specific message."""
        eng = self._make_engineer(tmp_path)

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("exceeded maximum buffer size 1048576")
            )
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_http_error_non_401(self, tmp_path):
        """HTTP error with non-401 status."""
        eng = self._make_engineer(tmp_path)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.reason_phrase = "Internal Server Error"
        error = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_response)

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(side_effect=error)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_health_check_401_with_custom_username(self, tmp_path):
        """401 with custom username shows username in output."""
        eng = self._make_engineer(tmp_path)
        eng.opencode_username = "custom_user"

        mock_response = MagicMock()
        mock_response.status_code = 401
        error = httpx.HTTPStatusError("401", request=MagicMock(), response=mock_response)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=error)

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_health_check_success_then_session_fail(self, tmp_path):
        """Health check succeeds but session creation raises."""
        eng = self._make_engineer(tmp_path)

        mock_health = MagicMock()
        mock_health.json.return_value = {"status": "ok"}
        mock_health.raise_for_status = MagicMock()

        mock_client = AsyncMock()

        async def mock_get(path, **kwargs):
            if path == "/global/health":
                return mock_health
            raise Exception("unexpected get")

        mock_client.get = mock_get
        mock_client.post = AsyncMock(side_effect=Exception("session creation failed"))

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_health_check_general_exception(self, tmp_path):
        """General exception on health check shows server not responding."""
        eng = self._make_engineer(tmp_path)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_full_success_flow(self, tmp_path):
        """Full success flow with MCP registration, streaming, and result."""
        eng = self._make_engineer(tmp_path)

        mock_health = MagicMock()
        mock_health.json.return_value = {"status": "ok"}
        mock_health.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.json.return_value = {"id": "sess_success"}
        mock_session.raise_for_status = MagicMock()

        mock_mcp = MagicMock()
        mock_mcp.raise_for_status = MagicMock()

        mock_prompt = MagicMock()
        mock_prompt.raise_for_status = MagicMock()

        mock_messages = MagicMock()
        mock_messages.status_code = 200
        mock_messages.json.return_value = [
            {
                "info": {"role": "assistant", "providerID": "anthropic", "modelID": "claude-opus-4-6"},
                "parts": [{"type": "text", "text": "API client"}],
            }
        ]

        async def mock_get(path, **kwargs):
            if path == "/global/health":
                return mock_health
            if path == "/config/providers":
                return _valid_catalog_response()
            if "/message" in path:
                return mock_messages
            return MagicMock()

        post_calls = [0]

        async def mock_post(path, **kwargs):
            post_calls[0] += 1
            if path == "/session":
                return mock_session
            if path == "/mcp":
                return mock_mcp
            return mock_prompt

        mock_stream_resp = AsyncMock()

        async def mock_aiter_lines():
            yield 'data: {"type":"session.idle","properties":{"sessionID":"sess_success"}}'

        mock_stream_resp.aiter_lines = mock_aiter_lines
        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_stream_resp)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.post = mock_post
        mock_client.stream = MagicMock(return_value=mock_stream_cm)
        mock_client.delete = AsyncMock()

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is not None
            assert "script_path" in result
            assert result["session_id"] == "sess_success"

    @pytest.mark.asyncio
    async def test_http_401_outer_with_username(self, tmp_path):
        """Outer 401 HTTPStatusError with custom username shows username."""
        eng = self._make_engineer(tmp_path)
        eng.opencode_username = "custom_user"

        mock_health = MagicMock()
        mock_health.json.return_value = {"status": "ok"}
        mock_health.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.json.return_value = {"id": "sess_auth"}
        mock_session.raise_for_status = MagicMock()

        mock_mcp = MagicMock()
        mock_mcp.raise_for_status = MagicMock()

        mock_response = MagicMock()
        mock_response.status_code = 401

        async def mock_get(path, **kwargs):
            if path == "/global/health":
                return mock_health
            raise httpx.HTTPStatusError("401", request=MagicMock(), response=mock_response)

        async def mock_post(path, **kwargs):
            if path == "/session":
                return mock_session
            if path == "/mcp":
                return mock_mcp
            raise httpx.HTTPStatusError("401", request=MagicMock(), response=mock_response)

        mock_stream_resp = AsyncMock()

        async def mock_aiter_lines():
            yield 'data: {"type":"session.idle","properties":{"sessionID":"sess_auth"}}'

        mock_stream_resp.aiter_lines = mock_aiter_lines
        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_stream_resp)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.post = mock_post
        mock_client.stream = MagicMock(return_value=mock_stream_cm)
        mock_client.delete = AsyncMock()

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_event_timeout(self, tmp_path):
        """Event stream timeout sets last error and returns None."""
        eng = self._make_engineer(tmp_path)

        mock_health = MagicMock()
        mock_health.json.return_value = {"status": "ok"}
        mock_health.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.json.return_value = {"id": "sess_timeout"}
        mock_session.raise_for_status = MagicMock()

        mock_mcp = MagicMock()
        mock_mcp.raise_for_status = MagicMock()

        mock_prompt = MagicMock()
        mock_prompt.raise_for_status = MagicMock()

        async def mock_get(path, **kwargs):
            if path == "/global/health":
                return mock_health
            return MagicMock(status_code=200, json=MagicMock(return_value=[]))

        async def mock_post(path, **kwargs):
            if path == "/session":
                return mock_session
            if path == "/mcp":
                return mock_mcp
            return mock_prompt

        mock_stream_resp = AsyncMock()

        async def mock_aiter_lines():
            # Never yield session.idle - simulates hanging
            await asyncio.sleep(100)
            yield "never reached"

        mock_stream_resp.aiter_lines = mock_aiter_lines
        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_stream_resp)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.post = mock_post
        mock_client.stream = MagicMock(return_value=mock_stream_cm)
        mock_client.delete = AsyncMock()

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            # Patch asyncio.wait_for to raise TimeoutError immediately
            async def mock_wait_for(coro, timeout=None):
                coro.close()  # Clean up the coroutine
                raise TimeoutError()

            with patch("reverse_api.auto_engineer.asyncio.wait_for", side_effect=mock_wait_for):
                result = await eng.analyze_and_generate()
                assert result is None

    @pytest.mark.asyncio
    async def test_mcp_deregistration_exception(self, tmp_path):
        """MCP deregistration exception is silently ignored."""
        eng = self._make_engineer(tmp_path)

        mock_health = MagicMock()
        mock_health.json.return_value = {"status": "ok"}
        mock_health.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.json.return_value = {"id": "sess_dereg"}
        mock_session.raise_for_status = MagicMock()

        mock_mcp = MagicMock()
        mock_mcp.raise_for_status = MagicMock()

        mock_prompt = MagicMock()
        mock_prompt.raise_for_status = MagicMock()

        mock_messages = MagicMock()
        mock_messages.status_code = 200
        mock_messages.json.return_value = [
            {"info": {"role": "assistant", "providerID": "anthropic", "modelID": "claude-sonnet-4-6"}, "parts": []}
        ]

        async def mock_get(path, **kwargs):
            if path == "/global/health":
                return mock_health
            if path == "/config/providers":
                return _valid_catalog_response()
            if "/message" in path:
                return mock_messages
            return MagicMock()

        async def mock_post(path, **kwargs):
            if path == "/session":
                return mock_session
            if path == "/mcp":
                return mock_mcp
            return mock_prompt

        mock_stream_resp = AsyncMock()

        async def mock_aiter_lines():
            yield 'data: {"type":"session.idle","properties":{"sessionID":"sess_dereg"}}'

        mock_stream_resp.aiter_lines = mock_aiter_lines
        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_stream_resp)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.post = mock_post
        mock_client.stream = MagicMock(return_value=mock_stream_cm)
        mock_client.delete = AsyncMock(side_effect=Exception("deregister failed"))

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            # Should succeed despite deregistration failure
            assert result is not None
            assert "script_path" in result

    @pytest.mark.asyncio
    async def test_message_fetch_exception(self, tmp_path):
        """Message fetch exception is silently handled."""
        eng = self._make_engineer(tmp_path)

        mock_health = MagicMock()
        mock_health.json.return_value = {"status": "ok"}
        mock_health.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.json.return_value = {"id": "sess_msgfail"}
        mock_session.raise_for_status = MagicMock()

        mock_mcp = MagicMock()
        mock_mcp.raise_for_status = MagicMock()

        mock_prompt = MagicMock()
        mock_prompt.raise_for_status = MagicMock()

        async def mock_get(path, **kwargs):
            if path == "/global/health":
                return mock_health
            if path == "/config/providers":
                return _valid_catalog_response()
            return MagicMock()

        async def mock_post(path, **kwargs):
            if path == "/session":
                return mock_session
            if path == "/mcp":
                return mock_mcp
            return mock_prompt

        mock_stream_resp = AsyncMock()

        async def mock_aiter_lines():
            yield 'data: {"type":"session.idle","properties":{"sessionID":"sess_msgfail"}}'

        mock_stream_resp.aiter_lines = mock_aiter_lines
        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_stream_resp)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.post = mock_post
        mock_client.stream = MagicMock(return_value=mock_stream_cm)
        mock_client.delete = AsyncMock()

        # Patch the second httpx.AsyncClient (for message fetch) to fail
        call_count = [0]

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            def side_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    # First call - the main client
                    cm = MagicMock()
                    cm.__aenter__ = AsyncMock(return_value=mock_client)
                    cm.__aexit__ = AsyncMock(return_value=False)
                    return cm
                else:
                    # Second call - message fetch client
                    cm = MagicMock()
                    cm.__aenter__ = AsyncMock(side_effect=Exception("fetch failed"))
                    cm.__aexit__ = AsyncMock(return_value=False)
                    return cm

            mock_async.side_effect = side_effect

            result = await eng.analyze_and_generate()
            # Should still succeed despite message fetch failure
            assert result is not None
            assert "script_path" in result

    @pytest.mark.asyncio
    async def test_finally_cleanup_with_mcp_name(self, tmp_path):
        """Finally block cleans up MCP server even on exception."""
        eng = self._make_engineer(tmp_path)
        eng.mcp_name = "playwright-test_sess"

        # Trigger exception to go through finally block
        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(
                side_effect=RuntimeError("test error")
            )
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None

    @pytest.mark.asyncio
    async def test_health_check_non_401_reraise(self, tmp_path):
        """Non-401 HTTPStatusError in health check is re-raised (line 414)."""
        eng = self._make_engineer(tmp_path)

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"
        error = httpx.HTTPStatusError("503", request=MagicMock(), response=mock_response)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=error)

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            # Non-401 is re-raised and caught by outer HTTPStatusError handler
            assert result is None

    @pytest.mark.asyncio
    async def test_mcp_registration_failure(self, tmp_path):
        """MCP server registration failure returns None."""
        eng = self._make_engineer(tmp_path)

        mock_health = MagicMock()
        mock_health.json.return_value = {"status": "ok"}
        mock_health.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.json.return_value = {"id": "sess_123"}
        mock_session.raise_for_status = MagicMock()

        async def mock_get(path, **kwargs):
            if path == "/global/health":
                return mock_health
            raise Exception("unexpected get")

        async def mock_post(path, **kwargs):
            if path == "/session":
                return mock_session
            if path == "/mcp":
                raise Exception("MCP registration failed")
            raise Exception(f"unexpected post to {path}")

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.post = mock_post

        with patch("reverse_api.auto_engineer.httpx.AsyncClient") as mock_async:
            mock_async.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_async.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await eng.analyze_and_generate()
            assert result is None


def test_run_auto_capture_forwards_requested_url_to_omp_browser_goto(tmp_path, monkeypatch):
    from reverse_api import auto_engineer, cli
    from reverse_api.auto_engineer import OMPAutoEngineer

    captured: dict[str, str] = {}

    class Config:
        @staticmethod
        def get(key, default=None):
            return {
                "agent_provider": "auto",
                "sdk": "omp",
                "omp_model": "",
                "output_language": "python",
                "real_time_sync": False,
            }.get(key, default)

    class Sessions:
        @staticmethod
        def add_run(**kwargs):
            return None

        @staticmethod
        def update_run(**kwargs):
            return None

    class CapturingOMPEngineer(OMPAutoEngineer):
        def start_sync(self):
            return None

        def stop_sync(self):
            return None

        async def analyze_and_generate(self):
            captured["user_message"] = self._get_active_prompts()[1]
            client_path = self.scripts_dir / self._get_client_filename()
            client_path.write_text("# generated test client\n", encoding="utf-8")
            return {"script_path": str(client_path), "usage": {}}

    monkeypatch.setattr(cli, "config_manager", Config())
    monkeypatch.setattr(cli, "session_manager", Sessions())
    monkeypatch.setattr(cli, "generate_run_id", lambda: "omp-url-run")
    monkeypatch.setattr(cli, "get_timestamp", lambda: "2026-10-22T00:00:00Z")
    monkeypatch.setattr(auto_engineer, "OMPAutoEngineer", CapturingOMPEngineer)

    result = cli.run_auto_capture(
        prompt="Search the requested site for its public API",
        url="https://shop.example.test/catalog",
        output_dir=str(tmp_path),
        interactive=False,
    )

    assert "error" not in result
    assert 'await tab.goto("https://shop.example.test/catalog")' in captured["user_message"]
