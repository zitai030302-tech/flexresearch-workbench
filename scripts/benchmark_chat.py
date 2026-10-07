"""Repeatable live benchmark for the FlexResearch chat contract.

This calls the running HTTP app and public providers. It measures product-facing
behavior rather than mocked internals, and exits non-zero if a contract regresses.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable


BASE_URL = os.environ.get("FLEXRESEARCH_URL", "http://127.0.0.1:8765").rstrip("/")


def request_json(path: str, payload: dict[str, Any] | None = None, timeout: int = 60) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    # Never send the local target through a system proxy.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


@dataclass(frozen=True)
class Case:
    name: str
    query: str
    validate: Callable[[dict[str, Any]], tuple[bool, str]]


def no_sources_and_phrase(phrase: str) -> Callable[[dict[str, Any]], tuple[bool, str]]:
    def validate(result: dict[str, Any]) -> tuple[bool, str]:
        answer = result.get("answer", "")
        if result.get("sources"):
            return False, "unexpected literature sources"
        if phrase not in answer:
            return False, f"missing expected phrase: {phrase}"
        return True, "direct answer; no search"
    return validate


def concise_model_answer(result: dict[str, Any]) -> tuple[bool, str]:
    answer = result.get("answer", "")
    if result.get("sources"):
        return False, "knowledge question unexpectedly searched literature"
    if not answer or len(answer) > 240:
        return False, "answer is empty or too long"
    if "迁移率" not in answer:
        return False, "answer does not address mobility"
    return True, f"{len(answer)} characters; no search"


def current_literature(result: dict[str, Any]) -> tuple[bool, str]:
    sources = result.get("sources", [])
    cutoff = datetime.now(UTC).year - 3
    if len(sources) < 3:
        return False, f"only {len(sources)} literature candidates"
    providers = {item.get("source") for item in sources}
    if not providers <= {"OpenAlex", "Crossref"}:
        return False, f"unexpected literature provider: {sorted(providers)}"
    if any(not str(item.get("url", "")).startswith("http") for item in sources):
        return False, "candidate without a clickable source URL"
    titles = " ".join(str(item.get("title", "")).lower() for item in sources)
    if "flexible" not in titles and "electronic" not in titles:
        return False, "titles do not appear in-domain"
    recent = sum(int(item.get("year") or 0) >= cutoff for item in sources)
    if not recent:
        return False, "no candidate in the recent window"
    return True, f"{len(sources)} candidates via {' + '.join(sorted(providers))}; {recent} in recent window"


CASES = (
    Case("identity_route", "谁做的你？", no_sources_and_phrase("不是腾讯")),
    Case("model_route", "你用什么模型？", no_sources_and_phrase("当前配置")),
    Case("direct_lab_answer", "柔性光电探测器的暗电流为什么重要？", no_sources_and_phrase("无光基线和噪声")),
    Case("configured_model_answer", "柔性电子器件中，迁移率为什么重要？", concise_model_answer),
    Case("recent_literature", "找最近的柔性电子论文并总结", current_literature),
)


def main() -> int:
    started = time.perf_counter()
    provider = request_json("/api/providers").get("model", {})
    probe_start = time.perf_counter()
    probe = request_json("/api/providers/probe", {})
    probe_latency_ms = round((time.perf_counter() - probe_start) * 1000)
    results = []
    for case in CASES:
        case_start = time.perf_counter()
        try:
            response = request_json("/api/research", {"query": case.query, "useModel": True, "useOpenAlex": True})
            passed, detail = case.validate(response)
            results.append({"case": case.name, "pass": passed, "latencyMs": round((time.perf_counter() - case_start) * 1000), "detail": detail})
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError) as exc:
            results.append({"case": case.name, "pass": False, "latencyMs": round((time.perf_counter() - case_start) * 1000), "detail": f"request failed: {type(exc).__name__}"})
    passed = sum(item["pass"] for item in results)
    report = {
        "benchmark": "flexresearch-basic-chat-v1",
        "timestamp": datetime.now(UTC).isoformat(),
        "endpoint": BASE_URL,
        "configuredModel": provider.get("model") or "unconfigured",
        "modelProbe": {"pass": bool(probe.get("ok")), "actualModel": probe.get("actualModel"), "latencyMs": probe.get("latencyMs", probe_latency_ms)},
        "summary": {"passed": passed, "total": len(results), "passRate": round(passed / len(results), 2), "elapsedMs": round((time.perf_counter() - started) * 1000)},
        "cases": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed == len(results) and probe.get("ok") else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError) as exc:
        print(f"benchmark failed before completion: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1)

