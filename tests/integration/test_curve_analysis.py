import hashlib
import io
import json
from pathlib import Path

import pytest

import app as app_module
from flexresearch.tooling import ToolExecution, ToolRegistry


FIXTURES = Path(__file__).resolve().parents[2] / "eval/fixtures"


def upload(client, name, question, **fields):
    return client.post("/api/analyze", data={"file": (io.BytesIO((FIXTURES/name).read_bytes()), name), "bindContext": "true", "question": question, **fields}, content_type="multipart/form-data")


@pytest.mark.parametrize("name,query,key,expected", [("strain-gf2.csv", "计算应变传感器的 GF。", "gauge_factor", 2), ("cycle-retention92.csv", "计算 1000 次循环后的保持率。", "retention_percent", 92)])
def test_upload_curve_tool_provenance_report_and_history(name, query, key, expected):
    client = app_module.app.test_client()
    response = upload(client, name, query)
    assert response.status_code == 200, response.json
    payload = response.json
    assert payload["intent"] == "data_analysis" and payload["responseState"] == "completed"
    analysis = payload["agent"]
    assert [step["tool_name"] for step in analysis["trajectory"]] == ["load_experiment_data", "load_csv", "extract_features"]
    assert all(step["status"] == "complete" for step in analysis["trajectory"])
    assert analysis["calculated_result"]["curve_features"][key] == pytest.approx(expected)
    ref = analysis["source_refs"][0]
    digest = hashlib.sha256((FIXTURES/name).read_bytes()).hexdigest()
    assert ref["source_sha256"] == digest and ref["experiment_id"] == payload["experimentContext"]["experiment_id"]
    assert ref["tool_run_id"] == analysis["trajectory"][-1]["tool_run_id"]
    assert ref["parameters"]["input_tool_run_id"] == analysis["trajectory"][1]["tool_run_id"]
    run_id = payload["agentRun"]["runId"]
    stored = client.get(f"/api/agent-runs/{run_id}").json
    assert stored["final_result"]["calculated_result"] == analysis["calculated_result"]
    report = client.get(f"/api/agent-runs/{run_id}/report.md").text
    assert digest in report and ref["tool_run_id"] in report and "curve-features-v1" in report
    assert "GF为" in payload["answer"] if key == "gauge_factor" else "1000 次循环保持率为 92%" in payload["answer"]
    with app_module.get_db() as db:
        metrics = json.loads(db.execute("SELECT metrics_json FROM measurements WHERE id = ?", (payload["measurement"]["id"],)).fetchone()[0])
        history = json.loads(db.execute("SELECT result_json FROM research_messages WHERE session_id = ? AND role='assistant'", (payload["sessionId"],)).fetchone()[0])
        parameters = json.loads(db.execute("SELECT parameters_json FROM analysis_runs WHERE analysis_type='curve_features'").fetchone()[0])
    assert metrics == payload["metrics"] == payload["measurement"]["metrics"]
    assert history["agent"] == analysis
    assert parameters == ref["parameters"]
    review = client.get(f"/api/agent-runs/{run_id}/report-review").json
    assert review["status"] == "supported_within_rubric", review


def test_missing_target_keeps_raw_archive_but_no_old_last_point_metric():
    client = app_module.app.test_client()
    result = upload(client, "cycle-retention92.csv", "计算 1200 次循环后的保持率。").json
    assert result["responseState"] == "needs_clarification"
    assert result["agent"]["calculated_result"] == {}
    assert result["metrics"] == result["measurement"]["metrics"] == []
    assert "1200" in result["answer"] and "未插值" in result["answer"]
    assert "70%" not in result["answer"]
    assert (app_module.MEASUREMENT_DIR/result["measurement"]["filename"]).read_bytes() == (FIXTURES/"cycle-retention92.csv").read_bytes()


def test_stored_curve_followup_selects_same_file_and_new_cycle():
    client = app_module.app.test_client()
    first = upload(client, "cycle-retention92.csv", "计算 1000 次循环后的保持率。").json
    reply = client.post("/api/research", json={"sessionId": first["sessionId"], "query": "计算 1500 次循环后的保持率。", "useModel": False}).json
    assert reply["responseState"] == "completed", reply
    assert reply["analysis"]["calculated_result"]["curve_features"]["retention_percent"] == 70
    assert reply["experimentContext"]["file_id"] == first["experimentContext"]["file_id"]


def test_stored_strain_metadata_conflict_cannot_be_overridden_by_column():
    client = app_module.app.test_client()
    first = upload(client, "strain-gf2.csv", "计算GF。").json
    with app_module.get_db() as db:
        db.execute("UPDATE experiments SET metadata_json=? WHERE id=?", (json.dumps({"strain_unit": "fraction"}), first["experimentContext"]["experiment_id"]))
    reply = client.post("/api/research", json={"sessionId": first["sessionId"], "query": "计算GF。", "useModel": False}).json
    assert reply["responseState"] == "needs_clarification"
    assert "冲突" in reply["answer"] and "GF为" not in reply["answer"]
    assert reply["analysis"]["calculated_result"] == {}


def test_curve_requested_plot_is_real_and_new_not_ignored():
    client = app_module.app.test_client()
    payload = upload(client, "strain-gf2.csv", "计算GF并画图。").json
    assert payload["responseState"] == "completed", payload
    assert [step["tool_name"] for step in payload["agent"]["trajectory"]] == ["load_experiment_data", "load_csv", "extract_features", "plot_signal"]
    plot = payload["agent"]["artifacts"][0]
    with client.get(plot["url"]) as response:
        assert response.status_code == 200 and response.data.startswith(b"\x89PNG")
    assert (app_module.MEASUREMENT_DIR/payload["measurement"]["filename"]).read_bytes() == (FIXTURES/"strain-gf2.csv").read_bytes()


def test_curve_does_not_ignore_filter_request():
    client = app_module.app.test_client()
    payload = upload(client, "strain-gf2.csv", "先滤波再计算GF。").json
    assert payload["responseState"] == "needs_clarification"
    assert "不会忽略滤波要求" in payload["answer"]
    assert payload["metrics"] == [] and payload["agent"]["calculated_result"] == {}


def test_modified_stored_curve_is_not_analyzed():
    client = app_module.app.test_client()
    first = upload(client, "strain-gf2.csv", "计算GF。").json
    (app_module.MEASUREMENT_DIR/first["measurement"]["filename"]).write_bytes(b"strain_percent,resistance_ohm\n0,100\n10,999\n")
    reply = client.post("/api/research", json={"sessionId": first["sessionId"], "query": "计算GF。", "useModel": False}).json
    assert reply["responseState"] == "needs_clarification"
    assert "SHA-256" in reply["answer"] and "GF为" not in reply["answer"]


def test_upload_missing_zero_baseline_is_partial_not_fake_gf():
    client = app_module.app.test_client()
    payload = client.post("/api/analyze", data={"file": (io.BytesIO(b"strain_percent,resistance_ohm\n1,102\n5,110\n10,120\n"), "no-zero.csv"), "bindContext": "true", "question": "计算GF。"}, content_type="multipart/form-data").json
    assert payload["responseState"] == "needs_clarification"
    assert "实测零应变" in payload["answer"]
    assert payload["metrics"] == [] and payload["agent"]["calculated_result"] == {}
    assert payload["agent"]["trajectory"][-1]["status"] == "error"


def test_curve_plot_failure_preserves_verified_gf_but_not_fake_artifact(monkeypatch):
    original = ToolRegistry.execute
    def fail_plot(self, name, arguments):
        if name == "plot_signal":
            return ToolExecution(tool_run_id="f"*32, tool_name=name, status="timeout", arguments=arguments, error_code="timeout", error="synthetic plot timeout", recoverable=True, latency_ms=1)
        return original(self, name, arguments)
    monkeypatch.setattr(ToolRegistry, "execute", fail_plot)
    client = app_module.app.test_client()
    payload = upload(client, "strain-gf2.csv", "计算GF并画图。").json
    assert payload["responseState"] == "needs_clarification"
    assert payload["agent"]["status"] == "partial"
    assert payload["agent"]["calculated_result"]["curve_features"]["gauge_factor"] == 2
    assert payload["agent"]["artifacts"] == []
    assert "timeout" in payload["answer"]

