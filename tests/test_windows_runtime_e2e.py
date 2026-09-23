"""Opt-in Windows acceptance with installed Chrome and the real OpenCode runtime.

Run in the prepared live-windows job; no model or production site is accessed.
"""

import asyncio
import json
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import httpx2
import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("RAE_WINDOWS_RUNTIME_E2E") != "1",
    reason="opt-in native Windows runtime acceptance",
)


@pytest.mark.parametrize("finish", ["close", "interrupt"])
def test_chrome_capture_finalizes_har(tmp_path, monkeypatch, finish):
    from playwright.sync_api import BrowserType, Page

    from reverse_api.browser import ManualBrowser

    api_seen = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if self.path == "/api":
                body = json.dumps({"name": "中文 — café"}, ensure_ascii=False).encode("utf-8")
                content_type = "application/json; charset=utf-8"
                api_seen.set()
            else:
                body = b'<script>fetch("/api").then(r=>r.json()).then(r=>document.title=r.name)</script>'
                content_type = "text/html"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    # Supply an isolated discovery path; the actual browser still uses channel=chrome.
    local_appdata = tmp_path / "Local AppData"
    (local_appdata / "Google/Chrome/User Data").mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    browser = ManualBrowser("windows-capture", "Unicode capture", output_dir=str(tmp_path))
    launch = BrowserType.launch_persistent_context
    wait = Page.wait_for_timeout
    deadline = time.monotonic() + 30
    result_seen = False

    def headless_launch(self, *args, **kwargs):
        kwargs["headless"] = True
        return launch(self, *args, **kwargs)

    def finish_capture(page, timeout):
        nonlocal result_seen
        wait(page, timeout)
        if time.monotonic() > deadline:
            raise TimeoutError("Chrome did not fetch the fixture API")
        if api_seen.is_set() and page.title() == "中文 — café":
            result_seen = True
            if finish == "interrupt":
                # Exercise the exact SIGINT callback after real traffic; console
                # event delivery itself is outside this deterministic check.
                browser._handle_signal(2, None)
            else:
                page.close()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    import signal

    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        with patch.object(BrowserType, "launch_persistent_context", headless_launch), patch.object(Page, "wait_for_timeout", finish_capture):
            url = f"http://127.0.0.1:{server.server_port}"
            if finish == "interrupt":
                with pytest.raises(SystemExit) as interrupted:
                    browser.start(url)
                assert interrupted.value.code == 0
            else:
                assert browser.start(url) == browser.har_path
        assert result_seen, "Chrome must finish fetching the fixture response"
        entries = json.loads(browser.har_path.read_text(encoding="utf-8"))["log"]["entries"]
        api_entry = next(entry for entry in entries if entry["request"]["url"] == f"{url}/api")
        assert json.loads(api_entry["response"]["content"]["text"]) == {"name": "中文 — café"}
        assert browser.metadata_path.is_file()
        assert browser._playwright is None
    finally:
        browser._abort_playwright()
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_managed_opencode_releases_listener(tmp_path, monkeypatch):
    from reverse_api import opencode_runtime

    for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "OPENCODE_CONFIG_DIR"):
        monkeypatch.setenv(key, str(tmp_path / key))
    monkeypatch.setenv("OPENCODE_CONFIG_CONTENT", '{"share":"disabled"}')
    monkeypatch.setenv("RAE_OPENCODE_PACKAGE", "opencode-ai@1.18.31")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"

    async def start():
        async with httpx2.AsyncClient(base_url=base_url) as client:
            return await opencode_runtime.ensure_opencode_server(client, base_url=base_url)

    try:
        status = asyncio.run(start())
        assert status.started
    finally:
        opencode_runtime.stop_managed_opencode_server()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.2)
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return
        time.sleep(0.1)
    pytest.fail("OpenCode still listens after its managed launcher was stopped")
