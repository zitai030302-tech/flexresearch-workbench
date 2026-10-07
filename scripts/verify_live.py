"""Live acceptance checks against a running FlexResearch instance.

This intentionally exercises the HTTP application and configured public
providers. It is complementary to unit tests, not a replacement for them.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


BASE_URL = os.environ.get("FLEXRESEARCH_URL", "http://127.0.0.1:8765").rstrip("/")


def request_json(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers={"Content-Type": "application/json"}, method="POST" if data else "GET")
    # The local acceptance target must never be sent through a corporate/user
    # HTTP proxy; doing so commonly turns localhost into a 502.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    health = request_json("/api/health")
    require(health.get("status") == "ok", "health check failed")

    product = request_json("/api/research", {"query": "谁做的你？", "useModel": True, "useOpenAlex": True})
    require(not product["sources"], "product question unexpectedly returned literature")
    require("不是腾讯" in product["answer"], "product identity answer is not constrained")

    knowledge = request_json("/api/research", {"query": "柔性光电探测器的暗电流为什么重要？", "useModel": True, "useOpenAlex": True})
    require(not knowledge["sources"], "knowledge question unexpectedly returned literature")
    require("无光基线和噪声" in knowledge["answer"], "condition-aware direct answer missing")

    literature = request_json("/api/research", {"query": "找最近的柔性电子论文并总结", "useModel": True, "useOpenAlex": True})
    require(literature["sources"], "literature task returned no source")
    require(all(item["source"] in {"OpenAlex", "Crossref"} for item in literature["sources"]), "literature task used an unexpected source")
    require(any("flexible" in item["title"].lower() or "electronic" in item["title"].lower() for item in literature["sources"]), "literature titles are not in-domain")

    # A probe is intentionally diagnostic: free/demo providers can be transient
    # even when the deterministic routing and literature paths are healthy.
    try:
        probe = request_json("/api/providers/probe", {})
        status = "ok" if probe.get("ok") else f"warning: {probe.get('detail')}"
    except (urllib.error.URLError, urllib.error.HTTPError):
        status = "warning: provider probe request failed"
    print(json.dumps({"health": "ok", "product": "ok", "knowledge": "ok", "literature": {"providers": sorted({item["source"] for item in literature["sources"]}), "count": len(literature["sources"])}, "modelProbe": status}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as exc:
        print(f"live acceptance failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

