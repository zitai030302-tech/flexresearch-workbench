import hashlib
import json

import pytest

import app as application
PROMPT = "为柔性 Bio-Z 多频扫描写一个下一次实验方案草案。"


@pytest.fixture
def client(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Initial draft must not call network, model or unselected history")
    for name in ["request_json", "request_model_json", "collect_experiment_history"]:
        monkeypatch.setattr(application, name, forbidden)
    return application.app.test_client()


def test_initial_draft_runs_typed_tool_and_persists_exact_snapshot(client):
    output = client.post("/api/research", json={"query": PROMPT, "useModel": True, "useOpenAlex": True}).get_json()
    assert output["responseState"] == "completed" and output["intent"] == "experiment_design"
    assert output["sources"] == output["privateEvidence"] == []
    assert [step["tool"] for step in output["tools"]] == ["create_experiment_plan"]
    assert output["tools"][0]["status"] == "complete"
    assert output["tools"][0]["arguments"]["question"] == PROMPT
    plan = output["experimentPlan"]
    assert plan["basis"]["request_sha256"] == hashlib.sha256(PROMPT.encode()).hexdigest()
    assert not plan["executable"] and plan["approval_required"]
    assert len(output["answer"]) < 100
    stored = client.get(f"/api/agent-runs/{output['agentRun']['runId']}").get_json()
    assert stored["intent"] == "experiment_design" and stored["status"] == "complete"
    assert stored["state"]["stopReason"] == "draft_created"
    assert stored["final_result"]["experimentPlan"] == plan
    assert stored["toolCalls"][0]["source_refs"] == []
    downloaded = client.get(output["planUrl"])
    assert downloaded.status_code == 200 and downloaded.text == output["planMarkdown"]
    assert "attachment;" in downloaded.headers["Content-Disposition"]
    history = client.get(f"/api/sessions/{output['sessionId']}").get_json()
    assert history["messages"][-1]["result"]["experimentPlan"] == plan
    assert history["messages"][-1]["result"]["planUrl"] == output["planUrl"]
    with application.get_db() as db:
        for table in ["experiments", "experiment_files", "measurements", "analysis_runs", "research_run_sources"]:
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
        row = db.execute("SELECT arguments_json, source_refs_json FROM tool_calls WHERE tool_name='create_experiment_plan'").fetchone()
        assert json.loads(row["arguments_json"])["question"] == PROMPT
        assert json.loads(row["source_refs_json"]) == []
    logs = [json.loads(line) for line in (application.LOG_DIR / "agent-runs.jsonl").read_text().splitlines()]
    assert logs[-1]["finalResult"]["experimentPlan"] == plan


def test_unrelated_experiment_does_not_become_draft_evidence(client):
    identifier = client.post("/api/experiments", json={"name": "unrelated-existing-data"}).get_json()["item"]["id"]
    first = client.post("/api/research", json={"query": f"读取实验{identifier}", "useModel": False}).get_json()
    output = client.post("/api/research", json={"query": PROMPT, "sessionId": first["sessionId"]}).get_json()
    assert output["experimentPlan"]["experiment_ids"] == []
    assert output["experimentPlan"]["observations"] == []
    assert "unrelated-existing-data" not in output["planMarkdown"]


@pytest.mark.parametrize("query", [
    "根据前3次实验结果建议下一次Bio-Z多频扫描方案",
    "根据项目999最近3次实验建议下一次Bio-Z多频扫描方案",
])
def test_history_request_is_not_replaced_by_generic_draft(client, query):
    output = client.post("/api/research", json={"query": query}).get_json()
    assert output["responseState"] == "needs_clarification"
    assert output["errorCode"] == "history_scope_required"
    assert "experimentPlan" not in output


def test_draft_failure_is_persisted_without_fake_success(client, monkeypatch):
    def fail(_question):
        raise RuntimeError("synthetic drafting failure")
    monkeypatch.setattr(application, "build_initial_bioz_plan", fail)
    output = client.post("/api/research", json={"query": PROMPT}).get_json()
    assert output["responseState"] == "error" and output["errorCode"] == "PLAN_GENERATION_FAILED"
    assert output["agentRun"]["status"] == "error"
    assert output["experimentPlan"] == {} and "planUrl" not in output
    assert output["tools"][0]["status"] == "error"
    stored = client.get(f"/api/agent-runs/{output['agentRun']['runId']}").get_json()
    assert stored["error"] == "PLAN_GENERATION_FAILED"
    assert stored["state"]["stopReason"] == "tool_error"


def test_invalid_tool_output_never_becomes_a_completed_draft(client, monkeypatch):
    original = application.build_initial_bioz_plan
    def corrupt(question):
        output = original(question).model_dump()
        output["frequency_sweep"]["frequencies_hz"] = [1000]
        return output
    monkeypatch.setattr(application, "build_initial_bioz_plan", corrupt)
    output = client.post("/api/research", json={"query": PROMPT}).get_json()
    assert output["responseState"] == "error"
    assert output["experimentPlan"] == {} and "planMarkdown" not in output

