"""Isolated end-to-end benchmark for the lab file and evidence workflow.

The script launches a temporary local FlexResearch service with a disposable
data directory. It verifies CSV archival + hash validation, text-bearing PDF
ingestion, and citation-addressable local evidence retrieval without touching
the user's lab vault.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def json_request(url: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def multipart_request(url: str, filename: str, content: bytes, mime_type: str) -> dict[str, Any]:
    boundary = f"----FlexResearchBenchmark{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def one_page_pdf(text: str) -> bytes:
    """Create a minimal text PDF without adding a report-generation dependency."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output, offsets = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), [0]
    for index, item in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode())
        output.extend(item)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    return bytes(output)


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(base_url: str, process: subprocess.Popen[bytes]) -> None:
    for _ in range(50):
        if process.poll() is not None:
            raise RuntimeError("isolated server exited before health check")
        try:
            if json_request(f"{base_url}/api/health", timeout=2).get("status") == "ok":
                return
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
            time.sleep(0.1)
    raise TimeoutError("isolated server did not become ready")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="flexresearch-lab-benchmark-") as temp_dir:
        port = available_port()
        base_url = f"http://127.0.0.1:{port}"
        env = {**os.environ, "FLEXRESEARCH_DATA_DIR": temp_dir}
        code = f"from app import app, init_db; init_db(); app.run(host='127.0.0.1', port={port}, debug=False, use_reloader=False)"
        process = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            wait_for_server(base_url, process)
            csv_bytes = b"voltage_v,current_a\n-1,-0.002\n-0.1,-0.0002\n0,0\n0.1,0.0003\n1,0.004\n"
            measurement = multipart_request(f"{base_url}/api/analyze", "iv-benchmark.csv", csv_bytes, "text/csv")
            measurement_id = measurement["measurement"]["id"]
            integrity = json_request(f"{base_url}/api/measurements/{measurement_id}/integrity")
            pdf_bytes = one_page_pdf("Bending record: dark current increased after 1000 cycles at 5 mm radius.")
            document = multipart_request(f"{base_url}/api/documents", "bending-record.pdf", pdf_bytes, "application/pdf")
            chat = json_request(f"{base_url}/api/research", {"query": "According to the local bending record, did dark current increase after 1000 cycles?", "useModel": False, "useOpenAlex": True})
            report_request = urllib.request.Request(f"{base_url}/api/sessions/{chat['sessionId']}/report.md")
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(report_request, timeout=20) as response:
                report = response.read().decode("utf-8")
            checks = [
                {"name": "csv_analysis", "pass": measurement.get("measurementType") == "I–V" and measurement.get("points") == 5, "detail": measurement.get("measurementType")},
                {"name": "csv_integrity", "pass": integrity.get("status") == "verified" and integrity.get("actualSha256") == hashlib.sha256(csv_bytes).hexdigest(), "detail": integrity.get("status")},
                {"name": "pdf_ingestion", "pass": document.get("item", {}).get("pages") == 1 and document.get("item", {}).get("chunks", 0) >= 1, "detail": f"pages={document.get('item', {}).get('pages')}, chunks={document.get('item', {}).get('chunks')}"},
                {"name": "local_evidence_retrieval", "pass": bool(chat.get("privateEvidence")) and not chat.get("sources"), "detail": chat.get("privateEvidence", [{}])[0].get("citation", "no citation")},
                {"name": "report_provenance", "pass": "local:" in report and "p. 1" in report, "detail": "local citation and page anchor"},
            ]
            passed = sum(item["pass"] for item in checks)
            print(json.dumps({"benchmark": "flexresearch-lab-workflow-v1", "isolation": "temporary FLEXRESEARCH_DATA_DIR removed after run", "summary": {"passed": passed, "total": len(checks), "passRate": round(passed / len(checks), 2)}, "checks": checks}, ensure_ascii=False, indent=2))
            return 0 if passed == len(checks) else 1
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError, RuntimeError) as exc:
        print(f"lab benchmark failed before completion: {type(exc).__name__}")
        raise SystemExit(1)

