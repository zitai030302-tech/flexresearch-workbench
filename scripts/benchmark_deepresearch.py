"""Run FlexResearch against public DeepResearch Bench task prompts.

This is a retrieval-grounding adapter, not an official RACE/FACT score. The
official DeepResearch Bench evaluator currently requires separate judge and
web-scraping credentials. The adapter instead executes real public benchmark
prompts against the running product and verifies observable source contracts.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any


BASE_URL = os.environ.get("FLEXRESEARCH_URL", "http://127.0.0.1:8765").rstrip("/")
DRB_QUERY_URL = "https://raw.githubusercontent.com/Ayanami0730/deep_research_bench/main/data/prompt_data/query.jsonl"
DEFAULT_TASK_IDS = (13, 33, 63)  # electronics readout, thin-film process, LN photonics


def request_json(url: str, payload: dict[str, Any] | None = None, timeout: int = 90) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if url.startswith("http://127.0.0.1") else urllib.request.build_opener()
    with opener.open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def load_tasks(task_ids: tuple[int, ...]) -> list[dict[str, Any]]:
    request = urllib.request.Request(DRB_QUERY_URL, headers={"User-Agent": "FlexResearch benchmark adapter"})
    with urllib.request.urlopen(request, timeout=30) as response:
        available = {row["id"]: row for row in (json.loads(line) for line in response.read().decode("utf-8").splitlines() if line.strip())}
    missing = [task_id for task_id in task_ids if task_id not in available]
    if missing:
        raise ValueError(f"DeepResearch Bench task IDs unavailable: {missing}")
    return [available[task_id] for task_id in task_ids]


def benchmark_prompt(task: dict[str, Any]) -> str:
    suffix = "请检索相关论文，并只基于可点击、可核验的来源做标题级整理；没有全文时不要扩写成论文结论。"
    if task.get("language") == "en":
        suffix = "Search relevant papers and provide only title-level notes with clickable, verifiable sources; do not turn metadata into full-text conclusions."
    return f"{task['prompt']}\n\n{suffix}"


def validate(result: dict[str, Any]) -> tuple[bool, str]:
    sources = result.get("sources", [])
    if len(sources) < 3:
        return False, f"only {len(sources)} candidates"
    if any(not str(source.get("url", "")).startswith("http") for source in sources):
        return False, "candidate without clickable URL"
    if any(not source.get("relevance", {}).get("matchedTerms") for source in sources):
        return False, "candidate without a visible query-term match"
    answer = str(result.get("answer", ""))
    if "标题" not in answer or "全文结论" not in answer:
        return False, "answer did not preserve title-level evidence boundary"
    return True, f"{len(sources)} candidates; {result.get('sources', [{}])[0].get('source', 'unknown')} primary source"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the DeepResearch Bench retrieval-grounding adapter.")
    parser.add_argument("--ids", default=",".join(str(value) for value in DEFAULT_TASK_IDS), help="Comma-separated DeepResearch Bench task IDs (default: 13,33,63).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task_ids = tuple(int(value.strip()) for value in args.ids.split(",") if value.strip())
    tasks = load_tasks(task_ids)
    cases = []
    for task in tasks:
        started = time.perf_counter()
        try:
            response = request_json(f"{BASE_URL}/api/research", {"query": benchmark_prompt(task), "useModel": True, "useOpenAlex": True})
            passed, detail = validate(response)
            cases.append({"taskId": task["id"], "topic": task["topic"], "language": task["language"], "pass": passed, "latencyMs": round((time.perf_counter() - started) * 1000), "sourceCount": len(response.get("sources", [])), "detail": detail})
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError) as exc:
            cases.append({"taskId": task["id"], "topic": task["topic"], "language": task["language"], "pass": False, "latencyMs": round((time.perf_counter() - started) * 1000), "sourceCount": 0, "detail": f"request failed: {type(exc).__name__}"})
    passed = sum(case["pass"] for case in cases)
    report = {
        "benchmark": "deepresearch-bench-retrieval-adapter-v1",
        "upstream": "Ayanami0730/deep_research_bench",
        "timestamp": datetime.now(UTC).isoformat(),
        "scope": "Public task prompts + live retrieval and source-grounding checks; not an official RACE/FACT score.",
        "officialScore": None,
        "summary": {"passed": passed, "total": len(cases), "passRate": round(passed / len(cases), 2)},
        "cases": cases,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError) as exc:
        print(f"DeepResearch Bench adapter failed before completion: {type(exc).__name__}")
        raise SystemExit(1)

