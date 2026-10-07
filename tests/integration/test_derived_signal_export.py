"""Read-only source → filter → new CSV → verified download and provenance."""

import hashlib
import io

import numpy as np
import pandas as pd
import pytest

import app as application
from flexresearch.lab_tools import build_lab_tool_registry


def test_filter_export_download_report_and_history_preserve_lineage():
    client = application.app.test_client()
    axis = np.arange(1000) / 100
    values = np.sin(2*np.pi*axis) + .2*np.sin(20*np.pi*axis)
    raw = pd.DataFrame({"time_s": axis, "ch4": values}).to_csv(index=False).encode()
    experiment = client.post("/api/experiments", json={"name": "Synthetic export validation"}).json["item"]["id"]
    uploaded = client.post("/api/analyze", data={"file": (io.BytesIO(raw), "source.csv"), "experimentId": str(experiment)}, content_type="multipart/form-data")
    assert uploaded.status_code == 200
    result = client.post("/api/research", json={"query": f"实验{experiment}通道4做0.5–3 Hz带通滤波，导出CSV并画图", "useModel": False}).json
    assert result["responseState"] == "completed"
    analysis = result["analysis"]
    derived = next(a for a in analysis["artifacts"] if a["metadata"]["format"] == "csv")
    plot = next(a for a in analysis["artifacts"] if a["metadata"]["format"] == "png")
    with client.get(derived["url"]) as download:
        assert download.status_code == 200
        assert "attachment" in download.headers["Content-Disposition"]
        exported_bytes = download.data
    exported = pd.read_csv(io.BytesIO(exported_bytes))
    expected = build_lab_tool_registry().execute("filter_signal", {"signal": values.tolist(), "sample_rate": 100, "low_cut": .5, "high_cut": 3, "order": 4}).result["filtered_signal"]
    assert np.allclose(exported.filtered_signal, expected, atol=1e-10)
    assert np.allclose(exported.time_s, axis, atol=1e-10)
    meta = derived["metadata"]
    assert meta["sha256"] == hashlib.sha256(exported_bytes).hexdigest()
    assert meta["parent_source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert meta["channel"] == "ch4" and meta["experiment_id"] == experiment
    steps = analysis["trajectory"]
    filtered = next(s for s in steps if s["tool_name"] == "filter_signal")
    export = next(s for s in steps if s["tool_name"] == "export_signal")
    assert meta["input_tool_run_id"] == filtered["tool_run_id"]
    assert any(r["tool_run_id"] == export["tool_run_id"] and r["parameters"]["sha256"] == meta["sha256"] for r in analysis["source_refs"])
    report = client.get(result["reportUrl"]).text
    assert meta["sha256"] in report and meta["parent_source_sha256"] in report
    assert derived["url"] in report and plot["url"] in report
    history = client.get(f"/api/sessions/{result['sessionId']}").json
    assert history["messages"][-1]["result"]["analysis"]["artifacts"] == analysis["artifacts"]
    originals = list(application.MEASUREMENT_DIR.glob("*.csv"))
    assert any(p.read_bytes() == raw for p in originals)
    # A changed derived file must not be served under its original provenance.
    (application.ARTIFACT_DIR / derived["file_path"]).write_text("changed", encoding="utf-8")
    assert client.get(derived["url"]).status_code == 409


def test_export_without_successful_filter_does_not_create_derived_csv(tmp_path):
    from flexresearch.agent import LabAgent
    source = tmp_path / "source.csv"
    source.write_text("time_s,signal\n" + "\n".join(f"{i/100},{i}" for i in range(100)), encoding="utf-8")
    result = LabAgent(build_lab_tool_registry()).analyze_csv(str(source), "滤波并导出CSV", output_dir=str(tmp_path / "derived"))
    assert result.status == "partial"
    assert result.artifacts == []
    assert not (tmp_path / "derived").exists()
    assert any("未导出" in text for text in result.limitations)


@pytest.mark.parametrize("failure", ["hash", "nan", "length"])
def test_export_rejects_invalid_or_changed_input_before_writing(tmp_path, failure):
    source = tmp_path / "source.csv"
    raw = b"x,y\n0,1\n1,2\n"
    source.write_bytes(raw)
    args = dict(x=[0., 1.], signal=[1., 2.], axis_name="time_s", source_file=str(source), source_sha256=hashlib.sha256(raw).hexdigest(), output_dir=str(tmp_path / "derived"), channel="ch4", input_tool_run_id="filter-test", processing_parameters={"sample_rate": 1})
    if failure == "hash":
        source.write_bytes(raw + b"2,3\n")
    elif failure == "nan":
        args["signal"] = [float("nan"), 2.]
    else:
        args["signal"] = [1., 2., 3.]
    run = build_lab_tool_registry().execute("export_signal", args)
    assert run.status == "error"
    assert run.result is None and not (tmp_path / "derived").exists()


def test_untracked_csv_is_not_exposed_by_artifact_route():
    application.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (application.ARTIFACT_DIR / "untracked.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    assert application.app.test_client().get("/artifacts/untracked.csv").status_code == 404

