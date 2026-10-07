"""Two-experiment HTTP comparison with numerical truth and source isolation."""

import hashlib
import io
import json
import math

import pytest

import app as application


def upload(client, raw, name="synthetic", metadata=None, experiment_id=None):
    if experiment_id is None:
        experiment_id = client.post("/api/experiments", json={"name": name, "metadata": metadata or {}}).json["item"]["id"]
    result = client.post("/api/analyze", data={"file": (io.BytesIO(raw), name + ".csv"), "experimentId": str(experiment_id)}, content_type="multipart/form-data")
    assert result.status_code == 200, result.json
    with application.get_db() as db:
        file_id = db.execute("SELECT id FROM experiment_files WHERE experiment_id = ? ORDER BY id DESC LIMIT 1", (experiment_id,)).fetchone()["id"]
    return experiment_id, file_id


def ask(client, query, use_model=False):
    response = client.post("/api/research", json={"query": query, "useModel": use_model})
    assert response.status_code == 200, response.json
    return response.json


BASE = b"frequency_hz,ch4_real_ohm,ch4_imag_ohm\n10,3,4\n100,6,8\n"
AFTER = b"frequency_hz,ch4_real_ohm,ch4_imag_ohm\n100,12,16\n10,6,8\n"


def test_bioz_comparison_aligns_frequency_not_row_order_and_preserves_both_sources():
    client = application.app.test_client()
    one, _ = upload(client, BASE, "baseline")
    two, _ = upload(client, AFTER, "after exercise")
    before = {path: path.read_bytes() for path in application.MEASUREMENT_DIR.glob("*.csv")}
    result = ask(client, f"比较实验{one}和实验{two}通道4的阻抗并画图")
    assert result["responseState"] == "completed"
    values = result["analysis"]["calculated_result"]["comparison"]
    assert values["mean_baseline"] == pytest.approx(7.5)
    assert values["mean_comparison"] == pytest.approx(15)
    assert values["mean_delta"] == pytest.approx(7.5)
    assert values["rmse"] == pytest.approx(math.sqrt(62.5))
    assert values["relative_change_percent"] == pytest.approx(100)
    assert result["comparisonContext"]["experiment_ids"] == [one, two]
    report = client.get(result["reportUrl"]).text
    for raw in (BASE, AFTER):
        assert hashlib.sha256(raw).hexdigest() in report
    for path, raw in before.items():
        assert path.read_bytes() == raw
    child = client.get(f"/api/agent-runs/{result['analysisRun']['runId']}").json
    comparison = next(call for call in child["toolCalls"] if call["tool_name"] == "compare_experiments")
    assert {ref["experiment_id"] for ref in comparison["source_refs"]} == {one, two}
    assert all(ref["tool_run_id"] == comparison["tool_run_id"] for ref in comparison["source_refs"])
    with client.get(result["analysis"]["artifacts"][0]["url"]) as image:
        assert image.data.startswith(b"\x89PNG")
    restored = client.get(f"/api/sessions/{result['sessionId']}").json["messages"][-1]["result"]
    assert restored["comparisonContext"] == result["comparisonContext"]


def test_comparison_converts_explicit_kohm_to_ohm_before_numeric_tools():
    client = application.app.test_client()
    one, _ = upload(client, b"frequency_hz,ch4_real_ohm,ch4_imag_ohm\n10,750,1000\n100,750,1000\n")
    two, _ = upload(client, b"frequency_khz,ch4_real_kohm,ch4_imag_kohm\n.01,1.5,2\n.1,1.5,2\n")
    result = ask(client, f"比较实验{one}和{two}通道4的阻抗")
    assert result["responseState"] == "completed"
    assert result["analysis"]["calculated_result"]["comparison"]["mean_delta"] == pytest.approx(1250)
    assert result["comparisonContext"]["unit"] == "Ω"


def test_independent_signal_samples_can_have_different_lengths_without_fake_paired_metrics():
    client = application.app.test_client()
    one, _ = upload(client, b"time_s,ch4_mV\n0,1000\n1,3000\n")
    two, _ = upload(client, b"time_s,ch4_V\n0,2\n1,4\n2,6\n")
    result = ask(client, f"比较实验{one}和实验{two}通道4的信号均值")
    assert result["responseState"] == "completed"
    values = result["analysis"]["calculated_result"]["comparison"]
    assert values["mean_baseline"] == pytest.approx(2)
    assert values["mean_comparison"] == pytest.approx(4)
    assert values["mean_delta"] == pytest.approx(2)
    assert values["baseline_count"] == 2 and values["comparison_count"] == 3
    assert values["rmse"] is None and values["correlation"] is None
    assert result["analysis"]["calculated_result"]["alignment"]["mode"] == "independent_samples"


@pytest.mark.parametrize("raw,reason", [
    (b"frequency_hz,ch4_real_ohm,ch4_imag_ohm\n10,3,4\n200,6,8\n", "频点不一致"),
    (b"frequency_hz,ch4_real_ohm,ch4_imag_ohm\n10,3,4\n10,6,8\n", "不重复"),
    (b"frequency_hz,ch4_real,ch4_imag\n10,3,4\n100,6,8\n", "没有单位"),
    (b"frequency_hz,ch4_real_V,ch4_imag_V\n10,3,4\n100,6,8\n", "电阻单位"),
    (b"frequency_hz,ch4_real_ohm,ch4_imag_ohm\n10,NaN,4\n100,6,8\n", "NaN"),
])
def test_incomparable_data_never_produce_difference_claims(raw, reason):
    client = application.app.test_client()
    one, _ = upload(client, BASE)
    two, _ = upload(client, raw)
    result = ask(client, f"比较实验{one}和实验{two}通道4的阻抗")
    assert result["responseState"] == "needs_clarification"
    assert reason in result["answer"]
    assert result["analysis"]["calculated_result"] == {} and result["sources"] == []
    assert result["analysis"]["trajectory"]
    assert client.get(result["reportUrl"]).status_code == 200


def test_metadata_units_are_accepted_but_conflicting_user_units_are_rejected():
    client = application.app.test_client()
    raw = b"frequency_hz,ch4_real,ch4_imag\n10,3,4\n100,6,8\n"
    metadata = {"units": {"ch4_real": "ohm", "ch4_imag": "ohm"}}
    one, _ = upload(client, raw, metadata=metadata)
    two, _ = upload(client, raw, metadata=metadata)
    result = ask(client, f"比较实验{one}和实验{two}通道4的阻抗")
    assert result["responseState"] == "completed"
    conflict = ask(client, f"比较实验{one}和实验{two}通道4的阻抗，单位kohm")
    assert conflict["responseState"] == "needs_clarification"
    assert "冲突" in conflict["answer"]


def test_single_channel_is_inferred_but_duplicate_experiment_names_require_clarification():
    client = application.app.test_client()
    one, _ = upload(client, BASE, "baseline")
    two, _ = upload(client, AFTER, "after exercise")
    result = ask(client, f"比较实验{one}和实验{two}阻抗")
    assert result["responseState"] == "completed"
    assert result["comparisonContext"]["channel"] == "4"
    names = ask(client, "比较 baseline 和 after exercise 通道4的阻抗")
    assert names["responseState"] == "completed"
    client.post("/api/experiments", json={"name": "baseline"})
    duplicate = ask(client, "比较 baseline 和 after exercise 通道4的阻抗")
    assert duplicate["responseState"] == "needs_clarification"
    assert "不唯一" in duplicate["answer"]


def test_multiple_channels_are_not_silently_selected_and_old_context_is_cleared():
    client = application.app.test_client()
    raw = b"frequency_hz,ch4_real_ohm,ch4_imag_ohm,ch5_real_ohm,ch5_imag_ohm\n10,3,4,6,8\n100,6,8,12,16\n"
    one, _ = upload(client, raw)
    two, _ = upload(client, raw)
    initial = ask(client, f"计算实验{one}通道4的平均阻抗")
    assert application.load_experiment_session_state(initial["sessionId"]) is not None
    compared = client.post("/api/research", json={"query": f"比较实验{one}和实验{two}的阻抗", "sessionId": initial["sessionId"], "useModel": False}).json
    assert compared["responseState"] == "needs_clarification"
    assert "多个候选通道" in compared["answer"]
    assert compared["analysis"]["calculated_result"] == {}
    assert application.load_experiment_session_state(initial["sessionId"]) is None
    followup = client.post("/api/research", json={"query": "继续分析这个实验通道4的频率", "sessionId": initial["sessionId"], "useModel": False}).json
    assert followup["errorCode"] == "experiment_context_required"
    assert followup["tools"] == []


def test_file_selection_is_bound_to_each_experiment_and_baseline_is_explicit():
    client = application.app.test_client()
    one, file_one = upload(client, BASE)
    two, file_two = upload(client, AFTER)
    upload(client, AFTER, experiment_id=one)
    ambiguous = ask(client, f"比较实验{one}和实验{two}通道4的阻抗")
    assert ambiguous["responseState"] == "needs_clarification"
    selected = ask(client, f"比较实验{one}文件{file_one}和实验{two}文件{file_two}通道4的阻抗，以实验{two}为基线")
    assert selected["responseState"] == "completed"
    assert selected["comparisonContext"]["experiment_ids"] == [two, one]
    assert selected["analysis"]["calculated_result"]["comparison"]["mean_delta"] == pytest.approx(-7.5)


def test_comparison_model_loop_selects_tool_and_only_observes_private_status(monkeypatch):
    client = application.app.test_client()
    one, _ = upload(client, BASE, "private-baseline")
    two, _ = upload(client, AFTER, "private-after")
    turns = []
    monkeypatch.setattr(application, "model_configuration", lambda: {"configured": True, "apiKey": "test-secret", "baseUrl": "https://provider.invalid/v1", "model": "mock/comparison"})
    def model(_url, *, headers, payload):
        turns.append(payload)
        assert payload["tools"][0]["function"]["name"] == "compare_stored_experiments"
        if len(turns) == 1:
            message = {"tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "compare_stored_experiments", "arguments": json.dumps({"experiment_id_1": one, "experiment_id_2": two, "channel": 4})}}]}
        else:
            observation = json.loads(payload["messages"][-1]["content"])
            assert "calculatedResult" not in observation
            assert observation["analysisStatus"] == "complete"
            message = {"content": json.dumps({"tool_run_id": observation["toolRunId"]})}
        return {"model": "mock/comparison", "choices": [{"message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}], "usage": {"total_tokens": 20, "prompt_tokens": 10, "completion_tokens": 10, "cost": 0}}, 1
    monkeypatch.setattr(application, "request_model_json", model)
    result = ask(client, f"比较实验{one}和实验{two}通道4的阻抗", use_model=True)
    assert result["responseState"] == "completed"
    assert len(turns) == 2
    assert "private-baseline" not in json.dumps(turns)
    assert result["analysis"]["calculated_result"]["comparison"]["mean_delta"] == pytest.approx(7.5)
    run = client.get(f"/api/agent-runs/{result['agentRun']['runId']}").json
    assert run["state"]["selectionValidated"] is True and run["token_usage"]["totalTokens"] == 40

