"""Real HTTP pulse request, explicit processing, provenance and artifacts."""

import hashlib
import io
import json
import re

import pytest

import app as application
from flexresearch.report_review import review_report_content
from scripts.run_agent_eval import pulse_csv


PROMPT = "分析主要脉搏频率并画图。"
BAND = {"low_cut": .5, "high_cut": 3, "order": 4}


def upload(client, *, prompt=PROMPT, band=BAND, raw=None):
    raw = raw if raw is not None else pulse_csv(column="ch4")
    data = {"question": prompt, "file": (io.BytesIO(raw), "SYNTHETIC-pulse.csv"), "sampleRate": "100", "bindContext": "true"}
    if band is not None:
        data["filterParameters"] = json.dumps(band)
    return client.post("/api/analyze", data=data, content_type="multipart/form-data")


def test_pulse_original_request_full_http_contract():
    client = application.app.test_client()
    raw = pulse_csv(column="ch4")
    digest = hashlib.sha256(raw).hexdigest()
    response = upload(client, raw=raw)
    assert response.status_code == 200
    body = response.json
    assert body["responseState"] == "completed"
    result = body["agent"]
    assert [s["tool_name"] for s in result["trajectory"]] == ["load_experiment_data", "load_csv", "filter_signal", "spectral_analysis", "plot_signal"]
    spectrum = result["calculated_result"]["spectrum"]
    assert spectrum["dominant_frequency_hz"] == pytest.approx(1.2)
    assert spectrum["pulse_rate_bpm"] == pytest.approx(72)
    assert "72 BPM" in body["answer"] and "不等同于已验证心率" in body["answer"]
    plot, = result["artifacts"]
    with client.get(plot["url"]) as download:
        assert download.status_code == 200 and download.mimetype == "image/png"
        assert download.data.startswith(b"\x89PNG")
        assert plot["metadata"]["sha256"] == hashlib.sha256(download.data).hexdigest()
    assert plot["metadata"]["parent_source_sha256"] == digest
    assert plot["metadata"]["algorithm_version"] == "matplotlib-line-v1"
    assert all(r["source_sha256"] == digest for r in result["source_refs"])
    filter_step = next(s for s in result["trajectory"] if s["tool_name"] == "filter_signal")
    spectral_step = next(s for s in result["trajectory"] if s["tool_name"] == "spectral_analysis")
    ref = next(r for r in result["source_refs"] if r["tool_run_id"] == spectral_step["tool_run_id"])
    assert ref["parameters"]["input_tool_run_id"] == filter_step["tool_run_id"]
    assert ref["parameters"]["pulse_rate_method"] == spectrum["pulse_rate_method"]
    assert any(p.read_bytes() == raw for p in application.MEASUREMENT_DIR.glob("*.csv"))
    run_id = body["agentRun"]["runId"]
    saved = client.get(f"/api/agent-runs/{run_id}").json
    assert saved["query"] == PROMPT and saved["final_result"] == result
    report = client.get(f"/api/agent-runs/{run_id}/report.md").text
    assert "脉率候选为 72 BPM" in report and spectrum["pulse_rate_method"] in report
    assert digest in report and plot["url"] in report
    # A Hz claim alone must not satisfy completeness of the separate BPM claim.
    missing_rate = re.sub(r"[^\n]*脉率候选为[^\n]*", "", report)
    review = review_report_content(missing_rate, [result])
    assert next(x.status for x in review.criteria if x.name == "result_explanation_completeness") == "fail"
    history = client.get(f"/api/sessions/{body['sessionId']}").json
    assert history["messages"][-2]["content"] == PROMPT
    assert history["messages"][-1]["result"]["agent"] == result


@pytest.mark.parametrize("prompt,band", [(PROMPT, {"low_cut": 3, "high_cut": .5}), ("分析原始信号脉搏频率", BAND), ("用1–4Hz带通分析脉搏频率", BAND), (PROMPT, {**BAND, "unexpected": 1})])
def test_invalid_or_conflicting_explicit_filter_is_rejected_before_archive(prompt, band):
    response = upload(application.app.test_client(), prompt=prompt, band=band)
    assert response.status_code == 400
    assert not list(application.MEASUREMENT_DIR.glob("*.csv"))


def test_unconfigured_pulse_request_does_not_invent_filter():
    body = upload(application.app.test_client(), band=None).json
    assert "filter_signal" not in [s["tool_name"] for s in body["agent"]["trajectory"]]
    assert body["agent"]["calculated_result"]["spectrum"]["pulse_rate_bpm"] == pytest.approx(72)


def test_missing_sample_rate_cannot_create_a_rate_claim():
    client = application.app.test_client()
    raw = b"ch4\n" + b"1\n2\n"*50
    body = client.post("/api/analyze", data={"question": PROMPT, "file": (io.BytesIO(raw), "missing.csv"), "bindContext": "true"}, content_type="multipart/form-data").json
    assert body["responseState"] == "needs_clarification"
    assert "spectrum" not in body["agent"]["calculated_result"]
    assert "BPM" not in body["answer"]

