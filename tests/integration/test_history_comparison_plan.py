"""Latest scoped history → real aligned numerical tools → evidenced next plan."""

import hashlib
import io

import pytest

import app as application
from flexresearch.history import ExperimentHistoryInput, HistoryPlanningInput


def seed(client, *, units=True, changed_frequency=False, second_channel=False):
    project = client.post("/api/projects", json={"name": "SYNTHETIC controlled Bio-Z"}).json["item"]["id"]
    ids, uploads, raw_files = [], [], []
    for index in range(3):
        metadata = {"sample_rate_hz": 100, "frequency_sweep_hz": [10, 100], "excitation_current": "as defined by approved SOP", "electrode_geometry": "fixture geometry", "sop_reference": "SYNTHETIC-SOP", "device_id": "fixture AD5940", "material": "hydrogel A" if index == 0 else "hydrogel B", "posture": "fixture rest", "activity_condition": "none", "temperature_c": 23}
        identifier = client.post("/api/experiments", json={"name": f"SYNTHETIC repeat {index}", "projectId": project, "metadata": metadata}).json["item"]["id"]
        channel = 14 if second_channel and index == 1 else 4
        suffix = "_ohm" if units else ""
        frequency = 200 if changed_frequency and index == 2 else 100
        raw = f"frequency_hz,ch{channel}_real{suffix},ch{channel}_imag{suffix}\n{frequency},{3*(index+1)},{4*(index+1)}\n10,{3*(index+1)},{4*(index+1)}\n".encode()
        uploaded = client.post("/api/analyze", data={"experimentId": str(identifier), "question": f"通道{channel}计算平均阻抗", "file": (io.BytesIO(raw), f"SYNTHETIC-bioz-{index}.csv")}, content_type="multipart/form-data")
        assert uploaded.status_code == 200
        ids.append(identifier)
        uploads.append(uploaded.json)
        raw_files.append(raw)
    return project, ids, uploads, raw_files


def ask(client, uploads, query="根据前 3 次实验结果建议下一次实验。"):
    response = client.post("/api/research", json={"query": query, "sessionId": uploads[-1]["sessionId"], "useModel": False})
    assert response.status_code == 200
    return response.json


def test_current_project_last_three_compare_then_plan_with_exact_ground_truth():
    client = application.app.test_client()
    _, ids, uploads, raw = seed(client)
    # A later, unrelated experiment must never become the implicit project scope.
    client.post("/api/experiments", json={"name": "excluded unrelated run"})
    output = ask(client, uploads)
    plan = output["experimentPlan"]
    assert output["responseState"] == "completed"
    assert set(plan["experiment_ids"]) == set(ids)
    assert len(plan["comparisons"]) == 2
    assert [item["tool"] for item in output["tools"]] == ["search_experiment"]*3 + ["compare_stored_experiments"]*2 + ["create_experiment_plan"]
    historical = [item["agentRun"]["runId"] for item in uploads]
    for index, item in enumerate(plan["comparisons"], 1):
        values = item["calculated_result"]["comparison"]
        assert item["experiment_ids"] == [ids[0], ids[index]]
        assert values["mean_delta"] == pytest.approx(5*index)
        assert values["rmse"] == pytest.approx(5*index)
        assert values["relative_change_percent"] == pytest.approx(100*index)
        assert item["source_run_ids"] == [historical[0], historical[index]]
        assert {ref["source_sha256"] for ref in item["source_refs"]} == {hashlib.sha256(raw[0]).hexdigest(), hashlib.sha256(raw[index]).hexdigest()}
        trace = client.get(f"/api/agent-runs/{item['comparison_run_id']}").json
        assert "compare_experiments" in [call["tool_name"] for call in trace["toolCalls"]]
        assert trace["final_result"]["state"]["planning_source_run_ids"] == item["source_run_ids"]
        assert client.get(f"/api/agent-runs/{item['comparison_run_id']}/report.md").status_code == 200
    assert {item["name"] for item in plan["variables"]} == {"material"}
    assert any(item["category"] == "controlled_followup" for item in plan["recommendations"])
    assert sum(item["category"] == "controlled_followup" for item in plan["recommendations"]) == 1
    assert not any(item["category"] == "replication" for item in plan["recommendations"])
    assert all(item["source_run_ids"] for item in plan["recommendations"])
    assert plan["controls"] and plan["quality_checks"] and plan["approval_required"]
    assert plan["unresolved_parameters"] == []
    history = client.get(f"/api/sessions/{output['sessionId']}").json
    assert history["messages"][-1]["result"]["experimentPlan"] == plan
    # A comparison run is not misclassified as a new failed acquisition on repeat.
    repeated = ask(client, uploads)["experimentPlan"]
    assert {item["source_run_id"] for item in repeated["observations"]} == set(historical)
    assert len(repeated["comparisons"]) == 2


@pytest.mark.parametrize("failure", ["units", "frequency", "channel"])
def test_incomparable_history_retains_explanation_without_fabricating_differences(failure):
    client = application.app.test_client()
    _, _, uploads, _ = seed(client, units=failure != "units", changed_frequency=failure == "frequency", second_channel=failure == "channel")
    output = ask(client, uploads)
    plan = output["experimentPlan"]
    assert plan["comparison_notes"]
    assert len(plan["comparisons"]) == (1 if failure == "frequency" else 0)
    assert output["responseState"] == "partial"
    if failure != "frequency":
        assert not any(item["category"] == "comparison" for item in plan["recommendations"])


def test_latest_failed_bioz_analysis_is_not_replaced_by_old_success():
    client = application.app.test_client()
    _, ids, uploads, _ = seed(client)
    failed = ask(client, uploads, f"实验{ids[-1]}通道99计算平均阻抗")
    assert failed["analysis"]["status"] == "error"
    result = ask(client, uploads)
    assert result["responseState"] == "partial"
    assert result["experimentPlan"]["comparisons"] == []
    assert any(item["source_run_id"] == failed["analysisRun"]["runId"] for item in result["experimentPlan"]["observations"])


def test_plan_tool_rejects_out_of_scope_comparison_and_stale_latest_analysis():
    client = application.app.test_client()
    _, ids, uploads, _ = seed(client)
    plan = ask(client, uploads)["experimentPlan"]
    comparison_ids = [item["comparison_run_id"] for item in plan["comparisons"]]
    with pytest.raises(ValueError, match="范围"):
        application.create_experiment_plan_tool(HistoryPlanningInput(experiment_ids=ids[1:], comparison_run_ids=comparison_ids))
    ask(client, uploads, f"实验{ids[0]}通道4计算平均阻抗")
    with pytest.raises(ValueError, match="最新分析"):
        application.create_experiment_plan_tool(HistoryPlanningInput(experiment_ids=ids, comparison_run_ids=comparison_ids))


def test_multiple_or_unknown_conditions_do_not_become_a_single_variable_causal_claim():
    client = application.app.test_client()
    _, ids, uploads, _ = seed(client)
    import json
    with application.get_db() as db:
        metadata = json.loads(db.execute("SELECT metadata_json FROM experiments WHERE id=?", (ids[1],)).fetchone()[0])
        metadata["posture"] = "changed posture"
        db.execute("UPDATE experiments SET metadata_json=? WHERE id=?", (json.dumps(metadata), ids[1]))
        metadata = json.loads(db.execute("SELECT metadata_json FROM experiments WHERE id=?", (ids[2],)).fetchone()[0])
        metadata.pop("temperature_c")
        db.execute("UPDATE experiments SET metadata_json=? WHERE id=?", (json.dumps(metadata), ids[2]))
    plan = ask(client, uploads)["experimentPlan"]
    assert {item["name"] for item in plan["comparisons"][0]["changed_conditions"]} == {"material", "posture"}
    assert any("混杂" in item["reason"] for item in plan["recommendations"])
    assert any("temperature_c" in item for item in plan["unresolved_parameters"])
    assert not any(item["action"].startswith("验证材料变化") for item in plan["recommendations"])


def test_comparison_metadata_snapshot_must_still_match_when_building_plan():
    client = application.app.test_client()
    _, ids, uploads, _ = seed(client)
    plan = ask(client, uploads)["experimentPlan"]
    with application.get_db() as db:
        db.execute("UPDATE experiments SET metadata_json='{}' WHERE id=?", (ids[0],))
    with pytest.raises(ValueError, match="条件.*变化"):
        application.create_experiment_plan_tool(HistoryPlanningInput(experiment_ids=ids, comparison_run_ids=[item["comparison_run_id"] for item in plan["comparisons"]]))


@pytest.mark.parametrize("identifier", [True, 1.0, "1"])
def test_history_ids_are_strict_integers(identifier):
    with pytest.raises(ValueError):
        ExperimentHistoryInput(experiment_ids=[identifier])

