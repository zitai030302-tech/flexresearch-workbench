"""Bounded model transport retries and secret-free attempt observations.

Retry-After follows RFC 9110 §10.2.3. If its delay exceeds the small interactive
retry budget, stop rather than retrying before the provider permits it.
"""

from __future__ import annotations

import time
import urllib.error
from contextvars import ContextVar
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Callable


TRANSPORT_EVENTS: ContextVar[list[dict[str, Any]]] = ContextVar("provider_attempts", default=[])
TRANSIENT_HTTP = frozenset({408, 425, 429, 500, 502, 503, 504})
MAX_RETRY_DELAY_SECONDS = 2.0


def failure_code(error: BaseException) -> str:
    if isinstance(error, urllib.error.HTTPError):
        if error.code == 429:
            return "MODEL_RATE_LIMITED"
        if error.code in {408, 504}:
            return "MODEL_TIMEOUT"
        return "MODEL_AUTH_FAILED" if error.code in {401, 403} else "MODEL_HTTP_ERROR"
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
        return "MODEL_TIMEOUT"
    if isinstance(error, (ValueError, TypeError, IndexError, KeyError)):
        return "MODEL_INVALID_RESPONSE"
    return "MODEL_NETWORK_ERROR"


def retry_after_seconds(headers: Any, *, current: datetime | None = None) -> float | None:
    value = headers.get("Retry-After") if headers else None
    if value is None:
        return None
    text = str(value).strip()
    if text.isascii() and text.isdigit():
        return float(text) if len(text) < 12 else float("inf")
    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return max(0.0, (parsed - (current or datetime.now(UTC))).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def request_with_retries(
    request: Callable[..., dict[str, Any]], url: str, headers: dict[str, str],
    payload: dict[str, Any], *, attempts: int = 2,
) -> tuple[dict[str, Any], int]:
    TRANSPORT_EVENTS.set([])
    if isinstance(attempts, bool) or not isinstance(attempts, int) or not 1 <= attempts <= 3:
        raise ValueError("attempts must be an integer between 1 and 3")
    events: list[dict[str, Any]] = []
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        try:
            response = request(url, headers=headers, method="POST", payload=payload)
            if not isinstance(response, dict):
                raise ValueError("provider response must be an object")
            if response.get("error"):
                error = response["error"]
                raw_code = error.get("code") if isinstance(error, dict) else None
                code = int(raw_code) if str(raw_code).isdigit() else 502
                if not 400 <= code <= 599:
                    code = 502
                raise urllib.error.HTTPError(url, code, "Provider error envelope", {}, None)
            events.append({"attempt": attempt, "status": "complete", "latencyMs": round((time.monotonic() - started) * 1000), "retryScheduled": False, "retryDelayMs": 0})
            TRANSPORT_EVENTS.set([dict(item) for item in events])
            return response, attempt
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            transient = not isinstance(exc, ValueError)
            delay = 0.2 * attempt
            if isinstance(exc, urllib.error.HTTPError):
                transient = exc.code in TRANSIENT_HTTP
                retry_after = retry_after_seconds(exc.headers)
                if retry_after is not None:
                    delay = max(delay, retry_after)
            retry = transient and attempt < attempts and delay <= MAX_RETRY_DELAY_SECONDS
            event = {"attempt": attempt, "status": "error", "errorCode": failure_code(exc), "latencyMs": round((time.monotonic() - started) * 1000), "retryScheduled": retry, "retryDelayMs": round(delay * 1000) if retry else 0}
            if isinstance(exc, urllib.error.HTTPError):
                event["httpStatus"] = exc.code
                if transient and delay > MAX_RETRY_DELAY_SECONDS:
                    event["stopReason"] = "retry_after_exceeds_budget"
            events.append(event)
            TRANSPORT_EVENTS.set([dict(item) for item in events])
            if not retry:
                raise
            # A retry can be billed upstream; never assume failure means zero cost.
            time.sleep(delay)
    raise AssertionError("unreachable retry state")

