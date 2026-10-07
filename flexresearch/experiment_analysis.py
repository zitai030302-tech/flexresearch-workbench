"""Validate the archived experiment scope before running numeric CSV tools."""

from __future__ import annotations

import hashlib
import time
import uuid
from pathlib import Path

from .agent import LabAgent, LabAgentResult
from .analysis_parameters import AnalysisParameters
from .analysis_context import AnalysisContext
from .tooling import ToolRegistry


def run_signal_analysis(
    registry: ToolRegistry,
    path: Path,
    question: str,
    *,
    experiment_id: int | None = None,
    file_id: int | None = None,
    sample_rate: float | None = None,
    channel: str | None = None,
    analysis_parameters: AnalysisParameters | None = None,
    analysis_context: AnalysisContext | None = None,
    output_dir: str | None = None,
    max_steps: int = 40,
) -> LabAgentResult:
    """Context and numeric calls share a trace; no invented experiment IDs.

    Standalone uploads may have no experiment association. They retain a
    load_csv-only scope, rather than creating a fictitious lab experiment.
    """
    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")
    started = time.monotonic()
    context = None
    expected_hash = None
    if experiment_id is not None:
        context = registry.execute("load_experiment_data", {"experiment_id": experiment_id})
        error = context.error
        try:
            if context.status != "complete" or not context.result:
                raise ValueError(error or "实验资料读取失败。")
            if context.result["experiment"]["experiment_id"] != experiment_id:
                raise ValueError("读取结果不属于所选实验，未执行计算。")
            matches = [entry for entry in context.result["files"]
                       if entry["source_file"] == path.name
                       and (file_id is None or entry["file_id"] == file_id)
                       and entry["available"] and entry["immutable"]
                       and entry["measurement_id"] is not None]
            if len(matches) != 1 or matches[0]["sha256"] != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError("所选实验文件范围或SHA-256不一致，未执行计算。")
            expected_hash = matches[0]["sha256"]
            if max_steps == 1:
                raise ValueError("工具预算已用完，未读取或分析数值。")
        except (ValueError, OSError, KeyError) as exc:
            return LabAgentResult(
                agent_run_id=uuid.uuid4().hex, status="error", intent="data_analysis",
                question=question, trajectory=[context], interpretation="实验读取未完成；未生成分析结论。",
                limitations=[str(exc)], state={"experiment_id": experiment_id, "file_id": file_id,
                    "phase": "failed", "step_count": 1, "max_steps": max_steps,
                    "completed_tools": [context.tool_name] if context.status == "complete" else []},
                stop_reason="step_budget_exhausted" if max_steps == 1 else "experiment_scope_error",
                latency_ms=round((time.monotonic() - started) * 1000),
            )
    result = LabAgent(registry, max_steps=max_steps - int(context is not None)).analyze_csv(
        str(path), question, sample_rate=sample_rate, output_dir=output_dir,
        experiment_id=experiment_id, channel=channel, analysis_parameters=analysis_parameters,
        analysis_context=analysis_context,
        expected_source_sha256=expected_hash,
    )
    if context is not None:
        result.trajectory.insert(0, context)
        result.state["step_count"] += 1
        result.state["completed_tools"].insert(0, context.tool_name)
        result.state["experiment_context_tool_run_id"] = context.tool_run_id
        result.state["experiment_id"] = experiment_id
        result.state["file_id"] = file_id
        for ref in result.source_refs:
            ref.parameters["experiment_context_tool_run_id"] = context.tool_run_id
    result.state["max_steps"] = max_steps
    goal_context = result.state.get("analysis_context") or {}
    if goal_context.get("source_run_id"):
        for ref in result.source_refs:
            ref.parameters["analysis_context"] = goal_context
    result.latency_ms = round((time.monotonic() - started) * 1000)
    return result

