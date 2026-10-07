"""Run the original continuation against different channel truths and persisted state."""

import hashlib
import io
import json
from dataclasses import replace

import numpy as np
import pytest

import app as application


QUESTION = "继续用刚才的 100 Hz 采样率分析通道 4。"


def upload(client, question="通道2，采样率100Hz，分析FFT主峰", **extra):
    axis = np.arange(1000) / 100
    raw = ("ch2,ch4,ch14\n" + "\n".join(f"{a:.17g},{b:.17g},{c:.17g}" for a,b,c in zip(
        2+np.sin(2*np.pi*2.4*axis), 4+np.sin(2*np.pi*1.2*axis), 14+np.sin(2*np.pi*3.6*axis))) + "\n").encode()
    response = client.post("/api/analyze", data={"file": (io.BytesIO(raw), "SYNTHETIC-channels.csv"),
        "bindContext": "true", "question": question, **extra}, content_type="multipart/form-data")
    assert response.status_code == 200, response.text
    return raw, response.get_json()


def ask(client, query, session):
    response = client.post("/api/research", json={"query": query, "sessionId": session, "useModel": False})
    assert response.status_code == 200
    return response.get_json()


def test_original_channel_switch_executes_new_signal_and_persists_goal_source():
    client = application.app.test_client()
    raw, first = upload(client)
    assert first["metrics"] == first["measurement"]["metrics"] == []
    assert first["agent"]["calculated_result"]["spectrum"]["dominant_frequency_hz"] == pytest.approx(2.4)
    second = ask(client, QUESTION, first["sessionId"])
    assert second["responseState"] == "completed" and second["intent"] == "signal_analysis"
    state, result = second["experimentContext"], second["analysis"]
    assert state["channel"] == "4" and state["sample_rate"] == 100
    goal = {"tasks": ["spectrum"], "source_run_id": first["agentRun"]["runId"]}
    assert state["analysis_context"] == result["state"]["analysis_context"] == goal
    assert [s["tool_name"] for s in result["trajectory"]] == ["load_experiment_data", "load_csv", "spectral_analysis"]
    assert result["calculated_result"]["spectrum"]["dominant_frequency_hz"] == pytest.approx(1.2)
    ref = result["source_refs"][-1]
    assert ref["channel"] == "ch4" and ref["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert ref["parameters"]["sample_rate"] == 100 and ref["parameters"]["analysis_context"] == goal
    application.init_db()  # Reopen database initialization; no in-memory state required.
    assert application.load_experiment_session_state(first["sessionId"]).model_dump(mode="json") == state
    with application.get_db() as db:
        row = db.execute("SELECT parameters_json FROM analysis_runs WHERE analysis_type='spectrum' ORDER BY id DESC").fetchone()
        assert json.loads(db.execute("SELECT metrics_json FROM measurements").fetchone()[0]) == []
    assert json.loads(row[0])["analysis_context"] == goal
    history = client.get(f"/api/sessions/{first['sessionId']}").get_json()["messages"]
    assert history[-2]["content"] == QUESTION and history[-1]["result"]["analysis"] == result
    assert first["agentRun"]["runId"] in client.get(second["reportUrl"]).text
    assert any(path.read_bytes() == raw for path in application.MEASUREMENT_DIR.glob("*.csv"))
    third = ask(client, "继续分析通道2", first["sessionId"])
    assert third["analysis"]["calculated_result"]["spectrum"]["dominant_frequency_hz"] == pytest.approx(2.4)
    assert third["experimentContext"]["analysis_context"]["source_run_id"] == second["analysisRun"]["runId"]


@pytest.mark.parametrize("prior,expected_key,absent", [
    ("通道2，采样率100Hz，计算均值", "statistics", "spectrum"),
    ("通道2，采样率100Hz，检查信号质量", "signal_quality", "spectrum"),
])
def test_continuation_uses_actual_previous_goal_not_always_fft(prior, expected_key, absent):
    client = application.app.test_client()
    _, first = upload(client, prior)
    result = ask(client, QUESTION, first["sessionId"])
    assert result["responseState"] == "completed"
    values = result["analysis"]["calculated_result"]
    assert expected_key in values and absent not in values
    if expected_key == "statistics":
        assert values[expected_key]["mean"] == pytest.approx(4)


def test_missing_goal_is_structured_clarification_not_sampling_rate_guess():
    client = application.app.test_client()
    _, first = upload(client, "读取通道2，采样率100Hz")
    result = ask(client, QUESTION, first["sessionId"])
    assert result["responseState"] == "needs_clarification" and "analysis" not in result
    assert result["clarificationFields"] == ["analysis_goal"]
    assert result["tools"] == [] and "不会仅凭采样率猜测" in result["answer"]
    explicit = ask(client, "继续分析通道4的主峰", first["sessionId"])
    assert explicit["responseState"] == "completed"


def test_fresh_session_does_not_borrow_another_sessions_goal():
    client = application.app.test_client()
    _, first = upload(client)
    result = ask(client, f"实验{first['experimentContext']['experiment_id']}继续分析通道4，采样率100Hz", None)
    assert result["responseState"] == "needs_clarification" and "analysis" not in result


def test_new_upload_clears_old_analysis_goal():
    client = application.app.test_client()
    _, first = upload(client)
    _, second = upload(client, "读取数据，采样率100Hz", sessionId=str(first["sessionId"]))
    assert second["experimentContext"]["analysis_context"]["tasks"] == []
    reply = ask(client, QUESTION, first["sessionId"])
    assert reply["responseState"] == "needs_clarification" and "analysis" not in reply


def test_failed_spectrum_cannot_become_successful_goal_memory(monkeypatch):
    original = application.build_lab_tool_registry
    def broken_registry():
        registry = original()
        def fail(_payload):
            raise TimeoutError("synthetic spectral failure")
        registry._tools["spectral_analysis"] = replace(registry._tools["spectral_analysis"], handler=fail)
        return registry
    monkeypatch.setattr(application, "build_lab_tool_registry", broken_registry)
    client = application.app.test_client()
    _, first = upload(client)
    assert first["responseState"] == "needs_clarification"
    assert first["experimentContext"]["analysis_context"]["tasks"] == []
    monkeypatch.setattr(application, "build_lab_tool_registry", original)
    result = ask(client, QUESTION, first["sessionId"])
    assert result["responseState"] == "needs_clarification" and "analysis" not in result


def test_continuation_never_silently_drops_previous_filter():
    client = application.app.test_client()
    _, first = upload(client, "通道2，采样率100Hz，0.5–3Hz带通滤波并分析主峰")
    result = ask(client, QUESTION, first["sessionId"])
    assert result["responseState"] == "needs_clarification" and "analysis" not in result
    assert result["clarificationFields"] == ["analysis_parameters.filter"]
    assert result["errorCode"] == "missing_processing_choice"
    assert application.load_experiment_session_state(first["sessionId"]).last_analysis_run_id == first["agentRun"]["runId"]


@pytest.mark.parametrize("query,filtered", [
    ("沿用刚才的滤波参数，继续分析通道4", True),
    ("继续分析通道4的原始信号，不滤波", False),
])
def test_explicit_processing_choice_and_goal_reuse_are_independent(query, filtered):
    client = application.app.test_client()
    _, first = upload(client, "通道2，采样率100Hz，0.5–3Hz带通滤波并分析主峰")
    result = ask(client, query, first["sessionId"])
    assert result["responseState"] == "completed"
    assert ("filter" in result["analysis"]["calculated_result"]) is filtered
    assert result["analysis"]["calculated_result"]["spectrum"]["dominant_frequency_hz"] == pytest.approx(1.2)
    assert result["experimentContext"]["analysis_context"]["source_run_id"] == first["agentRun"]["runId"]

