import io
import math

import pytest

import app as application


def experiment(client, name, frequency=1.2, project_id=None):
    identifier = client.post("/api/experiments", json={"name": name, "projectId": project_id}).json["item"]["id"]
    raw = ("time_s,ch4\n"+"\n".join(f"{i/100},{math.sin(2*math.pi*frequency*i/100)}" for i in range(1000))).encode()
    uploaded = client.post("/api/analyze", data={"file": (io.BytesIO(raw), name+".csv"), "experimentId": str(identifier), "question": "通道4分析主要频率并画图"}, content_type="multipart/form-data")
    assert uploaded.status_code == 200
    return identifier, uploaded.json


def ask(client, query):
    response = client.post("/api/research", json={"query": query, "useModel": False})
    assert response.status_code == 200
    return response.json


def test_report_assembles_multiple_runs_without_mixing_unselected_experiments():
    client = application.app.test_client()
    identifier, first = experiment(client, "selected")
    other, excluded = experiment(client, "excluded", 2.4)
    second = ask(client, f"实验{identifier}通道4计算均值")
    output = ask(client, f"生成实验{identifier}的报告")
    report = output["experimentReport"]
    assert output["responseState"] == "completed"
    assert [item["tool"] for item in output["tools"]] == ["search_experiment", "generate_report"]
    assert set(report["source_run_ids"]) == {first["agentRun"]["runId"], second["analysisRun"]["runId"]}
    assert excluded["agentRun"]["runId"] not in report["markdown"]
    downloaded = client.get(output["reportUrl"])
    assert downloaded.status_code == 200 and downloaded.text == report["markdown"]
    for heading in ("Experiment Metadata", "Data Quality", "Processing Methods", "Measured Result", "Calculated Result", "Agent Interpretation", "Figures & Derived Artifacts", "Limitations", "Source & Provenance"):
        assert f"## {heading}" in downloaded.text
    assert first["agent"]["artifacts"][0]["url"] in downloaded.text
    assert first["agent"]["source_refs"][0]["source_sha256"] in downloaded.text
    # Report URLs are immutable snapshots, not latest-state regeneration.
    with application.get_db() as db:
        db.execute("UPDATE experiments SET name = 'later rename' WHERE id = ?", (identifier,))
    assert client.get(output["reportUrl"]).text == report["markdown"]
    history = client.get(f"/api/sessions/{output['sessionId']}").json
    assert history["messages"][-1]["result"]["reportUrl"] == output["reportUrl"]


def test_report_marks_missing_analysis_and_changed_files_without_inventing_results():
    client = application.app.test_client()
    empty = client.post("/api/experiments", json={"name": "empty"}).json["item"]["id"]
    result = ask(client, f"生成实验{empty}的报告")
    assert result["responseState"] == "partial"
    assert result["experimentReport"]["source_run_ids"] == []
    identifier, uploaded = experiment(client, "changed")
    (application.MEASUREMENT_DIR / uploaded["measurement"]["filename"]).write_bytes(b"changed")
    result = ask(client, f"生成实验{identifier}的报告")
    assert result["responseState"] == "partial"
    assert result["experimentReport"]["history"][0]["files"][0]["integrity"] == "mismatch"
    assert result["experimentReport"]["history"][0]["runs"]  # historical, explicitly unverified now


def test_plan_recommendations_bind_real_latest_runs_and_missing_protocol():
    client = application.app.test_client()
    ids, runs = [], []
    for index in range(3):
        identifier, uploaded = experiment(client, f"repeat{index}")
        ids.append(identifier)
        runs.append(uploaded["agentRun"]["runId"])
    result = ask(client, f"根据实验{ids[0]}、{ids[1]}和{ids[2]}建议下一次实验方案")
    plan = result["experimentPlan"]
    assert result["responseState"] == "partial"
    assert plan["approval_required"] is True and plan["mode"] == "history_grounded_rules"
    assert plan["comparison_notes"]  # Pulse-feature cross-history comparison is not implemented.
    assert len(plan["observations"]) == 3
    assert all(item["source_run_ids"] and set(item["source_run_ids"]) <= set(runs) for item in plan["recommendations"])
    assert any("excitation_current" in item for item in plan["unresolved_parameters"])
    assert {item["category"] for item in plan["recommendations"]} == {"replication", "protocol"}
    assert all(item["calculated_result"]["spectrum"]["dominant_frequency_hz"] == pytest.approx(1.2) for item in plan["observations"])


def test_unscoped_history_or_missing_experiment_requests_clarification():
    client = application.app.test_client()
    result = ask(client, "根据前3次实验结果建议下一次实验")
    assert result["errorCode"] == "history_scope_required"
    assert result["tools"] == []
    missing = ask(client, "生成实验999的报告")
    assert missing["responseState"] == "needs_clarification"
    assert missing["experimentReport"] == {}


def test_latest_failed_attempt_is_not_hidden_by_an_older_success():
    client = application.app.test_client()
    identifier, successful = experiment(client, "failed-later")
    failed = ask(client, f"实验{identifier}通道99分析主峰")
    assert failed["analysis"]["status"] == "error"
    plan = ask(client, f"根据实验{identifier}建议下一次实验")["experimentPlan"]
    assert plan["status"] == "needs_evidence"
    assert plan["observations"][0]["source_run_id"] == failed["analysisRun"]["runId"]
    assert plan["observations"][0]["status"] == "error"
    assert not any(item["category"] == "replication" for item in plan["recommendations"])


def test_changed_source_prevents_a_ready_plan():
    client = application.app.test_client()
    identifier, uploaded = experiment(client, "changed-plan")
    (application.MEASUREMENT_DIR / uploaded["measurement"]["filename"]).write_bytes(b"tampered")
    result = ask(client, f"根据实验{identifier}建议下一次实验")
    assert result["responseState"] == "partial"
    assert result["experimentPlan"]["status"] == "needs_evidence"
    assert result["experimentPlan"]["recommendations"][0]["category"] == "integrity"


def test_project_recent_three_does_not_include_another_project():
    client = application.app.test_client()
    project = client.post("/api/projects", json={"name": "selected project"}).json["item"]["id"]
    excluded, _ = experiment(client, "outside")
    expected = [experiment(client, f"inside{index}", project_id=project)[0] for index in range(3)]
    result = ask(client, f"根据项目{project}最近3次实验建议下一次实验方案")
    assert result["responseState"] == "partial"
    assert set(result["experimentPlan"]["experiment_ids"]) == set(expected)
    assert excluded not in result["experimentPlan"]["experiment_ids"]

