"""API→actual adapter→injected transport→history/DB, plus real localhost I/O."""

import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import app as application
from flexresearch import provider_transport as transport


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(application, "model_configuration", lambda: {"configured": True, "apiKey": "test-secret-only", "baseUrl": "https://provider.invalid/v1", "model": "fixture/model"})
    monkeypatch.setattr(transport.time, "sleep", lambda seconds: None)
    def forbidden(*args, **kwargs):
        pytest.fail("knowledge question must not retrieve external papers")
    for name in ("openalex_search", "crossref_search", "europepmc_search"):
        monkeypatch.setattr(application, name, forbidden)


def ask(client, **extra):
    return client.post("/api/research", json={"query": "解释柔性电极接触阻抗。", "useModel": True, "useOpenAlex": True, **extra})


@pytest.mark.parametrize("kind,expected,attempts", [
    ("timeout", "MODEL_TIMEOUT", 2), ("wrapped_timeout", "MODEL_TIMEOUT", 2),
    ("rate_limit", "MODEL_RATE_LIMITED", 2), ("auth", "MODEL_AUTH_FAILED", 1),
    ("malformed", "MODEL_INVALID_RESPONSE", 1),
])
def test_knowledge_failure_is_not_canned_success_and_persists(configured, monkeypatch, kind, expected, attempts):
    calls = []
    def fail(*args, **kwargs):
        calls.append(kwargs["payload"])
        if kind == "timeout":
            raise TimeoutError("test-secret-only")
        if kind == "wrapped_timeout":
            raise urllib.error.URLError(TimeoutError("test-secret-only"))
        if kind == "malformed":
            return {"choices": []}
        raise urllib.error.HTTPError("https://provider.invalid", 429 if kind == "rate_limit" else 401, "test-secret-only", {"Retry-After": "1"}, None)
    monkeypatch.setattr(application, "request_json", fail)
    client = application.app.test_client()
    response = ask(client)
    assert response.status_code == 200
    result = response.json
    assert result["responseState"] == "partial" and result["errorCode"] == expected
    assert result["answerOrigin"] == "unavailable" and result["sources"] == []
    assert "模型当前不可用" in result["answer"]
    assert "通道间不匹配" not in result["answer"]  # old canned answer must not mask failure
    assert len(calls) == attempts == result["modelObservation"]["attempts"]
    assert result["modelObservation"]["retryCount"] == attempts - 1
    history = client.get(f"/api/sessions/{result['sessionId']}").json["messages"][-1]["result"]
    assert history["errorCode"] == expected and history["responseState"] == "partial"
    assert history["answerOrigin"] == "unavailable"
    assert application.load_conversation_context(result["sessionId"]).messages == []
    with application.get_db() as db:
        run = db.execute("SELECT * FROM agent_runs WHERE id=?", (result["agentRun"]["id"],)).fetchone()
    assert run["error"] == expected and run["status"] == "partial"
    assert json.loads(run["model_json"])["attempts"] == attempts
    assert json.loads(run["state_json"])["stop_reason"] == expected
    assert run["cost_usd"] is None
    logs = (application.LOG_DIR / "agent-runs.jsonl").read_text()
    assert expected in logs and "test-secret-only" not in logs + response.get_data(as_text=True)


def test_enabled_model_gets_actual_question_and_followup_not_offline_snippet(configured, monkeypatch):
    replies = iter(["接触阻抗是电极与皮肤界面的复阻抗，随频率、材料和贴合状态变化。", "可以在相同电极面积、贴合压力和仪器设置下比较频率响应，并记录重复测量差异。"])
    requests = []
    def respond(*args, **kwargs):
        requests.append(kwargs["payload"])
        return {"model": "fixture/model", "choices": [{"message": {"content": next(replies)}}]}
    monkeypatch.setattr(application, "request_json", respond)
    client = application.app.test_client()
    first = ask(client).json
    second = ask(client, query="怎么比较它？", sessionId=first["sessionId"]).json
    assert first["answer"] != second["answer"]
    assert first["answerOrigin"] == second["answerOrigin"] == "model"
    assert first["responseState"] == second["responseState"] == "completed"
    assert "解释柔性电极接触阻抗。" in requests[0]["messages"][-1]["content"]
    assert any(item["role"] == "assistant" and item["content"] == first["answer"] for item in requests[1]["messages"])
    assert "怎么比较它？" in requests[1]["messages"][-1]["content"]


def test_repair_failure_retains_both_request_attempts(configured, monkeypatch):
    calls = []
    def respond(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return {"choices": [{"message": {"content": "太长了。" * 60}}]}
        raise urllib.error.HTTPError("https://provider.invalid", 429, "test-secret-only", {}, None)
    monkeypatch.setattr(application, "request_json", respond)
    result = ask(application.app.test_client()).json
    assert result["errorCode"] == "MODEL_RATE_LIMITED"
    observation = result["modelObservation"]
    assert observation["attempts"] == 3 and observation["retryCount"] == 1
    assert [event["requestIndex"] for event in observation["transportEvents"]] == [1, 2, 2]
    assert "太长了" not in result["answer"]


@pytest.mark.parametrize("status,attempts", [(401, 1), (429, 2)])
def test_tool_model_failure_records_attempts_and_unknown_usage(configured, monkeypatch, status, attempts):
    def failed(url, **kwargs):
        raise urllib.error.HTTPError(url, status, "test-secret-only", {}, None)
    monkeypatch.setattr(application, "request_json", failed)
    observations = []
    with pytest.raises(urllib.error.HTTPError):
        application.tool_model_client(application.model_configuration(), observations, [{"role": "user", "content": "test"}], [])
    assert len(observations) == 1 and observations[0]["attempts"] == attempts
    assert observations[0]["status"] == "error" and observations[0]["usage"] == {}
    assert len(observations[0]["transportEvents"]) == attempts
    assert "test-secret-only" not in json.dumps(observations)


@pytest.mark.parametrize("mode,code", [("timeout", "MODEL_TIMEOUT"), ("429", "MODEL_RATE_LIMITED")])
def test_real_localhost_transport_failure_is_caught_without_external_calls(monkeypatch, mode, code):
    release = threading.Event()
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            seen.append(self.path)
            if mode == "timeout":
                release.wait(1)
                return
            self.send_response(429)
            self.send_header("Content-Length", "0")
            self.send_header("Retry-After", "0")
            self.end_headers()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01})
    thread.start()
    monkeypatch.setattr(application, "HTTP_TIMEOUT_SECONDS", .03)
    monkeypatch.setattr(application, "model_configuration", lambda: {"configured": True, "apiKey": "localhost-test", "baseUrl": f"http://127.0.0.1:{server.server_port}/v1", "model": "fixture/local"})
    try:
        result = ask(application.app.test_client()).json
        assert result["responseState"] == "partial" and result["errorCode"] == code
        assert result["modelObservation"]["attempts"] == 2
        assert len(seen) == 2
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

