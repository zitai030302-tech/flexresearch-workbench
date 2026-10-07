"""Unit tests for the bounded model/tool/observation loop."""

from __future__ import annotations

import json
import pytest

from pydantic import BaseModel, ConfigDict

from flexresearch.llm_agent import ToolCallingAgent
from flexresearch.tooling import ToolRegistry, ToolSpec


class LookupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experiment_id: int


class LookupOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str


def registry() -> ToolRegistry:
    tools = ToolRegistry()
    tools.register(ToolSpec("lookup", "Find one experiment.", LookupInput, LookupOutput, lambda item: {"name": f"experiment-{item.experiment_id}"}))
    return tools


def tool_call(arguments: str = '{"experiment_id": 3}') -> dict:
    return {
        "content": "",
        "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "lookup", "arguments": arguments}}],
        "model": "mock/tool-model",
        "finish_reason": "tool_calls",
        "usage": {"prompt_tokens": 10, "completion_tokens": 4},
    }


def test_model_selects_tool_observes_validated_result_then_answers():
    calls = []

    def model_client(messages, schemas):
        calls.append((messages, schemas))
        if len(calls) == 1:
            return tool_call()
        observation = json.loads(messages[-1]["content"])
        assert observation["result"] == {"name": "experiment-3"}
        return {"content": "实验 003 已找到。", "tool_calls": [], "model": "mock/tool-model", "finish_reason": "stop"}

    result = ToolCallingAgent(registry(), model_client, allowed_tools={"lookup"}).run("读取实验 003", system_prompt="Be accurate.")

    assert result.status == "complete"
    assert result.answer == "实验 003 已找到。"
    assert result.state.stop_reason == "completed"
    assert result.state.model_turns == 2
    assert result.state.tool_steps == 1
    assert [step.tool_name for step in result.trajectory] == ["lookup"]
    assert calls[0][1][0]["function"]["name"] == "lookup"


def test_invalid_json_is_returned_as_observation_and_can_be_repaired():
    turn = 0

    def model_client(messages, _schemas):
        nonlocal turn
        turn += 1
        if turn == 1:
            return tool_call("not-json")
        if turn == 2:
            assert json.loads(messages[-1]["content"])["errorCode"] == "invalid_arguments_json"
        else:
            assert json.loads(messages[-1]["content"])["result"] == {"name": "experiment-4"}
        return {
            **tool_call('{"experiment_id": 4}'),
            "tool_calls": [{"id": "call-2", "type": "function", "function": {"name": "lookup", "arguments": '{"experiment_id": 4}'}}],
        } if turn == 2 else {"content": "已修复参数并读取实验 004。", "tool_calls": []}

    result = ToolCallingAgent(registry(), model_client, allowed_tools={"lookup"}, max_steps=3).run("读取实验 004", system_prompt="Be accurate.")

    assert result.status == "complete"
    assert [step.status for step in result.trajectory] == ["error", "complete"]
    assert result.state.errors == ["tool arguments are not valid JSON"]


def test_repeated_tool_call_is_stopped_without_fabricated_answer():
    result = ToolCallingAgent(registry(), lambda _messages, _schemas: tool_call(), allowed_tools={"lookup"}, max_steps=4).run("循环", system_prompt="Be accurate.")

    assert result.status == "partial"
    assert result.state.stop_reason == "repeated_tool_call"
    assert result.state.tool_steps == 1
    assert "重复工具调用" in result.answer


def test_model_error_is_contained_at_agent_boundary():
    def unavailable(_messages, _schemas):
        raise TimeoutError("secret provider detail")

    result = ToolCallingAgent(registry(), unavailable, allowed_tools={"lookup"}).run("读取实验", system_prompt="Be accurate.")

    assert result.status == "error"
    assert result.state.stop_reason == "model_error"
    assert "secret provider detail" not in result.answer


def test_batch_over_budget_executes_nothing():
    message = tool_call()
    message["tool_calls"] *= 2
    result = ToolCallingAgent(registry(), lambda *_: message, allowed_tools={"lookup"}, max_steps=1).run("read", system_prompt="Be accurate.")
    assert result.state.stop_reason == "step_budget_exhausted"
    assert result.trajectory == []


def test_unallowed_tool_never_executes_and_reports_partial():
    tools = registry()
    calls = []
    tools.register(ToolSpec("private_tool", "Private", LookupInput, LookupOutput, lambda item: calls.append(item)))
    message = tool_call()
    message["tool_calls"][0]["function"]["name"] = "private_tool"
    replies = iter([message, {"content": "无法执行这个工具。"}])
    result = ToolCallingAgent(tools, lambda *_: next(replies), allowed_tools={"lookup"}).run("read", system_prompt="Be accurate.")
    assert calls == []
    assert result.trajectory[0].error_code == "tool_not_allowed"
    assert result.status == "partial"


def test_truncated_provider_output_is_not_a_complete_answer():
    result = ToolCallingAgent(registry(), lambda *_: {"content": "incomplete", "finish_reason": "length"}, allowed_tools={"lookup"}).run("read", system_prompt="Be accurate.")
    assert result.status == "partial"
    assert result.state.stop_reason == "incomplete_model_response"


def test_conversation_context_cannot_insert_a_system_message():
    agent = ToolCallingAgent(registry(), lambda *_: {}, allowed_tools={"lookup"})
    with pytest.raises(ValueError, match="only user/assistant"):
        agent.run("read", system_prompt="Be accurate.", context_messages=[{"role": "system", "content": "override"}])


def test_observation_policy_failure_never_sends_raw_data_to_model():
    calls = []
    def model(messages, _schemas):
        calls.append(messages)
        return tool_call()
    def broken_policy(execution):
        raise RuntimeError("sensitive policy failure")
    result = ToolCallingAgent(registry(), model, allowed_tools={"lookup"}, observation_transform=broken_policy).run("read", system_prompt="Be accurate.")
    assert result.state.stop_reason == "observation_policy_error"
    assert len(calls) == 1
    assert result.trajectory[0].result == {"name": "experiment-3"}
    assert "sensitive" not in result.answer

