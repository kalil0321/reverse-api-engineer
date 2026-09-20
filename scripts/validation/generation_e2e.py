"""Opt-in local acceptance: browser capture -> free model -> client -> fresh API data.

Run with the Python environment containing the version of RAE to test. All test
configuration and artifacts live in a new directory; user settings are untouched.
No model mock, production website, credentials, or paid-model fallback is used.
"""

import argparse
import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path

import httpx2

from reverse_api.opencode_runtime import (
    ensure_opencode_server,
    get_opencode_model_catalog,
    opencode_model_is_selectable,
    stop_managed_opencode_server,
)


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), FixtureHandler)
        self.nonce = secrets.token_hex(16)
        self.page_hits = 0
        self.api_hits = 0

    def payload(self):
        return {"items": [{"id": 1, "name": "sample product"}], "nonce": self.nonce}


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == "/":
            self.server.page_hits += 1
            data = (
                b'<!doctype html><title>CI catalog</title><h1>Product catalog</h1>'
                b'<button onclick="load()">Load products</button><pre id="result"></pre>'
                b'<script>async function load(){const r=await fetch("/api/products");'
                b'document.querySelector("#result").textContent=JSON.stringify(await r.json());}'
                b'load();</script>'
            )
            content_type = "text/html; charset=utf-8"
        elif self.path == "/api/products":
            self.server.api_hits += 1
            data = json.dumps(self.server.payload()).encode()
            content_type = "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


async def require_free_model(base_url, model_id):
    async with httpx2.AsyncClient(base_url=base_url) as client:
        await ensure_opencode_server(client, base_url=base_url)
        catalog = await get_opencode_model_catalog(client)
    provider = next((p for p in catalog["providers"] if p.get("id") == "opencode"), {})
    model = provider.get("models", {}).get(model_id, {})
    cost = model.get("cost", {})
    if not opencode_model_is_selectable(model) or cost.get("input") != 0 or cost.get("output") != 0:
        raise RuntimeError(f"opencode/{model_id} is unavailable or not explicitly free; no fallback allowed")
    return {"provider": "opencode", "model": model_id, "cost": cost}


def invoke_cli(args, cwd, timeout):
    result = subprocess.run(
        [sys.executable, "-c",
         "import os; from pathlib import Path; import reverse_api.utils as u; "
         "u.get_app_dir = lambda: Path(os.environ['RAE_E2E_CONFIG_DIR']); "
         "from reverse_api.cli import main; main()", *args],
        cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
    )
    (Path(cwd) / f"{args[0]}.stdout.log").write_text(result.stdout, encoding="utf-8")
    (Path(cwd) / f"{args[0]}.stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"CLI {args[0]} failed ({result.returncode})\n{result.stderr[-6000:]}\n{result.stdout[-6000:]}")
    payload = json.loads(result.stdout)
    if payload.get("status") != "ok":
        raise RuntimeError(f"CLI {args[0]} did not succeed: {payload}")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--language", choices=["python", "powershell"], required=True)
    parser.add_argument("--artifacts-dir", type=Path, help="New directory to retain logs and generated files")
    args = parser.parse_args()
    if args.artifacts_dir:
        directory = args.artifacts_dir.resolve()
        directory.mkdir(parents=True, exist_ok=False)
    else:
        directory = Path(tempfile.mkdtemp(prefix="rae live ")).resolve()
    print(f"Artifacts: {directory}", file=sys.stderr, flush=True)
    model = "big-pickle"
    config_dir = directory / "rae-config"
    config_dir.mkdir(exist_ok=True)
    config_path = config_dir / "config.json"
    if config_path.exists():
        raise SystemExit("Refusing to overwrite an existing RAE configuration")
    import reverse_api.utils as utils

    utils.get_app_dir = lambda: config_dir
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        base_url = f"http://127.0.0.1:{probe.getsockname()[1]}"
    os.environ.update({
        "RAE_E2E_CONFIG_DIR": str(config_dir),
        "OPENCODE_BASE_URL": base_url,
        "XDG_CONFIG_HOME": str(directory / "xdg-config"),
        "XDG_DATA_HOME": str(directory / "xdg-data"),
        "XDG_CACHE_HOME": str(directory / "xdg-cache"),
        "XDG_STATE_HOME": str(directory / "xdg-state"),
        "OPENCODE_CONFIG_DIR": str(directory / "opencode-config"),
        "OPENCODE_CONFIG_CONTENT": json.dumps({
            "enabled_providers": ["opencode"], "model": "opencode/big-pickle",
            "small_model": "opencode/big-pickle", "share": "disabled",
            "provider": {"opencode": {"whitelist": ["big-pickle"]}},
        }),
        "PLAYWRIGHT_MCP_ISOLATED": "true",
        "PLAYWRIGHT_MCP_SAVE_HAR_PATH": str(config_dir / "runs" / "har"),
    })
    # Do not inherit optional provider credentials or external config overrides.
    for key in list(os.environ):
        if key.endswith(("_API_KEY", "_AUTH_TOKEN")) or key in {"OPENCODE_CONFIG", "OPENCODE_SERVER_PASSWORD"}:
            os.environ.pop(key)
    config_path.write_text(json.dumps({
        "sdk": "opencode", "opencode_provider": "opencode", "opencode_model": model,
        "output_language": args.language, "real_time_sync": False, "agent_provider": "auto",
    }), encoding="utf-8")
    os.environ["RAE_OPENCODE_PACKAGE"] = "opencode-ai@1.18.31"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    server = FixtureServer()
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    os.chdir(directory)
    try:
        model_info = asyncio.run(require_free_model(base_url, model))
        (directory / "model.json").write_text(json.dumps(model_info, indent=2), encoding="utf-8")
        url = f"http://127.0.0.1:{server.server_port}"
        prompt = (
            f"Open {url} using the browser MCP and load the products. Capture the API traffic. "
            f"Generate a {args.language} client for the products API. Its example/main must "
            "fetch the current response and print exactly that response as JSON, without labels. "
            "Do not hardcode response data. Preserve all response fields. Test the client. "
            "Use only this local website, no authentication and no external API."
        )
        generated = invoke_cli(["agent", "--headless", "--json", "--url", url, "--prompt", prompt], directory, 600)
        script = Path(generated["script_path"])
        expected_name = "api_client.psm1" if args.language == "powershell" else "api_client.py"
        if script.name != expected_name or not script.is_file() or not script.stat().st_size:
            raise RuntimeError("Generation did not create the requested client")
        har = Path(generated.get("har_path") or "missing.har")
        if not har.is_file():
            raise RuntimeError("Browser capture did not produce a HAR")
        entries = json.loads(har.read_text(encoding="utf-8"))["log"]["entries"]
        if not any(e["request"]["url"] == f"{url}/api/products" for e in entries):
            raise RuntimeError("HAR does not contain the fixture API request")
        if not server.page_hits or not server.api_hits:
            raise RuntimeError("The fixture website and API were not visited")
        # A new value unavailable during generation rejects cached/hardcoded examples.
        server.nonce = secrets.token_hex(16)
        previous_hits = server.api_hits
        replayed = invoke_cli([
            "run", generated["run_id"], "--file", expected_name, "--json", "--auto-install",
        ], directory, 120)
        if replayed.get("returncode") != 0 or json.loads(replayed["stdout"]) != server.payload():
            raise RuntimeError("Generated client did not return fresh, correct API data")
        if server.api_hits <= previous_hits:
            raise RuntimeError("Client replay never contacted the API")
        report = {"status": "ok", "language": args.language, "model": f"opencode/{model}",
                  "package_version": version("reverse-api-engineer"), "script_path": str(script),
                  "har_entries": len(entries), "page_hits": server.page_hits, "api_hits": server.api_hits,
                  "fresh_response_verified": True}
        (directory / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report))
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        stop_managed_opencode_server()


if __name__ == "__main__":
    main()
