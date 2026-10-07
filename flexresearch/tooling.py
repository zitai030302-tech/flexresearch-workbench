"""Typed tool registry with timeouts, structured errors and execution events."""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from .model_schema import inline_local_refs


LOGGER = logging.getLogger("flexresearch.tools")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[BaseModel], BaseModel | dict[str, Any]]
    timeout_seconds: float = 10.0
    # Optional two-phase tools prepare without side effects in the worker.
    # Only an on-time, validated preparation may commit in the caller thread.
    prepared_model: type[BaseModel] | None = None
    commit_handler: Callable[[BaseModel], BaseModel | dict[str, Any]] | None = None


class ToolExecution(BaseModel):
    tool_run_id: str
    tool_name: str
    status: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error: str | None = None
    recoverable: bool = False
    latency_ms: int


class ToolRegistry:
    def __init__(self, observer: Callable[[ToolExecution], None] | None = None) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._observer = observer

    def register(self, spec: ToolSpec) -> None:
        if (spec.prepared_model is None) != (spec.commit_handler is None):
            raise ValueError("prepared_model and commit_handler must be configured together")
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def names(self) -> list[str]:
        return sorted(self._tools)

    def openai_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": inline_local_refs(spec.input_model.model_json_schema()),
                },
            }
            for spec in self._tools.values()
        ]

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolExecution:
        started = time.monotonic()
        tool_run_id = uuid.uuid4().hex
        spec = self._tools.get(name)
        if spec is None:
            execution = ToolExecution(tool_run_id=tool_run_id, tool_name=name, status="error", arguments=arguments, error_code="tool_not_found", error=f"unknown tool: {name}", recoverable=True, latency_ms=0)
            return self._emit(execution)
        try:
            parsed = spec.input_model.model_validate(arguments)
        except ValidationError as exc:
            execution = ToolExecution(tool_run_id=tool_run_id, tool_name=name, status="error", arguments=arguments, error_code="invalid_arguments", error=str(exc), recoverable=True, latency_ms=round((time.monotonic() - started) * 1000))
            return self._emit(execution)
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"tool-{name}")
        future = executor.submit(spec.handler, parsed)
        try:
            raw_result = future.result(timeout=spec.timeout_seconds)
            if spec.commit_handler is not None:
                prepared = spec.prepared_model.model_validate(raw_result)
                raw_result = spec.commit_handler(prepared)
            result = spec.output_model.model_validate(raw_result).model_dump(mode="json")
            execution = ToolExecution(tool_run_id=tool_run_id, tool_name=name, status="complete", arguments=parsed.model_dump(mode="json"), result=result, latency_ms=round((time.monotonic() - started) * 1000))
        except FutureTimeout:
            future.cancel()
            execution = ToolExecution(tool_run_id=tool_run_id, tool_name=name, status="timeout", arguments=parsed.model_dump(mode="json"), error_code="timeout", error=f"tool exceeded {spec.timeout_seconds:g}s timeout", recoverable=True, latency_ms=round((time.monotonic() - started) * 1000))
        except (OSError, ValueError, RuntimeError, ValidationError) as exc:
            execution = ToolExecution(tool_run_id=tool_run_id, tool_name=name, status="error", arguments=parsed.model_dump(mode="json"), error_code=type(exc).__name__, error=str(exc), recoverable=True, latency_ms=round((time.monotonic() - started) * 1000))
        except Exception as exc:  # Keep an unexpected tool bug inside the Agent boundary.
            LOGGER.exception("unexpected tool failure", extra={"tool_name": name, "tool_run_id": tool_run_id})
            execution = ToolExecution(
                tool_run_id=tool_run_id,
                tool_name=name,
                status="error",
                arguments=parsed.model_dump(mode="json"),
                error_code="unexpected_tool_error",
                error=f"{type(exc).__name__}: tool execution failed",
                recoverable=False,
                latency_ms=round((time.monotonic() - started) * 1000),
            )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        return self._emit(execution)

    def _emit(self, execution: ToolExecution) -> ToolExecution:
        LOGGER.info("tool_execution", extra={"event": execution.model_dump(mode="json")})
        if self._observer:
            self._observer(execution)
        return execution

