"""Original statistical / missing-rate / stored-source contracts via real HTTP."""

import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path

import pytest

import app as application
from flexresearch.experiment_analysis import run_signal_analysis


ROOT = Path(__file__).resolve().parents[2]


def upload(client, raw, question, **extra):
    response = client.post("/api/analyze", data={"file": (io.BytesIO(raw), "SYNTHETIC-signal.csv"),
        "question": question, "bindContext": "true", **extra}, content_type="multipart/form-data")
    assert response.status_code == 200, response.text
    return response.get_json()


def test_basic_statistics_original_question_has_typed_math_and_persisted_source():
    client = application.app.test_client()
    raw = (ROOT / "eval/fixtures/generic_two_column.csv").read_bytes()
    question = "给这个两列信号做基础统计。"
    result = upload(client, raw, question)
    analysis = result["agent"]
    assert result["intent"] == "data_analysis" and result["responseState"] == "completed"
    assert [s["tool_name"] for s in analysis["trajectory"]] == ["load_experiment_data", "load_csv", "analyze_signal"]
    statistics = analysis["calculated_result"]["statistics"]
    assert {key: statistics[key] for key in ("valid_point_count", "mean", "min", "max", "drift", "slope")} == {"valid_point_count": 5, "mean": 6, "min": 2, "max": 10, "drift": 8, "slope": 4}
    assert statistics["slope_axis_unit"] == "second"
    source = next(r for r in analysis["source_refs"] if r["tool_run_id"] == statistics["tool_run_id"])
    assert source["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert source["channel"] == "signal" and source["experiment_id"] == result["experimentContext"]["experiment_id"]
    assert source["parameters"]["experiment_context_tool_run_id"] == analysis["trajectory"][0]["tool_run_id"]
    assert analysis["state"]["step_count"] == 3
    assert "可疑" not in result["answer"] and "均值为 6" in result["answer"]
    persisted = client.get(f"/api/agent-runs/{result['agentRun']['runId']}").get_json()
    assert [s["tool_name"] for s in persisted["toolCalls"]] == ["load_experiment_data", "load_csv", "analyze_signal"]
    assert persisted["final_result"]["calculated_result"] == analysis["calculated_result"]
    with application.get_db() as db:
        parameters = db.execute("SELECT parameters_json FROM analysis_runs WHERE analysis_type='statistics'").fetchone()
    assert json.loads(parameters[0]) == source["parameters"]
    history = client.get(f"/api/sessions/{result['sessionId']}").get_json()["messages"]
    assert history[-2]["content"] == question and history[-1]["result"]["agent"] == analysis


def test_missing_rate_has_explicit_field_no_frequency_claim_and_survives_history():
    client = application.app.test_client()
    raw = (ROOT / "eval/fixtures/time_signal_without_sample_rate.csv").read_bytes()
    question = "找这段时域信号的主要频率。"
    result = upload(client, raw, question)
    assert result["intent"] == "signal_analysis"
    assert result["responseState"] == "needs_clarification"
    assert result["clarificationFields"] == result["agent"]["clarification_fields"] == ["sample_rate_hz"]
    assert result["agent"]["calculated_result"] == {}
    assert result["agent"]["artifacts"] == []
    assert result["agent"]["stop_reason"] == "needs_clarification"
    assert [s["tool_name"] for s in result["agent"]["trajectory"]] == ["load_experiment_data", "load_csv"]
    history = client.get(f"/api/sessions/{result['sessionId']}").get_json()["messages"]
    assert history[-1]["result"]["clarificationFields"] == ["sample_rate_hz"]
    assert history[-2]["content"] == question
    second = client.post("/api/research", json={"query": "继续找主要频率，采样率100Hz", "sessionId": result["sessionId"], "useModel": False}).get_json()
    assert second["responseState"] == "completed" and second["clarificationFields"] == []
    assert second["analysis"]["calculated_result"]["spectrum"]


@pytest.mark.parametrize("fault", ["scope", "hash", "timeout", "nonimmutable", "wrong_file"])
def test_context_failure_never_runs_numeric_tools_or_returns_claims(fault, monkeypatch):
    client = application.app.test_client()
    raw = (ROOT / "eval/fixtures/generic_two_column.csv").read_bytes()
    created = upload(client, raw, "读取数据")
    state = created["experimentContext"]
    path = next(application.MEASUREMENT_DIR.glob("*.csv"))
    registry = application.build_application_tool_registry()
    original = registry._tools["load_experiment_data"]
    def corrupted(payload):
        if fault == "timeout":
            raise TimeoutError("fixture context unavailable")
        output = original.handler(payload)
        if fault == "scope":
            output.experiment.experiment_id += 1
        elif fault == "hash":
            output.files[0].sha256 = "0" * 64
        elif fault == "nonimmutable":
            output.files[0].immutable = False
        else:
            output.files[0].file_id += 1
        return output
    registry._tools["load_experiment_data"] = replace(original, handler=corrupted)
    result = run_signal_analysis(registry, path, "基础统计", experiment_id=state["experiment_id"], file_id=state["file_id"])
    assert result.status == "error" and result.calculated_result == {} and result.artifacts == []
    assert [s.tool_name for s in result.trajectory] == ["load_experiment_data"]
    assert path.read_bytes() == raw


def test_context_consumes_real_budget_before_csv_and_math():
    client = application.app.test_client()
    created = upload(client, b"time_s,signal\n0,1\n1,3\n", "读取数据")
    result = run_signal_analysis(application.build_application_tool_registry(), next(application.MEASUREMENT_DIR.glob("*.csv")), "基础统计", experiment_id=created["experimentContext"]["experiment_id"], max_steps=1)
    assert result.stop_reason == "step_budget_exhausted" and len(result.trajectory) == 1
    assert result.calculated_result == {} and result.state["max_steps"] == 1


def test_changed_bytes_between_context_and_csv_are_rejected(monkeypatch):
    client = application.app.test_client()
    created = upload(client, b"time_s,signal\n0,1\n1,3\n", "读取数据")
    path = next(application.MEASUREMENT_DIR.glob("*.csv"))
    registry = application.build_application_tool_registry()
    original = registry._tools["load_csv"]
    def changed(payload):
        output = original.handler(payload)
        output.source_sha256 = "0" * 64
        return output
    registry._tools["load_csv"] = replace(original, handler=changed)
    result = run_signal_analysis(registry, path, "基础统计", experiment_id=created["experimentContext"]["experiment_id"])
    assert result.status == "error" and result.calculated_result == {}
    assert [s.tool_name for s in result.trajectory] == ["load_experiment_data", "load_csv"]

