"""Transport policy tests use virtual waiting, never live external providers."""

from datetime import UTC, datetime
from email.message import Message
import json
import urllib.error

import pytest

from flexresearch import provider_transport as transport


@pytest.mark.parametrize("header,expected", [
    (None, None), ("1", 1), ("0", 0), (" 2 ", 2), ("1.5", None),
    ("-1", None), ("garbage", None), ("999999999999999999999", float("inf")),
    ("Sat, 12 Sep 2026 00:00:01 GMT", 1), ("Fri, 11 Sep 2026 23:59:59 GMT", 0),
])
def test_retry_after_dates_and_seconds(header, expected):
    headers = Message()
    if header is not None:
        headers["retry-after"] = header
    assert transport.retry_after_seconds(headers, current=datetime(2026, 9, 12, tzinfo=UTC)) == expected


@pytest.mark.parametrize("budget", [0, 4, True, 1.5, "2"])
def test_invalid_retry_budget_never_sends_request(budget):
    with pytest.raises(ValueError, match="attempts"):
        transport.request_with_retries(lambda *args, **kwargs: pytest.fail("must not send"), "https://invalid", {}, {}, attempts=budget)


@pytest.mark.parametrize("status,header,expected_calls,waits", [
    (429, "1", 2, [1]), (429, "60", 1, []), (401, "1", 1, []),
    (503, "bad", 2, [.2]), (400, None, 1, []), (504, None, 2, [.2]),
])
def test_retry_budget_is_bounded_and_does_not_retry_before_retry_after(monkeypatch, status, header, expected_calls, waits):
    calls, delays = [], []
    monkeypatch.setattr(transport.time, "sleep", delays.append)
    def fail(*args, **kwargs):
        calls.append(1)
        raise urllib.error.HTTPError("https://invalid?private", status, "secret provider body", {"Retry-After": header} if header else {}, None)
    with pytest.raises(urllib.error.HTTPError):
        transport.request_with_retries(fail, "https://invalid", {"Authorization": "secret"}, {})
    assert len(calls) == expected_calls and delays == waits
    events = transport.TRANSPORT_EVENTS.get()
    assert len(events) == expected_calls
    assert events[-1]["retryScheduled"] is False
    assert "secret" not in json.dumps(events) and "private" not in json.dumps(events)


@pytest.mark.parametrize("error,code", [
    (TimeoutError("slow"), "MODEL_TIMEOUT"),
    (urllib.error.URLError(TimeoutError("slow")), "MODEL_TIMEOUT"),
    (urllib.error.URLError("timed out"), "MODEL_TIMEOUT"),
    (urllib.error.URLError(ConnectionRefusedError()), "MODEL_NETWORK_ERROR"),
    (ValueError("invalid"), "MODEL_INVALID_RESPONSE"),
])
def test_error_codes(error, code):
    assert transport.failure_code(error) == code


def test_error_envelope_then_success_records_transport_not_fake_result(monkeypatch):
    monkeypatch.setattr(transport.time, "sleep", lambda seconds: None)
    replies = iter([{"error": {"code": 429, "message": "secret"}}, {"choices": []}])
    result, attempts = transport.request_with_retries(lambda *args, **kwargs: next(replies), "https://invalid", {}, {})
    assert result == {"choices": []} and attempts == 2
    assert [item["status"] for item in transport.TRANSPORT_EVENTS.get()] == ["error", "complete"]


def test_nonobject_response_is_not_retried():
    with pytest.raises(ValueError):
        transport.request_with_retries(lambda *args, **kwargs: [], "https://invalid", {}, {})
    assert len(transport.TRANSPORT_EVENTS.get()) == 1
    assert transport.TRANSPORT_EVENTS.get()[0]["errorCode"] == "MODEL_INVALID_RESPONSE"

