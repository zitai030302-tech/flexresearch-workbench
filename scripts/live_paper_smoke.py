#!/usr/bin/env python3
"""Opt-in live public-paper tool loop; never part of offline CI.

Creates one local chat, uses the configured model and public bibliographic
APIs, and verifies selection against this run's persisted tool observations.
This is a discovery/provenance check, not validation of scientific findings.
"""

import argparse
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--query", default="找关于 bioimpedance pulse waveform 的研究论文，给出真实来源。")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    if urllib.parse.urlparse(base).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("this smoke test is restricted to a local application")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
        with opener.open(req, timeout=180) as response:
            return json.load(response)

    request("/api/health")
    started = time.monotonic()
    result = request("/api/research", {"query": args.query, "useModel": True, "useOpenAlex": True, "allowPrivateContext": False})
    run = request(f'/api/agent-runs/{result["agentRun"]["runId"]}')
    calls = [call for call in run["toolCalls"] if call["tool_name"] == "search_papers"]
    observed = {ref["url"] for call in calls if call["status"] == "complete" for ref in call["source_refs"]}
    sources = result.get("sources", [])
    checks = {
        "completed": result.get("responseState") == "completed",
        "model_selected_sources": run["state"].get("selectionValidated") is True,
        "two_or_more_model_turns": run["model"].get("calls", 0) >= 2,
        "search_called": bool(calls),
        "nonempty_sources": bool(sources),
        "sources_observed_in_this_run": bool(sources) and all(source["url"] in observed for source in sources),
        "metadata_only": result.get("evidenceLevel") == "bibliographic_metadata_only",
        "no_private_evidence": result.get("privateEvidence") == [],
    }
    evidence = {"query": args.query, "sessionId": result["sessionId"], "runId": run["run_uuid"], "responseState": result.get("responseState"), "model": run["model"], "state": run["state"], "costUsd": run["cost_usd"], "seconds": round(time.monotonic() - started, 3), "answer": result["answer"], "sources": sources, "searchCalls": [{key: call[key] for key in ("tool_run_id", "arguments", "status", "latency_ms", "source_refs")} for call in calls], "checks": checks, "passed": all(checks.values())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

