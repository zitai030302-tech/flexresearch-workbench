"""Scientific ground truth through stored experiment IDs and persistent sessions."""

import hashlib
import io
import math
import json

import pytest

import app as application


def upload(client, raw, *, name="pulse", experiment_id=None):
    if experiment_id is None:
        experiment_id = client.post("/api/experiments", json={"name": name}).json["item"]["id"]
    result = client.post("/api/analyze", data={"file": (io.BytesIO(raw), name + ".csv"), "experimentId": str(experiment_id)}, content_type="multipart/form-data")
    assert result.status_code == 200
    return experiment_id


def pulse_csv(time_column=False):
    rows = [("time_s," if time_column else "") + "ch4,ch14"]
    for i in range(1000):
        rows.append((f"{i/100}," if time_column else "") + f"{math.sin(2*math.pi*1.2*i/100)},{math.sin(2*math.pi*2.4*i/100)}")
    return "\n".join(rows).encode()


def ask(client, query, session_id=None):
    response = client.post("/api/research", json={"query": query, "sessionId": session_id, "useModel": False})
    assert response.status_code == 200
    return response.json


def test_experiment_channel_fft_and_plot_has_ground_truth_and_exact_lineage():
    client = application.app.test_client()
    original = pulse_csv(time_column=True)
    experiment_id = upload(client, original)
    result = ask(client, f"分析实验 {experiment_id} 通道 4 的主要脉搏频率并画图")
    assert result["responseState"] == "completed"
    assert result["analysis"]["calculated_result"]["spectrum"]["dominant_frequency_hz"] == pytest.approx(1.2, abs=.01)
    assert "1.2 Hz" in result["answer"]
    assert result["experimentContext"]["channel"] == "4"
    assert result["experimentContext"]["sample_rate"] == pytest.approx(100)
    with client.get(result["analysis"]["artifacts"][0]["url"]) as image:
        assert image.status_code == 200
        assert image.data.startswith(b"\x89PNG")
    report = client.get(result["reportUrl"])
    assert hashlib.sha256(original).hexdigest() in report.text
    run = client.get(f"/api/agent-runs/{result['analysisRun']['runId']}").json
    for call in run["toolCalls"]:
        assert all(ref["tool_run_id"] == call["tool_run_id"] for ref in call["source_refs"])


def test_missing_rate_can_be_supplied_next_turn_and_persists_per_session():
    client = application.app.test_client()
    experiment_id = upload(client, pulse_csv())
    first = ask(client, f"分析实验 {experiment_id} 通道4的主要频率")
    assert first["responseState"] == "needs_clarification"
    assert "spectrum" not in first["analysis"]["calculated_result"]
    second = ask(client, "继续用100 Hz采样率分析通道4的主要频率", first["sessionId"])
    assert second["responseState"] == "completed"
    assert second["analysis"]["calculated_result"]["spectrum"]["dominant_frequency_hz"] == pytest.approx(1.2, abs=.01)
    third = ask(client, "继续分析这个实验通道14的主要频率", first["sessionId"])
    assert third["analysis"]["calculated_result"]["spectrum"]["dominant_frequency_hz"] == pytest.approx(2.4, abs=.01)
    fresh_session = client.post("/api/sessions", json={"title": "isolated"}).json["item"]["id"]
    assert application.load_experiment_session_state(fresh_session) is None


def test_switching_experiments_does_not_reuse_previous_rate():
    client = application.app.test_client()
    one = upload(client, pulse_csv(), name="first")
    two = upload(client, pulse_csv(), name="second")
    first = ask(client, f"实验{one} 通道4 采样率100Hz，分析主峰")
    second = ask(client, f"实验{two} 通道4，分析主峰", first["sessionId"])
    assert second["responseState"] == "needs_clarification"
    assert second["experimentContext"]["sample_rate"] is None
    assert "spectrum" not in second["analysis"]["calculated_result"]


def test_bioz_mean_uses_only_requested_channel():
    client = application.app.test_client()
    experiment_id = upload(client, b"frequency_hz,ch1_real,ch1_imag,ch4_real,ch4_imag\n10,60,80,3,4\n100,60,80,3,4\n")
    result = ask(client, f"计算实验{experiment_id}通道4的平均阻抗")
    assert result["responseState"] == "completed"
    assert result["analysis"]["calculated_result"]["bioz"]["magnitude_mean_ohm"] == pytest.approx(5)
    assert result["analysis"]["calculated_result"]["bioz"]["channel"] == "ch4"
    assert "100 Ω" not in result["answer"]


def test_ambiguous_file_and_invalid_channel_request_clarification():
    client = application.app.test_client()
    experiment_id = upload(client, pulse_csv(), name="one")
    invalid = ask(client, f"分析实验{experiment_id}通道99的平均值")
    assert invalid["responseState"] == "needs_clarification"
    assert invalid["analysis"]["calculated_result"] == {}
    upload(client, pulse_csv(), name="two", experiment_id=experiment_id)
    ambiguous = ask(client, f"分析实验{experiment_id}通道4的平均值")
    assert ambiguous["responseState"] == "needs_clarification"
    assert "多个 CSV" in ambiguous["answer"]


def test_corrupted_archived_bytes_are_not_analyzed():
    client = application.app.test_client()
    experiment_id = upload(client, pulse_csv())
    path = next(application.MEASUREMENT_DIR.glob("*.csv"))
    path.write_bytes(b"ch4\n99\n99\n")
    result = ask(client, f"计算实验{experiment_id}通道4的平均值")
    assert result["responseState"] == "needs_clarification"
    assert "SHA-256" in result["answer"]
    assert "analysis" not in result


def test_invalid_sample_rate_is_a_clarification_not_http500():
    client = application.app.test_client()
    experiment_id = upload(client, pulse_csv())
    result = ask(client, f"实验{experiment_id}通道4，采样率0Hz，分析主峰")
    assert result["responseState"] == "needs_clarification"
    assert result["errorCode"] == "invalid_analysis_arguments"


@pytest.mark.parametrize("rate", ["-100Hz", "abc", "100kHz", "NaNHz"])
def test_invalid_new_rate_never_silently_reuses_old_rate(rate):
    client = application.app.test_client()
    experiment_id = upload(client, pulse_csv())
    first = ask(client, f"实验{experiment_id} 通道4 采样率100Hz，分析主峰")
    bad = ask(client, f"继续分析通道4主峰，采样率{rate}", first["sessionId"])
    assert bad["responseState"] == "needs_clarification"
    assert bad["errorCode"] == "invalid_analysis_arguments"
    assert "analysis" not in bad


def test_multiple_channels_require_selection_before_scientific_analysis():
    client = application.app.test_client()
    experiment_id = upload(client, pulse_csv(time_column=True))
    result = ask(client, f"分析实验{experiment_id}的主要频率")
    assert result["responseState"] == "needs_clarification"
    assert "多个数值通道" in result["answer"]
    assert result["analysis"]["calculated_result"] == {}


def fake_science_provider(monkeypatch, experiment_id, *, invalid_final=False, repair=False):
    monkeypatch.setattr(application, "model_configuration", lambda: {"configured": True, "apiKey": "fixture-secret", "baseUrl": "https://example.invalid/v1", "model": "fixture/requested"})
    turns = []
    def call(_url, *, headers, payload):
        turns.append(payload)
        assert [schema["function"]["name"] for schema in payload["tools"]] == ["analyze_experiment"]
        if len(turns) == 1 or repair and len(turns) == 2:
            arguments = json.loads(payload["messages"][0]["content"].split("Confirmed scope: ", 1)[1])
            arguments["experiment_id"] = experiment_id + 1 if repair and len(turns) == 1 else experiment_id
            message = {"tool_calls": [{"id": "model-call", "type": "function", "function": {"name": "analyze_experiment", "arguments": json.dumps(arguments)}}]}
        else:
            observation = json.loads(payload["messages"][-1]["content"])
            message = {"content": "频率是999Hz，患者存在疾病。" if invalid_final else json.dumps({"tool_run_id": observation["toolRunId"]})}
        return {"model": "fixture/actual", "choices": [{"message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0}}, 1
    monkeypatch.setattr(application, "request_model_json", call)
    return turns


def test_scientific_model_loop_computes_locally_without_disclosing_raw_data(monkeypatch):
    client = application.app.test_client()
    experiment_id = upload(client, pulse_csv(), name="private-patient-name")
    turns = fake_science_provider(monkeypatch, experiment_id)
    result = client.post("/api/research", json={"query": f"分析实验{experiment_id}通道4，采样率100Hz，找主峰并画图", "useModel": True}).json
    assert result["responseState"] == "completed"
    assert result["analysis"]["calculated_result"]["spectrum"]["dominant_frequency_hz"] == pytest.approx(1.2)
    assert len(turns) == 2
    schema = turns[0]["tools"][0]["function"]["parameters"]
    assert set(schema["required"]) == set(schema["properties"])
    assert '"$ref"' not in json.dumps(schema)
    observation = json.loads(turns[1]["messages"][-1]["content"])
    assert observation["analysisStatus"] == "complete"
    assert observation["resultPrivacy"] == "local_only"
    assert "calculatedResult" not in observation
    assert "private-patient-name" not in json.dumps(turns)
    assert "source_sha256" not in json.dumps(turns)
    run = client.get(f"/api/agent-runs/{result['agentRun']['runId']}").json
    assert run["model"]["actualModel"] == "fixture/actual"
    assert run["token_usage"]["totalTokens"] == 30
    assert run["state"]["selectionValidated"] is True
    assert run["state"]["childAnalysisRunId"] == result["analysisRun"]["runId"]


def test_explicit_opt_in_sends_only_numeric_summary_to_science_model(monkeypatch):
    client = application.app.test_client()
    experiment_id = upload(client, pulse_csv(), name="private-patient-name")
    turns = fake_science_provider(monkeypatch, experiment_id)
    result = client.post("/api/research", json={"query": f"分析实验{experiment_id}通道4，采样率100Hz，找主峰", "useModel": True, "allowPrivateContext": True}).json
    assert result["responseState"] == "completed"
    observation = json.loads(turns[1]["messages"][-1]["content"])
    assert observation["calculatedResult"]["spectrum"]["dominant_frequency_hz"] == pytest.approx(1.2)
    assert "private-patient-name" not in json.dumps(turns)
    assert "frequency_hz" not in observation["calculatedResult"]["spectrum"]


def test_model_cannot_invent_scientific_results_or_medical_conclusions(monkeypatch):
    client = application.app.test_client()
    experiment_id = upload(client, pulse_csv())
    fake_science_provider(monkeypatch, experiment_id, invalid_final=True)
    result = client.post("/api/research", json={"query": f"分析实验{experiment_id}通道4，采样率100Hz，找主峰", "useModel": True}).json
    assert result["responseState"] == "partial"
    assert result["errorCode"] == "model_orchestration_incomplete"
    assert "999" not in result["answer"] and "疾病" not in result["answer"]
    assert "1.2 Hz" in result["answer"]


def test_model_wrong_experiment_is_rejected_and_can_repair(monkeypatch):
    client = application.app.test_client()
    experiment_id = upload(client, pulse_csv())
    turns = fake_science_provider(monkeypatch, experiment_id, repair=True)
    result = client.post("/api/research", json={"query": f"分析实验{experiment_id}通道4，采样率100Hz，找主峰", "useModel": True}).json
    assert result["responseState"] == "completed"
    assert len(turns) == 3
    assert [step["status"] for step in result["tools"]] == ["error", "complete"]
    assert "confirmed user scope" in result["tools"][0]["error"]
    assert json.loads(turns[1]["messages"][-1]["content"])["errorCode"] == "ValueError"
    repair = json.loads(turns[1]["messages"][-1]["content"])
    assert repair["confirmedArguments"]["experiment_id"] == experiment_id
    assert repair["confirmedArguments"]["channel"] == "4"
    assert "calculatedResult" not in repair


def test_model_timeout_preserves_explicit_local_science_fallback(monkeypatch):
    client = application.app.test_client()
    experiment_id = upload(client, pulse_csv())
    fake_science_provider(monkeypatch, experiment_id)
    def unavailable(*args, **kwargs):
        raise TimeoutError("private connection detail")
    monkeypatch.setattr(application, "request_model_json", unavailable)
    result = client.post("/api/research", json={"query": f"分析实验{experiment_id}通道4，采样率100Hz，找主峰", "useModel": True}).json
    assert result["responseState"] == "partial"
    assert "Python" in result["answer"] and "1.2 Hz" in result["answer"]
    assert "private connection detail" not in json.dumps(result)
    run = client.get(f"/api/agent-runs/{result['agentRun']['runId']}").json
    assert run["state"]["fallbackToolSteps"] == 1
    assert run["state"]["stop_reason"] == "model_error"
    assert run["token_usage"]["totalTokens"] is None


def test_channel_integer_from_live_provider_is_losslessly_normalized():
    value = application.AnalyzeExperimentInput(experiment_id=1, channel=4)
    assert value.channel == "4"
    for invalid in (4.5, True, -4, [4]):
        with pytest.raises(ValueError):
            application.AnalyzeExperimentInput(experiment_id=1, channel=invalid)


def test_history_restores_each_analysis_without_attaching_it_to_greetings():
    client = application.app.test_client()
    experiment_id = upload(client, pulse_csv(time_column=True))
    first = ask(client, f"实验{experiment_id}通道4，分析主要频率并画图")
    second = ask(client, "继续分析这个实验通道14的主要频率并画图", first["sessionId"])
    ask(client, "你好", first["sessionId"])
    messages = client.get(f"/api/sessions/{first['sessionId']}").json["messages"]
    assistants = [message for message in messages if message["role"] == "assistant"]
    assert assistants[0]["result"]["analysis"]["calculated_result"]["spectrum"]["dominant_frequency_hz"] == pytest.approx(1.2)
    assert assistants[1]["result"]["analysis"]["calculated_result"]["spectrum"]["dominant_frequency_hz"] == pytest.approx(2.4)
    assert assistants[0]["result"]["reportUrl"] == first["reportUrl"]
    assert assistants[1]["result"]["reportUrl"] == second["reportUrl"]
    assert assistants[2]["result"] == {"contextKind": "ordinary_chat_v1", "contextEligible": True}
    assert "result_json" not in assistants[0]


def test_upload_analysis_artifacts_survive_session_reload():
    client = application.app.test_client()
    response = client.post("/api/analyze", data={"file": (io.BytesIO(b"time_s,signal\n0,1\n1,2\n2,3\n"), "synthetic.csv"), "question": "画图"}, content_type="multipart/form-data")
    assert response.status_code == 200
    result = response.json
    messages = client.get(f"/api/sessions/{result['sessionId']}").json["messages"]
    restored = messages[-1]["result"]
    assert restored["agent"]["artifacts"][0]["url"] == result["agent"]["artifacts"][0]["url"]
    assert restored["agentRun"]["runId"] == result["agentRun"]["runId"]

