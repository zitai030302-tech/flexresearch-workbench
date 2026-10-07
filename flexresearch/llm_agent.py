"""Bounded OpenAI-compatible tool-calling loop.

The loop is deliberately small and framework-free.  A model may select from an
explicit allowlist, but every call is still validated and executed by the
existing :class:`ToolRegistry`.  Deterministic scientific calculations remain
inside Python tools; the model never becomes the numeric oracle.
"""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from .tooling import ToolExecution, ToolRegistry


ModelClient = Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any]]


class ToolLoopState(BaseModel):
    phase: Literal["planning", "acting", "observing", "stopped", "failed"]
    model_turns: int = 0
    tool_steps: int = 0
    max_steps: int
    completed_tools: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    stop_reason: str | None = None


class ToolLoopResult(BaseModel):
    status: Literal["complete", "partial", "error"]
    answer: str
    trajectory: list[ToolExecution] = Field(default_factory=list)
    state: ToolLoopState
    model_observations: list[dict[str, Any]] = Field(default_factory=list)


class ToolCallingAgent:
    """Run a bounded model/tool loop over a strict tool allowlist."""

    def __init__(
        self,
        registry: ToolRegistry,
        model_client: ModelClient,
        *,
        allowed_tools: set[str],
        max_steps: int = 4,
        observation_transform: Callable[[ToolExecution], dict[str, Any]] | None = None,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        known = set(registry.names())
        unknown = allowed_tools - known
        if unknown:
            raise ValueError(f"unknown allowed tools: {', '.join(sorted(unknown))}")
        if not allowed_tools:
            raise ValueError("at least one allowed tool is required")
        self.registry = registry
        self.model_client = model_client
        self.allowed_tools = set(allowed_tools)
        self.max_steps = max_steps
        self.observation_transform = observation_transform

    def run(
        self,
        query: str,
        *,
        system_prompt: str,
        context_messages: list[dict[str, Any]] | None = None,
    ) -> ToolLoopResult:
        if not query.strip():
            raise ValueError("query must not be empty")
        state = ToolLoopState(phase="planning", max_steps=self.max_steps)
        trajectory: list[ToolExecution] = []
        observations: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        for message in context_messages or []:
            if message.get("role") not in {"user", "assistant"} or not isinstance(message.get("content"), str):
                raise ValueError("context must contain only user/assistant text messages")
            messages.append({"role": message["role"], "content": message["content"]})
        messages.append({"role": "user", "content": query})
        schemas = [
            item
            for item in self.registry.openai_schemas()
            if item.get("function", {}).get("name") in self.allowed_tools
        ]
        seen_signatures: set[str] = set()

        # At most max_steps tool calls plus one final model turn.  A response may
        # contain multiple calls, but calls beyond the remaining budget are not
        # executed or silently accepted.
        for _ in range(self.max_steps + 1):
            state.phase = "planning"
            try:
                model_message = self.model_client(deepcopy(messages), deepcopy(schemas))
            except Exception as exc:  # Provider errors stay inside the Agent boundary.
                state.phase = "failed"
                state.stop_reason = "model_error"
                code = getattr(exc, "code", None)
                detail = f"HTTP {code}" if isinstance(code, int) else type(exc).__name__
                state.errors.append(f"{detail}: model request failed")
                return ToolLoopResult(
                    status="error",
                    answer="模型当前不可用，已有工具记录已保留，未生成最终结论。" if trajectory else "模型当前不可用；没有生成工具结果或科学结论。",
                    trajectory=trajectory,
                    state=state,
                    model_observations=observations,
                )
            state.model_turns += 1
            if not isinstance(model_message, dict):
                state.phase = "failed"
                state.stop_reason = "invalid_model_response"
                state.errors.append("model message must be an object")
                return ToolLoopResult(status="error", answer="模型响应格式无效。", trajectory=trajectory, state=state, model_observations=observations)

            content = model_message.get("content")
            tool_calls = model_message.get("tool_calls") or []
            observations.append(
                {
                    "model": model_message.get("model"),
                    "finishReason": model_message.get("finish_reason"),
                    "toolCallCount": len(tool_calls) if isinstance(tool_calls, list) else 0,
                    "usage": model_message.get("usage") or {},
                }
            )
            if not isinstance(tool_calls, list):
                state.phase = "failed"
                state.stop_reason = "invalid_model_response"
                state.errors.append("tool_calls must be a list")
                return ToolLoopResult(status="error", answer="模型工具调用格式无效。", trajectory=trajectory, state=state, model_observations=observations)
            if model_message.get("finish_reason") in {"length", "content_filter"}:
                state.phase = "stopped"
                state.stop_reason = "incomplete_model_response"
                state.errors.append("provider did not finish the response")
                return ToolLoopResult(status="partial", answer="模型响应未完整返回，已保留执行记录。", trajectory=trajectory, state=state, model_observations=observations)
            if not tool_calls:
                answer = content.strip() if isinstance(content, str) else ""
                if not answer:
                    state.phase = "failed"
                    state.stop_reason = "empty_model_response"
                    state.errors.append("model returned neither text nor tool calls")
                    return ToolLoopResult(status="error", answer="模型没有返回可用内容。", trajectory=trajectory, state=state, model_observations=observations)
                state.phase = "stopped"
                unresolved_error = bool(trajectory and trajectory[-1].status != "complete")
                state.stop_reason = "completed_with_tool_errors" if unresolved_error else "completed"
                return ToolLoopResult(status="partial" if unresolved_error else "complete", answer=answer, trajectory=trajectory, state=state, model_observations=observations)

            if state.tool_steps + len(tool_calls) > self.max_steps:
                state.phase = "stopped"
                state.stop_reason = "step_budget_exhausted"
                state.errors.append(f"tool step budget exhausted at {self.max_steps}")
                return ToolLoopResult(
                    status="partial",
                    answer="工具调用达到安全上限，未生成未经验证的结论。",
                    trajectory=trajectory,
                    state=state,
                    model_observations=observations,
                )

            assistant_tool_calls: list[dict[str, Any]] = []
            pending: list[tuple[str, str, dict[str, Any], str | None]] = []
            for raw_call in tool_calls:
                call = raw_call if isinstance(raw_call, dict) else {}
                function = call.get("function") if isinstance(call.get("function"), dict) else {}
                # Use unique local correlation IDs even when a provider repeats one.
                call_id = f"call_{uuid.uuid4().hex}"
                name = str(function.get("name") or "")
                raw_arguments = function.get("arguments", "{}")
                parse_error: str | None = None
                if isinstance(raw_arguments, str):
                    try:
                        arguments = json.loads(raw_arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                        parse_error = "tool arguments are not valid JSON"
                elif isinstance(raw_arguments, dict):
                    arguments = raw_arguments
                else:
                    arguments = {}
                    parse_error = "tool arguments must be a JSON object"
                if not isinstance(arguments, dict):
                    arguments = {}
                    parse_error = "tool arguments must decode to an object"
                signature = json.dumps({"name": name, "arguments": arguments}, ensure_ascii=False, sort_keys=True)
                if signature in seen_signatures:
                    state.phase = "stopped"
                    state.stop_reason = "repeated_tool_call"
                    state.errors.append(f"repeated tool call blocked: {name or '<missing>'}")
                    return ToolLoopResult(
                        status="partial",
                        answer="检测到重复工具调用，已停止，未补写结论。",
                        trajectory=trajectory,
                        state=state,
                        model_observations=observations,
                    )
                seen_signatures.add(signature)
                assistant_tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
                    }
                )
                pending.append((call_id, name, arguments, parse_error))

            messages.append({"role": "assistant", "content": content or "", "tool_calls": assistant_tool_calls})
            state.phase = "acting"
            for call_id, name, arguments, parse_error in pending:
                if parse_error:
                    execution = ToolExecution(
                        tool_run_id=uuid.uuid4().hex,
                        tool_name=name or "<missing>",
                        status="error",
                        arguments=arguments,
                        error_code="invalid_arguments_json",
                        error=parse_error,
                        recoverable=True,
                        latency_ms=0,
                    )
                elif name not in self.allowed_tools:
                    execution = ToolExecution(
                        tool_run_id=uuid.uuid4().hex,
                        tool_name=name or "<missing>",
                        status="error",
                        arguments=arguments,
                        error_code="tool_not_allowed",
                        error=f"tool is not allowed in this run: {name or '<missing>'}",
                        recoverable=False,
                        latency_ms=0,
                    )
                else:
                    execution = self.registry.execute(name, arguments)
                trajectory.append(execution)
                state.tool_steps += 1
                state.phase = "observing"
                if execution.status == "complete":
                    state.completed_tools.append(execution.tool_name)
                elif execution.error:
                    state.errors.append(execution.error)
                observation = {
                    "status": execution.status,
                    "result": execution.result,
                    "errorCode": execution.error_code,
                    "error": execution.error,
                    "recoverable": execution.recoverable,
                    "toolRunId": execution.tool_run_id,
                }
                if self.observation_transform is not None:
                    try:
                        observation = self.observation_transform(execution.model_copy(deep=True))
                        if not isinstance(observation, dict):
                            raise TypeError("observation must be an object")
                        json.dumps(observation)
                    except Exception:
                        # Fail closed: never fall back to disclosing the raw tool result.
                        state.phase = "failed"
                        state.stop_reason = "observation_policy_error"
                        state.errors.append("tool observation could not be safely serialized")
                        return ToolLoopResult(status="error", answer="工具结果已保留，但未通过模型上下文安全检查。", trajectory=trajectory, state=state, model_observations=observations)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": execution.tool_name,
                        "content": json.dumps(observation, ensure_ascii=False),
                    }
                )

        state.phase = "stopped"
        state.stop_reason = "model_turn_budget_exhausted"
        state.errors.append("model turn budget exhausted")
        return ToolLoopResult(
            status="partial",
            answer="模型未在限定轮数内形成最终回答，已安全停止。",
            trajectory=trajectory,
            state=state,
            model_observations=observations,
        )

