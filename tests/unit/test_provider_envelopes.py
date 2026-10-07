"""HTTP-200 provider failures must use the same retry/error semantics as HTTP errors."""

import urllib.error

import pytest

import app as application


def test_embedded_transient_error_is_retried(monkeypatch):
    responses = iter([{"error": {"code": 429, "message": "private upstream detail"}}, {"choices": [{"message": {"content": "OK"}}]}])
    monkeypatch.setattr(application, "request_json", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(application.time, "sleep", lambda *_args: None)
    result, attempts = application.request_model_json("https://example.invalid/v1/chat/completions", {}, {})
    assert attempts == 2
    assert result["choices"][0]["message"]["content"] == "OK"


def test_embedded_permanent_error_is_sanitized_and_not_retried(monkeypatch):
    calls = []
    monkeypatch.setattr(application, "request_json", lambda *_args, **_kwargs: calls.append(1) or {"error": {"code": 401, "message": "secret-value"}})
    with pytest.raises(urllib.error.HTTPError) as failure:
        application.request_model_json("https://example.invalid/v1/chat/completions", {}, {})
    assert failure.value.code == 401
    assert "secret-value" not in str(failure.value)
    assert calls == [1]

