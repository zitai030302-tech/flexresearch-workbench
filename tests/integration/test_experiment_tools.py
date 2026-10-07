"""Integration checks for experiment-id lookup and read-only data loading."""

from __future__ import annotations

import io

from app import app


def create_experiment_three(client) -> int:
    ids = []
    for index in range(1, 4):
        response = client.post(
            "/api/experiments",
            json={"name": f"Bio-Z run {index:03d}", "metadata": {"sampleRateHz": 100, "channelCount": 24}},
        )
        assert response.status_code == 201
        ids.append(response.json["item"]["id"])
    assert ids[-1] == 3
    return ids[-1]


def test_chat_resolves_experiment_id_and_profiles_immutable_csv():
    client = app.test_client()
    experiment_id = create_experiment_three(client)
    raw = b"frequency_hz,ch4_real,ch4_imag\n10,100,100\n100,100,100\n"
    upload = client.post(
        "/api/analyze",
        data={
            "experimentId": str(experiment_id),
            "question": "读取并概览",
            "file": (io.BytesIO(raw), "experiment_003.csv"),
        },
        content_type="multipart/form-data",
    )
    assert upload.status_code == 200

    response = client.post("/api/research", json={"query": "读取实验 003。", "useModel": True, "useOpenAlex": True})

    assert response.status_code == 200
    payload = response.json
    assert payload["responseState"] == "completed"
    assert [step["tool"] for step in payload["tools"]] == ["search_experiment", "load_experiment_data"]
    assert payload["tools"][0]["arguments"]["experiment_id"] == 3
    loaded = payload["experimentData"]
    assert loaded["experiment"]["experiment_id"] == 3
    assert loaded["raw_data_modified"] is False
    assert loaded["files"][0]["source_file"].endswith("experiment_003.csv")
    assert loaded["files"][0]["shape"] == [2, 3]
    assert loaded["files"][0]["columns"] == ["frequency_hz", "ch4_real", "ch4_imag"]
    assert len(loaded["files"][0]["sha256"]) == 64
    assert loaded["files"][0]["immutable"] is True

    run = client.get(f"/api/agent-runs/{payload['agentRun']['runId']}")
    assert run.status_code == 200
    assert [item["tool_name"] for item in run.json["toolCalls"]] == ["search_experiment", "load_experiment_data"]
    assert run.json["model"]["provider"] == "deterministic-python"


def test_missing_experiment_requests_correction_without_numeric_claims():
    client = app.test_client()

    response = client.post("/api/research", json={"query": "读取实验 999。", "useModel": True, "useOpenAlex": True})

    assert response.status_code == 200
    payload = response.json
    assert payload["responseState"] == "needs_clarification"
    assert payload["errorCode"] == "EXPERIMENT_NOT_FOUND"
    assert [step["tool"] for step in payload["tools"]] == ["search_experiment"]
    assert "不会猜测" in payload["answer"]
    assert payload["sources"] == []


def test_application_tool_schema_includes_experiment_tools():
    response = app.test_client().get("/api/tools")
    assert response.status_code == 200
    names = {item["function"]["name"] for item in response.json["items"]}
    assert {"search_experiment", "load_experiment_data", "search_knowledge_base"} <= names

