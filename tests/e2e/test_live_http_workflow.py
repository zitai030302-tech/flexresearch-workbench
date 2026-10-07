"""Real local process/HTTP tests; no browser and no external model/network.

Every test owns a temporary vault and server. These complement (not rename)
the Flask test-client cases and verify persistence across an actual restart.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

import pytest
from pypdf import PdfReader, PdfWriter

from scripts.benchmark_lab import ROOT, available_port, one_page_pdf, wait_for_server
from scripts.run_agent_eval import pulse_csv


class LocalServer:
    def __init__(self, vault):
        self.vault = vault
        self.port = available_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.process = None

    def start(self):
        # Block the application's outbound adapter even if the developer has
        # credentials in .env. Accidental routing to a remote tool must fail.
        code = (
            "import app as m; "
            "m.request_json=lambda *a, **k: (_ for _ in ()).throw(RuntimeError('external access forbidden in HTTP E2E')); "
            f"m.app.run(host='127.0.0.1', port={self.port}, debug=False, use_reloader=False)"
        )
        self.process = subprocess.Popen(
            [sys.executable, "-c", code], cwd=ROOT,
            env={**os.environ, "FLEXRESEARCH_DATA_DIR": str(self.vault)},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        wait_for_server(self.url, self.process)

    def stop(self):
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self.process = None

    def request(self, path, *, data=None, headers=None):
        request = urllib.request.Request(self.url + path, data=data, headers=headers or {})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            response = opener.open(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            payload = json.loads(raw) if response.headers.get_content_type() == "application/json" else raw
            return response.status, payload

    def upload(self, path, filename, raw, fields=None):
        boundary = "test-" + uuid.uuid4().hex
        parts = []
        for name, value in (fields or {}).items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        parts += [f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode(), raw, f'\r\n--{boundary}--\r\n'.encode()]
        return self.request(path, data=b"".join(parts), headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})


@pytest.fixture
def live_server(tmp_path):
    server = LocalServer(tmp_path / "http-vault")
    try:
        server.start()
        yield server
    finally:
        server.stop()


def test_real_http_csv_filter_fft_plot_report_survive_process_restart(live_server):
    raw = pulse_csv(column="signal")
    status, payload = live_server.upload("/api/analyze", "synthetic-pulse.csv", raw, {"question": "做 0.5-3 Hz 带通滤波，找 FFT 主峰并画图", "sampleRate": "100"})
    assert status == 200
    agent = payload["agent"]
    assert agent["status"] == "complete"
    assert [step["tool_name"] for step in agent["trajectory"]] == ["load_csv", "filter_signal", "spectral_analysis", "plot_signal"]
    assert agent["calculated_result"]["spectrum"]["dominant_frequency_hz"] == pytest.approx(1.2, abs=.05)
    digest = hashlib.sha256(raw).hexdigest()
    assert all(ref["source_sha256"] == digest for ref in agent["source_refs"])
    run_path = f"/api/agent-runs/{payload['agentRun']['runId']}"
    status, run = live_server.request(run_path)
    assert status == 200 and len(run["toolCalls"]) == 4
    status, png = live_server.request(agent["artifacts"][0]["url"])
    assert status == 200 and png.startswith(b"\x89PNG\r\n\x1a\n")
    status, report = live_server.request(run_path + "/report.md")
    assert status == 200
    assert all(title.encode() in report for title in ("Data Quality", "Measured Result", "Calculated Result", "Agent Interpretation", "Source & Provenance"))
    assert digest.encode() in report
    assert any(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path in live_server.vault.rglob("*.csv"))

    live_server.stop()
    live_server.start()
    assert live_server.request(run_path) == (200, run)
    assert live_server.request(agent["artifacts"][0]["url"]) == (200, png)
    assert live_server.request(run_path + "/report.md") == (200, report)
    status, session = live_server.request(f"/api/sessions/{payload['sessionId']}")
    assert status == 200 and len(session["messages"]) >= 2


def test_real_http_pdf_pages_index_citation_and_duplicate(live_server):
    writer = PdfWriter()
    for text in ("Methods: record electrode ID and sample identifier.", "Calibration: bioimpedance reference resistor is 1250 ohm. Repeat calibration before recording."):
        writer.add_page(PdfReader(io.BytesIO(one_page_pdf(text))).pages[0])
    output = io.BytesIO()
    writer.write(output)
    raw = output.getvalue()
    status, payload = live_server.upload("/api/documents", "synthetic-calibration.pdf", raw)
    assert status == 201 and payload["item"]["pages"] == 2
    status, search = live_server.request("/api/private-search?q=calibration%20bioimpedance")
    assert status == 200 and search["items"]
    assert any(item["id"] == payload["item"]["id"] for item in search["items"])
    status, answer = live_server.request("/api/research", data=json.dumps({"query": "According to the local calibration SOP, what bioimpedance reference resistor is used?", "useModel": False}).encode(), headers={"Content-Type": "application/json"})
    assert status == 200 and not answer["sources"]
    hits = [item for item in answer["privateEvidence"] if item["documentId"] == payload["item"]["id"]]
    assert hits and any("1250" in item["excerpt"] and "p. 2" in item["locator"] for item in hits)
    assert all(item["citation"].startswith("local:") for item in hits)
    status, duplicate = live_server.upload("/api/documents", "renamed.pdf", raw)
    assert status == 200 and duplicate["duplicate"] is True
    assert duplicate["item"]["id"] == payload["item"]["id"]
    assert len(live_server.request("/api/documents")[1]["items"]) == 1


@pytest.mark.parametrize("kind,error_code,status_code", [
    ("oversized", "FILE_TOO_LARGE", 413),
    ("corrupt", "DOCUMENT_PARSE_FAILED", 400),
    ("no_text", "OCR_REQUIRED", 400),
])
def test_real_http_failed_upload_is_structured_and_not_archived(live_server, kind, error_code, status_code):
    raw = b"x" * (8 * 1024 * 1024 + 1) if kind == "oversized" else b"%PDF-invalid" if kind == "corrupt" else one_page_pdf("")
    status, payload = live_server.upload("/api/documents", "rejected.pdf", raw)
    assert status == status_code
    assert payload["errorCode"] == error_code
    assert payload["responseState"] == ("failed" if kind == "oversized" else "needs_clarification")
    assert "agent" not in payload and "result" not in payload
    assert live_server.request("/api/documents")[1]["items"] == []
    assert not list(live_server.vault.rglob("*.pdf"))

