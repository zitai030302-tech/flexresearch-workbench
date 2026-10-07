import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path

import pytest

import app as application


ROOT = Path(__file__).resolve().parents[2]
QUESTION = "分析这组已知线性 I-V，计算零偏微分电阻。"


def upload(raw=None, question=QUESTION):
    raw = raw if raw is not None else (ROOT / "eval/fixtures/iv_1kohm.csv").read_bytes()
    response = application.app.test_client().post("/api/analyze", data={"file": (io.BytesIO(raw), "SYNTHETIC-IV.csv"), "question": question, "bindContext": "true"}, content_type="multipart/form-data")
    assert response.status_code == 200, response.text
    return response.get_json(), raw


def test_iv_upload_persists_exact_tool_result_parameters_and_report_then_can_reanalyze():
    payload, raw = upload()
    assert payload["intent"] == "data_analysis" and payload["responseState"] == "completed"
    result = payload["agent"]
    assert [s["tool_name"] for s in result["trajectory"]] == ["load_experiment_data", "load_csv", "analyze_signal"]
    assert result["calculated_result"]["iv"]["differential_resistance_ohm"] == pytest.approx(1000)
    assert "1000 Ω" in payload["answer"] and result["state"]["sample_rate"] is None
    assert len(payload["answer"]) < 150 and "限制：" not in payload["answer"]
    assert len(result["limitations"]) == 3  # Retained in structured result/report/details.
    refs = [ref for ref in result["source_refs"] if ref["tool_run_id"] == result["trajectory"][-1]["tool_run_id"]]
    assert len(refs) == 1
    ref = refs[0]
    assert ref["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert ref["channel"] == "current_mA" and ref["experiment_id"] == payload["experimentContext"]["experiment_id"]
    assert ref["parameters"]["input_tool_run_id"] == result["trajectory"][1]["tool_run_id"]
    assert ref["parameters"]["experiment_context_tool_run_id"] == result["trajectory"][0]["tool_run_id"]
    client = application.app.test_client()
    saved = client.get(f"/api/agent-runs/{payload['agentRun']['runId']}").get_json()
    assert saved["final_result"] == result
    with application.get_db() as db:
        row = db.execute("SELECT parameters_json,result_json FROM analysis_runs WHERE analysis_type='iv'").fetchone()
        assert json.loads(row[0]) == ref["parameters"]
        assert json.loads(row[1]) == result["calculated_result"]["iv"]
        metric = json.loads(db.execute("SELECT metrics_json FROM measurements").fetchone()[0])
        assert len(metric) == 1 and metric[0]["value"] == "1000"
    report = client.get(f"/api/agent-runs/{payload['agentRun']['runId']}/report.md").text
    assert "零偏附近微分电阻为 1000 Ω" in report and ref["source_sha256"] in report
    review = client.get(f"/api/agent-runs/{payload['agentRun']['runId']}/report-review").get_json()
    assert review["status"] == "supported_within_rubric" and review["recognized_claim_count"] == 1
    history = client.get(f"/api/sessions/{payload['sessionId']}").get_json()["messages"]
    assert history[-2]["content"] == QUESTION and history[-1]["result"]["agent"] == result
    again = client.post("/api/research", json={"query": "继续计算零偏微分电阻", "sessionId": payload["sessionId"], "useModel": False}).get_json()
    assert again["responseState"] == "completed"
    assert again["analysis"]["calculated_result"]["iv"]["differential_resistance_ohm"] == pytest.approx(1000)
    assert next(application.MEASUREMENT_DIR.glob("*.csv")).read_bytes() == raw


@pytest.mark.parametrize("change", ["unit", "missing", "ambiguous_current", "filter"])
def test_invalid_iv_request_clears_legacy_resistance_and_never_claims_success(change):
    raw = (ROOT / "eval/fixtures/iv_1kohm.csv").read_bytes()
    question = QUESTION
    if change == "unit":
        raw = raw.replace(b"current_mA", b"current")
    elif change == "missing":
        raw = raw.replace(b"0,0.002", b"0,")
    elif change == "ambiguous_current":
        raw = b"voltage_V,current_mA,current2_mA\n-1,-1,-2\n-.1,-.1,-.2\n0,0,0\n.1,.1,.2\n1,1,2\n"
    else:
        question += "并滤波。"
    result, _ = upload(raw, question)
    assert result["responseState"] == "needs_clarification"
    assert result["agent"]["calculated_result"] == {} and result["metrics"] == []
    assert result["measurement"]["metrics"] == [] and "ivParameters" not in result
    assert result["agent"]["clarification_fields"] == ["iv_curve"]
    assert "1000" not in result["answer"] and "I–V计算未完成" in result["answer"]


def test_iv_zero_conductance_is_explicit_not_a_finite_resistance():
    result, _ = upload(b"voltage_V,current_A\n-1,0\n-.1,0\n0,0\n.1,0\n1,0\n")
    assert result["agent"]["calculated_result"]["iv"]["differential_resistance_ohm"] is None
    assert result["agent"]["stop_reason"] == "undefined_differential_resistance"
    assert "没有有限微分电阻" in result["answer"]
    assert result["responseState"] != "completed"


def test_iv_tool_timeout_never_exposes_legacy_resistance(monkeypatch):
    build = application.build_application_tool_registry
    def registry():
        tools = build()
        original = tools._tools["analyze_signal"]
        def unavailable(_payload):
            raise TimeoutError("synthetic I-V failure")
        tools._tools["analyze_signal"] = replace(original, handler=unavailable)
        return tools
    monkeypatch.setattr(application, "build_application_tool_registry", registry)
    result, _ = upload()
    assert result["agent"]["status"] != "complete" and result["agent"]["calculated_result"] == {}
    assert result["metrics"] == [] and "1000" not in result["answer"]


@pytest.mark.parametrize("plot_fails", [False, True])
def test_iv_plot_uses_bias_axis_and_preserves_numeric_result_on_failure(monkeypatch, plot_fails):
    if plot_fails:
        build = application.build_application_tool_registry
        def registry():
            tools = build()
            def unavailable(_payload):
                raise TimeoutError("synthetic plot unavailable")
            tools._tools["plot_signal"] = replace(tools._tools["plot_signal"], handler=unavailable)
            return tools
        monkeypatch.setattr(application, "build_application_tool_registry", registry)
    result, raw = upload(question=QUESTION+"并画图。")
    agent = result["agent"]
    assert agent["calculated_result"]["iv"]["differential_resistance_ohm"] == pytest.approx(1000)
    assert [s["tool_name"] for s in agent["trajectory"]] == ["load_experiment_data", "load_csv", "analyze_signal", "plot_signal"]
    if plot_fails:
        assert agent["status"] == "partial" and not agent["artifacts"]
        assert agent["stop_reason"] == "tool_error"
    else:
        artifact = agent["artifacts"][0]
        assert artifact["metadata"]["x_label"] == "voltage_V"
        assert artifact["metadata"]["y_label"] == "current_mA"
        assert artifact["metadata"]["parent_source_sha256"] == hashlib.sha256(raw).hexdigest()
        response = application.app.test_client().get(artifact["url"])
        assert response.status_code == 200 and response.data.startswith(b"\x89PNG")
        response.close()

