"""HTTP-level checks for the unified chat CSV → Agent → artifact workflow."""

from __future__ import annotations

import io
import json
import math

import app as app_module
from app import app


def pulse_csv(frequency_hz: float = 1.2, sample_rate: float = 100.0, points: int = 1000) -> bytes:
    rows = ["time_s,signal"]
    rows.extend(f"{index / sample_rate},{math.sin(2 * math.pi * frequency_hz * index / sample_rate)}" for index in range(points))
    return ("\n".join(rows) + "\n").encode()


def test_upload_runs_typed_tools_persists_trajectory_and_serves_plot():
    response = app.test_client().post(
        "/api/analyze",
        data={
            "question": "请做 0.5-3 Hz 带通滤波，找 FFT 主峰并画图",
            "file": (io.BytesIO(pulse_csv()), "pulse.csv"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    payload = response.json
    assert payload["sessionId"]
    assert payload["agent"]["status"] == "complete"
    assert [item["tool_name"] for item in payload["agent"]["trajectory"]] == ["load_csv", "filter_signal", "spectral_analysis", "plot_signal"]
    assert abs(payload["agent"]["calculated_result"]["spectrum"]["dominant_frequency_hz"] - 1.2) <= 0.05
    assert all({"source_file", "timestamp", "processing_method", "parameters", "tool_run_id"} <= set(item) for item in payload["agent"]["source_refs"])

    run = app.test_client().get(f"/api/agent-runs/{payload['agentRun']['runId']}")
    assert run.status_code == 200
    assert len(run.json["toolCalls"]) == 4
    assert run.json["model"]["provider"] == "deterministic-python"
    assert run.json["token_usage"] == {"promptTokens": 0, "completionTokens": 0}

    with app.test_client().get(payload["agent"]["artifacts"][0]["url"]) as artifact:
        assert artifact.status_code == 200
        assert artifact.mimetype == "image/png"

    report = app.test_client().get(f"/api/agent-runs/{payload['agentRun']['runId']}/report.md")
    assert report.status_code == 200
    assert all(
        section in report.text
        for section in (
            "Experiment Metadata",
            "Data Quality",
            "Processing Methods",
            "Figures & Derived Artifacts",
            "Measured Result",
            "Calculated Result",
            "Agent Interpretation",
            "Limitations",
            "Source & Provenance",
        )
    )
    assert "SHA-256" in report.text
    assert "immutable source CSV was not overwritten" in report.text


def test_agent_log_compacts_signal_arrays_instead_of_copying_raw_series():
    response = app.test_client().post(
        "/api/analyze",
        data={"question": "找主要频率", "sampleRate": "100", "file": (io.BytesIO(pulse_csv(points=500)), "signal.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    record = json.loads((app_module.LOG_DIR / "agent-runs.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    load_step = record["trajectory"][0]
    assert "data" not in load_step["resultSummary"]
    spectrum_step = record["trajectory"][1]
    assert spectrum_step["arguments"]["signal"]["valueCount"] == 500


def test_private_vault_is_not_exposed_by_demo_data_route():
    assert app.test_client().get("/data/flexresearch.db").status_code == 404
    with app.test_client().get("/data/demo_strain_sensor.csv") as response:
        assert response.status_code == 200


def test_sqlite_foreign_keys_are_enforced_for_every_connection():
    with app_module.get_db() as db:
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_experiment_state_links_immutable_csv_and_agent_provenance():
    client = app.test_client()
    project = client.post("/api/projects", json={"name": "Bio-Z Array", "track": "医疗与仿生"}).json["item"]
    experiment = client.post("/api/experiments", json={"name": "24ch baseline", "projectId": project["id"], "metadata": {"sampleRate": 100, "channels": 24}})
    assert experiment.status_code == 201
    experiment_id = experiment.json["item"]["id"]
    analyzed = client.post(
        "/api/analyze",
        data={"experimentId": str(experiment_id), "question": "找主要脉搏频率", "sampleRate": "100", "file": (io.BytesIO(pulse_csv(points=200)), "baseline.csv")},
        content_type="multipart/form-data",
    )
    assert analyzed.status_code == 200
    assert all(ref["experiment_id"] == experiment_id for ref in analyzed.json["agent"]["source_refs"])
    detail = client.get(f"/api/experiments/{experiment_id}").json
    assert detail["item"]["metadata"] == {"sampleRate": 100, "channels": 24}
    assert detail["files"][0]["immutable"] == 1
    assert detail["files"][0]["source_path"].endswith("baseline.csv")

