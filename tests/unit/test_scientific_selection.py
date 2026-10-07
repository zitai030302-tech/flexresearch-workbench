"""A confirmed analysis cannot be satisfied by text without a tool result."""

import app as application
from flexresearch.experiment_tools import AnalyzeExperimentInput
from flexresearch.science_agent import run_science_loop


def test_provider_requires_initial_science_tool_then_allows_final_selection(monkeypatch):
    payloads = []
    def request(_endpoint, *, headers, payload):
        payloads.append(payload)
        return {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}], "usage": {}}, 1
    monkeypatch.setattr(application, "request_model_json", request)
    config = {"configured": True, "apiKey": "test-only", "baseUrl": "https://provider.invalid/v1", "model": "fixture/model"}
    schema = [{"type": "function", "function": {"name": "analyze_experiment"}}]
    initial = [{"role": "user", "content": "分析实验3"}]
    application.scientific_model_client(config, [], initial, schema)
    application.scientific_model_client(config, [], initial + [{"role": "tool", "tool_call_id": "test", "content": "completed"}], schema)
    assert payloads[0]["tool_choice"] == {"type": "function", "function": {"name": "analyze_experiment"}}
    assert payloads[1]["tool_choice"] == "auto"
    assert all(payload["parallel_tool_calls"] is False for payload in payloads)


def test_provider_ignoring_required_tool_is_partial_not_completed():
    def forbidden(_):
        raise AssertionError("no tool was called")
    result, selected, valid = run_science_loop(
        AnalyzeExperimentInput(experiment_id=3, question="分析实验3"), forbidden,
        lambda _messages, _schemas: {"content": '{"tool_run_id":"invented"}', "finish_reason": "stop"},
    )
    assert result.status == "partial"
    assert result.state.stop_reason == "missing_required_tool"
    assert result.trajectory == []
    assert selected is None and valid is False

