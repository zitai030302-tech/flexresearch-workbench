"""Resume explicit actions after clarification, using the original immutable file."""

import hashlib
import io

import numpy as np
import pandas as pd
import pytest

import app as application


PROMPT = "滤波并保存结果，但不要改原始文件。"


def upload(client, query=PROMPT, *, time_axis=True, session=None):
    axis = np.arange(1000) / 100
    columns = {"ch4": np.sin(2*np.pi*1.2*axis) + .3*np.sin(2*np.pi*12*axis)}
    if time_axis:
        columns = {"time_s": axis, **columns}
    raw = pd.DataFrame(columns).to_csv(index=False).encode()
    data = {"file": (io.BytesIO(raw), "pending.csv"), "bindContext": "true", "question": query}
    if session:
        data["sessionId"] = str(session)
    response = client.post("/api/analyze", data=data, content_type="multipart/form-data")
    assert response.status_code == 200
    return raw, response.json


def ask(client, first, query):
    response = client.post("/api/research", json={"query": query, "sessionId": first["sessionId"], "useModel": False})
    assert response.status_code == 200
    return response.json


def test_clarification_resumes_original_save_request_with_persisted_lineage():
    client = application.app.test_client()
    raw, first = upload(client)
    assert first["responseState"] == "needs_clarification"
    assert "analysis_parameters.filter" in first["clarificationFields"]
    assert first["agent"]["artifacts"] == []
    pending = first["experimentContext"]["pending_request"]
    assert pending["query"] == PROMPT and pending["filter"] is None
    assert pending["source_sha256"] == hashlib.sha256(raw).hexdigest()
    # Reconstruct the client; the next request must read SQL state, not globals.
    client = application.app.test_client()
    result = ask(client, first, "0.5–3 Hz带通，4阶")
    assert result["responseState"] == "completed"
    assert result["experimentContext"]["pending_request"] is None
    analysis = result["analysis"]
    assert [s["tool_name"] for s in analysis["trajectory"]] == ["load_experiment_data", "load_csv", "filter_signal", "export_signal"]
    derived, = analysis["artifacts"]
    with client.get(derived["url"]) as downloaded:
        assert downloaded.status_code == 200
        exported = downloaded.data
    values = pd.read_csv(io.BytesIO(exported))
    assert len(values) == 1000 and set(values) == {"time_s", "filtered_signal"}
    assert not np.allclose(values.filtered_signal, pd.read_csv(io.BytesIO(raw)).ch4)
    assert derived["metadata"]["sha256"] == hashlib.sha256(exported).hexdigest()
    assert derived["metadata"]["parent_source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert any(p.read_bytes() == raw for p in application.MEASUREMENT_DIR.glob("*.csv"))
    provenance = analysis["state"]["pending_request_context"]
    assert provenance == {"source_run_id": first["agentRun"]["runId"], "original_query": PROMPT, "parameter_reply": "0.5–3 Hz带通，4阶"}
    assert all(ref["parameters"]["pending_request_context"] == provenance for ref in analysis["source_refs"])
    report = client.get(result["reportUrl"]).text
    assert provenance["source_run_id"] in report and derived["url"] in report
    history = client.get(f"/api/sessions/{first['sessionId']}").json
    assert history["messages"][-2]["content"] == provenance["parameter_reply"]
    assert history["messages"][-1]["result"]["analysis"] == analysis


def test_multiple_clarifications_retain_explicit_band_until_sample_rate_provided():
    client = application.app.test_client()
    _, first = upload(client, time_axis=False)
    partial = ask(client, first, "0.5–3 Hz带通")
    assert partial["responseState"] == "needs_clarification"
    assert partial["analysis"]["artifacts"] == []
    assert partial["experimentContext"]["pending_request"]["filter"]["high_cut"] == 3
    result = ask(client, first, "采样率100 Hz")
    assert result["responseState"] == "completed"
    assert len(result["analysis"]["artifacts"]) == 1
    assert result["analysis"]["state"]["pending_request_context"]["source_run_id"] == first["agentRun"]["runId"]


def test_incomplete_new_band_cannot_fall_back_to_original_band():
    client = application.app.test_client()
    _, first = upload(client, query="0.5–3Hz带通滤波并保存结果", time_axis=False)
    result = ask(client, first, "采样率100Hz，改为低通5")
    assert result["responseState"] == "needs_clarification"
    assert "analysis" not in result
    assert not list(application.ARTIFACT_DIR.glob("*.csv"))


@pytest.mark.parametrize("reply", ["3–0.5 Hz带通", "0.5–3 Hz带通，采样率4Hz", "低通滤波"])
def test_invalid_or_incomplete_parameters_never_produce_a_saved_result(reply):
    client = application.app.test_client()
    _, first = upload(client)
    result = ask(client, first, reply)
    assert result["responseState"] != "completed" or "analysis" not in result
    assert not list(application.ARTIFACT_DIR.glob("*.csv"))


@pytest.mark.parametrize("mutation", ["bytes", "hash", "query", "run", "session"])
def test_pending_request_cannot_resume_with_inconsistent_source(mutation):
    client = application.app.test_client()
    _, first = upload(client)
    state = application.load_experiment_session_state(first["sessionId"])
    if mutation == "bytes":
        next(application.MEASUREMENT_DIR.glob("*.csv")).write_bytes(b"changed")
    elif mutation == "hash":
        state.pending_request.source_sha256 = "0" * 64
    elif mutation == "query":
        state.pending_request.query = "伪造的保存任务"
    elif mutation == "run":
        state.pending_request.source_run_id = "0" * 32
    else:
        first["sessionId"] = application.create_session("other")["id"]
    application.save_experiment_session_state(first["sessionId"], state)
    result = ask(client, first, "0.5–3 Hz带通")
    assert result["responseState"] == "needs_clarification"
    assert "analysis" not in result
    assert not list(application.ARTIFACT_DIR.glob("*.csv"))


def test_new_file_clears_pending_request_and_ordinary_chat_does_not_execute_it():
    client = application.app.test_client()
    _, first = upload(client)
    ordinary = ask(client, first, "你好")
    assert "analysis" not in ordinary
    _, replacement = upload(client, query="读取并概览这个 CSV", session=first["sessionId"])
    assert replacement["experimentContext"]["pending_request"] is None
    result = ask(client, replacement, "0.5–3 Hz带通")
    assert "analysis" not in result
    assert not list(application.ARTIFACT_DIR.glob("*.csv"))


def test_pending_from_stored_experiment_request_has_same_continuation_behavior():
    client = application.app.test_client()
    _, first = upload(client, query="读取并概览这个 CSV")
    partial = ask(client, first, PROMPT)
    assert partial["experimentContext"]["pending_request"]["query"] == PROMPT
    result = ask(client, first, "0.5–3 Hz带通")
    assert result["responseState"] == "completed"
    assert len(result["analysis"]["artifacts"]) == 1

