"""Cross-turn filter settings must retain scope and exact numeric lineage."""

import hashlib
import io

import numpy as np
import pandas as pd
import pytest

import app as application
from flexresearch.analysis_parameters import parse_filter_parameters


def ask(client, query, session=None):
    response = client.post("/api/research", json={"query": query, "sessionId": session, "useModel": False})
    assert response.status_code == 200
    return response.json


def setup(client):
    axis = np.arange(1000) / 100
    raw = pd.DataFrame({"time_s": axis, "ch4": np.sin(2*np.pi*1.2*axis) + .3*np.sin(2*np.pi*12*axis)}).to_csv(index=False).encode()
    upload = client.post("/api/analyze", data={"file": (io.BytesIO(raw), "source.csv"), "bindContext": "true", "question": "通道4做0.5–3 Hz带通滤波"}, content_type="multipart/form-data")
    assert upload.status_code == 200
    return raw, upload.json


def step(result, name):
    return next(item for item in result["analysis"]["trajectory"] if item["tool_name"] == name)


def test_reuse_filters_original_once_and_binds_every_downstream_tool(monkeypatch):
    client = application.app.test_client()
    raw, first = setup(client)
    captured = {}
    original_registry = application.build_lab_tool_registry
    def recording_registry():
        registry = original_registry()
        original_execute = registry.execute
        def execute(name, arguments):
            captured[name] = arguments
            return original_execute(name, arguments)
        registry.execute = execute
        return registry
    monkeypatch.setattr(application, "build_lab_tool_registry", recording_registry)
    context = application.load_experiment_session_state(first["sessionId"])
    assert context.analysis_parameters.filter.low_cut == .5
    result = ask(client, "沿用刚才的滤波参数，分析主峰、导出CSV并画图", first["sessionId"])
    assert result["responseState"] == "completed"
    params = result["experimentContext"]["analysis_parameters"]
    assert params["parameter_source_run_id"] == first["agentRun"]["runId"]
    assert params["filter"] == {"low_cut": .5, "high_cut": 3., "order": 4}
    load, filtered, fft = (step(result, name) for name in ("load_csv", "filter_signal", "spectral_analysis"))
    values = pd.read_csv(io.BytesIO(raw)).ch4.to_numpy()
    assert np.allclose(captured["filter_signal"]["signal"], values)
    expected = original_registry().execute("filter_signal", {"signal": values.tolist(), "sample_rate": 100, "low_cut": .5, "high_cut": 3}).result["filtered_signal"]
    assert np.allclose(captured["spectral_analysis"]["signal"], expected, atol=1e-10)
    assert result["analysis"]["calculated_result"]["spectrum"]["dominant_frequency_hz"] == pytest.approx(1.2)
    refs = {ref["tool_run_id"]: ref for ref in result["analysis"]["source_refs"]}
    assert refs[filtered["tool_run_id"]]["parameters"]["input_tool_run_id"] == load["tool_run_id"]
    for name in ("spectral_analysis", "plot_signal", "export_signal"):
        assert refs[step(result, name)["tool_run_id"]]["parameters"]["input_tool_run_id"] == filtered["tool_run_id"]
    assert all(ref["source_sha256"] == hashlib.sha256(raw).hexdigest() for ref in refs.values())
    assert any(path.read_bytes() == raw for path in application.MEASUREMENT_DIR.glob("*.csv"))
    restored = client.get(f"/api/sessions/{first['sessionId']}").json
    assert restored["messages"][-1]["result"]["experimentContext"]["analysis_parameters"] == params
    assert first["agentRun"]["runId"] in client.get(result["reportUrl"]).text


def test_explicit_replacement_wins_and_is_saved():
    client = application.app.test_client()
    _, first = setup(client)
    result = ask(client, "继续滤波，改为0.8–2 Hz带通，2阶并画图", first["sessionId"])
    assert result["responseState"] == "completed"
    assert result["experimentContext"]["analysis_parameters"] == {"filter": {"low_cut": .8, "high_cut": 2., "order": 2}, "parameter_source_run_id": None}


@pytest.mark.parametrize("query", ["继续画原始信号，不滤波", "继续画图"])
def test_raw_or_unqualified_request_does_not_implicitly_filter(query):
    client = application.app.test_client()
    _, first = setup(client)
    result = ask(client, query, first["sessionId"])
    assert result["responseState"] == "completed"
    assert not any(s["tool_name"] == "filter_signal" for s in result["analysis"]["trajectory"])
    assert step(result, "plot_signal")["status"] == "complete"
    assert result["experimentContext"]["analysis_parameters"]["filter"] is None


@pytest.mark.parametrize("query", ["继续滤波，改为abc Hz低通并画图", "继续滤波，改为3–0.5 Hz带通", "继续滤波，改为-1–3 Hz带通"])
def test_invalid_replacement_never_falls_back_to_old_band(query):
    client = application.app.test_client()
    _, first = setup(client)
    result = ask(client, query, first["sessionId"])
    assert result["responseState"] == "needs_clarification"
    assert "analysis" not in result


def test_reused_band_is_revalidated_against_new_rate_before_fft_or_plot():
    client = application.app.test_client()
    _, first = setup(client)
    result = ask(client, "沿用刚才的滤波参数，采样率4Hz，分析主峰并画图", first["sessionId"])
    assert result["responseState"] == "needs_clarification"
    assert step(result, "filter_signal")["status"] == "error"
    # CSV profiling already succeeded; no failed filtering/FFT output may appear.
    assert set(result["analysis"]["calculated_result"]) == {"basic_stats"}
    assert result["analysis"]["calculated_result"]["basic_stats"]["ch4"]["count"] == 1000
    assert result["analysis"]["artifacts"] == []
    assert not any(s["tool_name"] == "spectral_analysis" for s in result["analysis"]["trajectory"])


def test_new_file_or_session_cannot_reuse_previous_file_parameters():
    client = application.app.test_client()
    raw, first = setup(client)
    experiment = first["experimentContext"]["experiment_id"]
    other = client.post("/api/analyze", data={"file": (io.BytesIO(raw), "different.csv"), "experimentId": str(experiment)}, content_type="multipart/form-data").json
    file_id = other["experimentContext"]["file_id"]
    result = ask(client, f"实验{experiment}文件{file_id}沿用刚才的滤波参数并画图", first["sessionId"])
    assert result["responseState"] == "needs_clarification" and "analysis" not in result
    fresh = ask(client, f"实验{experiment}文件{first['experimentContext']['file_id']}沿用刚才的滤波参数并画图")
    assert fresh["responseState"] == "needs_clarification" and "analysis" not in fresh


@pytest.mark.parametrize("query, expected", [("采样率100Hz，3Hz低通滤波", (None, 3)), ("100 Hz采样率，低通滤波3Hz", (None, 3)), ("采样率100Hz，高通滤波0.5Hz", (.5, None)), ("采样率100Hz，低通滤波", None)])
def test_sampling_rate_is_not_mistaken_for_filter_cutoff(query, expected):
    params = parse_filter_parameters(query)
    assert ((params.low_cut, params.high_cut) if params else None) == expected

