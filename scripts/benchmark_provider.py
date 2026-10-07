"""Isolated HTTP benchmark for the model-provider boundary."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SECRET = "provider-boundary-benchmark-secret"


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def local_json(url: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class MockProvider(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
        model = str(payload.get("model", ""))
        if model == "mock/fail":
            self.send_response(503)
            self.end_headers()
            return
        response = {"model": model, "choices": [{"message": {"content": f"{model} 已生效。"}}]}
        raw = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def wait_for_app(base_url: str, process: subprocess.Popen[bytes]) -> None:
    for _ in range(50):
        if process.poll() is not None:
            raise RuntimeError("isolated application exited before health check")
        try:
            if local_json(f"{base_url}/api/health", timeout=2).get("status") == "ok":
                return
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
            time.sleep(0.1)
    raise TimeoutError("isolated application did not become ready")


def main() -> int:
    provider_port, app_port = available_port(), available_port()
    provider = ThreadingHTTPServer(("127.0.0.1", provider_port), MockProvider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    provider_url, app_url = f"http://127.0.0.1:{provider_port}/v1", f"http://127.0.0.1:{app_port}"
    with tempfile.TemporaryDirectory(prefix="flexresearch-provider-benchmark-") as temp_dir:
        env = {**os.environ, "FLEXRESEARCH_DATA_DIR": temp_dir, "OPENAI_API_KEY": SECRET, "OPENAI_BASE_URL": provider_url, "OPENAI_MODEL": "mock/alpha"}
        code = f"from app import app, init_db; init_db(); app.run(host='127.0.0.1', port={app_port}, debug=False, use_reloader=False)"
        process = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            wait_for_app(app_url, process)
            initial = local_json(f"{app_url}/api/providers")
            alpha = local_json(f"{app_url}/api/research", {"query": "解释迁移率", "useModel": True, "useOpenAlex": True})
            switched = local_json(f"{app_url}/api/providers", {"baseUrl": provider_url, "model": "mock/beta"})
            beta = local_json(f"{app_url}/api/research", {"query": "解释载流子迁移率", "useModel": True, "useOpenAlex": True})
            probe = local_json(f"{app_url}/api/providers/probe", {})
            failed_switch_status = None
            failed_switch: dict[str, Any] = {}
            try:
                local_json(f"{app_url}/api/providers", {"baseUrl": provider_url, "model": "mock/fail"})
            except urllib.error.HTTPError as exc:
                failed_switch_status = exc.code
                failed_switch = json.loads(exc.read().decode("utf-8"))
            after_failed_switch = local_json(f"{app_url}/api/providers")
            preserved = local_json(f"{app_url}/api/research", {"query": "解释柔性器件迁移率", "useModel": True, "useOpenAlex": True})
            checks = [
                {"name": "secret_not_exposed", "pass": SECRET not in json.dumps(initial, ensure_ascii=False), "detail": "provider status excludes API key"},
                {"name": "initial_model_used", "pass": "mock/alpha 已生效" in alpha["answer"] and not alpha["sources"], "detail": alpha["answer"]},
                {"name": "hot_switch_next_turn", "pass": switched["model"]["model"] == "mock/beta" and "mock/beta 已生效" in beta["answer"], "detail": beta["answer"]},
                {"name": "probe_reports_actual_model", "pass": probe.get("ok") and probe.get("actualModel") == "mock/beta", "detail": probe.get("actualModel", "")},
                {
                    "name": "failed_switch_preserves_previous_model",
                    "pass": failed_switch_status == 502
                    and failed_switch.get("applied") is False
                    and after_failed_switch["model"]["model"] == "mock/beta"
                    and "mock/beta 已生效" in preserved["answer"],
                    "detail": f"HTTP {failed_switch_status}; active={after_failed_switch['model']['model']}",
                },
            ]
            passed = sum(item["pass"] for item in checks)
            print(json.dumps({"benchmark": "flexresearch-provider-boundary-v1", "isolation": "temporary app vault + local mock provider", "summary": {"passed": passed, "total": len(checks), "passRate": round(passed / len(checks), 2)}, "checks": checks}, ensure_ascii=False, indent=2))
            return 0 if passed == len(checks) else 1
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            provider.shutdown()
            provider.server_close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError, RuntimeError, StopIteration) as exc:
        print(f"provider benchmark failed before completion: {type(exc).__name__}")
        raise SystemExit(1)

