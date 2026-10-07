#!/usr/bin/env python3
"""Opt-in live HTTP/model smoke test using ONLY a labelled synthetic experiment.

Creates a local test experiment and chat session. Uses the configured provider,
so run manually, never as part of offline CI. No private lab file is uploaded.
"""

import argparse
import hashlib
import json
import math
import time
import urllib.request
import urllib.parse
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--export-filtered", action="store_true", help="Also filter 0.5–3 Hz and verify a derived CSV download")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    if urllib.parse.urlparse(base).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("this smoke test is restricted to a local application")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def get(path):
        with opener.open(base + path, timeout=60) as response:
            return response.read()
    def post(path, value):
        request = urllib.request.Request(base + path, data=json.dumps(value).encode(), headers={"Content-Type": "application/json"})
        with opener.open(request, timeout=120) as response:
            return json.load(response)
    experiment = post("/api/experiments", {"name": "SYNTHETIC smoke: 1.2 Hz / 2.4 Hz — not human data", "metadata": {"synthetic": True, "purpose": "live-science-smoke"}})["item"]
    raw = ("time_s,ch4,ch14\n" + "\n".join(f"{i/100},{math.sin(2*math.pi*1.2*i/100)},{math.sin(2*math.pi*2.4*i/100)}" for i in range(1000))).encode()
    boundary = "smoke-" + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="experimentId"\r\n\r\n{experiment["id"]}\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="SYNTHETIC-pulse-smoke.csv"\r\nContent-Type: text/csv\r\n\r\n'.encode() + raw + f"\r\n--{boundary}--\r\n".encode())
    request = urllib.request.Request(base + "/api/analyze", data=body, headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    with opener.open(request, timeout=60) as response:
        upload = json.load(response)
    query = f'分析实验{experiment["id"]}通道4，采样率100Hz，找主要脉搏频率并画图。'
    if args.export_filtered:
        query = f'分析实验{experiment["id"]}通道4，采样率100Hz，用0.5–3 Hz带通滤波后找主要脉搏频率，导出CSV并画图。'
    started = time.monotonic()
    result = post("/api/research", {"query": query, "useModel": True, "useOpenAlex": False, "allowPrivateContext": False})
    elapsed = round(time.monotonic() - started, 3)
    run = json.loads(get(f'/api/agent-runs/{result["agentRun"]["runId"]}'))
    child = json.loads(get(f'/api/agent-runs/{result["analysisRun"]["runId"]}')) if result.get("analysisRun") else {}
    analysis = result.get("analysis", {})
    peak = analysis.get("calculated_result", {}).get("spectrum", {}).get("dominant_frequency_hz")
    plots = [artifact for artifact in analysis.get("artifacts", []) if artifact.get("metadata", {}).get("format") == "png"]
    png = get(plots[0]["url"]) if plots else b""
    report = get(result["reportUrl"]).decode() if result.get("reportUrl") else ""
    checks = {
        "completed": result.get("responseState") == "completed",
        "model_selected_result": run.get("state", {}).get("selectionValidated") is True,
        "two_or_more_model_turns": run.get("model", {}).get("calls", 0) >= 2,
        "peak_1_2_hz": peak is not None and abs(peak - 1.2) < .01,
        "png_generated": png.startswith(b"\x89PNG"),
        "report_contains_source_hash": hashlib.sha256(raw).hexdigest() in report,
        "private_results_not_shared": run.get("state", {}).get("resultPrivacy") == "local_only",
        "no_unrelated_papers": result.get("sources") == [],
    }
    if args.export_filtered:
        import csv
        import io
        derived = [artifact for artifact in analysis.get("artifacts", []) if artifact.get("metadata", {}).get("format") == "csv"]
        data = get(derived[0]["url"]) if len(derived) == 1 else b""
        metadata = derived[0]["metadata"] if len(derived) == 1 else {}
        rows = list(csv.DictReader(io.StringIO(data.decode()))) if data else []
        checks["derived_csv_1000_rows"] = len(rows) == 1000
        checks["derived_hash_verified"] = bool(data) and hashlib.sha256(data).hexdigest() == metadata.get("sha256")
        checks["export_source_lineage"] = metadata.get("parent_source_sha256") == hashlib.sha256(raw).hexdigest() and metadata.get("sha256", "missing") in report
        checks["export_filter_lineage"] = any(call["tool_name"] == "filter_signal" and call["tool_run_id"] == metadata.get("input_tool_run_id") for call in child.get("toolCalls", []))
    evidence = {"synthetic": True, "experimentId": experiment["id"], "sessionId": result["sessionId"], "measurementId": upload["measurement"]["id"], "query": query, "responseState": result.get("responseState"), "answer": result.get("answer"), "runId": result["agentRun"]["runId"], "analysisRunId": result.get("analysisRun", {}).get("runId"), "model": run.get("model"), "state": run.get("state"), "tokens": run.get("token_usage"), "costUsd": run.get("cost_usd"), "seconds": elapsed, "scientificTools": [call["tool_name"] for call in child.get("toolCalls", [])], "checks": checks, "passed": all(checks.values())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

