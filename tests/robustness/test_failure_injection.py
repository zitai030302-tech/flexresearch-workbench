"""Failure-injection tests for scientific tools, the LabAgent and API boundaries.

These tests deliberately assert absence of calculated results after a failure.
They do not use an LLM judge and never accept a plausible-looking number as a
substitute for a completed deterministic tool call.
"""

from __future__ import annotations

import io
import math
import sqlite3
import time
import urllib.error

import pytest
from pydantic import BaseModel

import app as app_module
import flexresearch.lab_tools as lab_tools
from app import app
from flexresearch import LabAgent, build_lab_tool_registry
from flexresearch.tooling import ToolRegistry, ToolSpec


def test_missing_file_is_an_explicit_recoverable_error_without_results(tmp_path):
    result = LabAgent(build_lab_tool_registry()).analyze_csv(
        str(tmp_path / "does-not-exist.csv"),
        "分析这个文件",
    )

    assert result.status == "error"
    assert result.state["phase"] == "failed"
    assert result.measured_result == {}
    assert result.calculated_result == {}
    assert result.source_refs == []
    assert result.artifacts == []
    assert len(result.trajectory) == 1
    assert result.trajectory[0].status == "error"
    assert result.trajectory[0].recoverable is True
    assert result.trajectory[0].result is None
    assert "does not exist" in (result.trajectory[0].error or "")


def test_corrupt_csv_is_rejected_without_partial_numeric_output(tmp_path):
    source = tmp_path / "corrupt.csv"
    source.write_bytes(b"\xff\xfe\xfa\x00not-a-valid-utf8-csv")

    run = build_lab_tool_registry().execute("load_csv", {"file_path": str(source)})

    assert run.status == "error"
    assert run.error_code == "ValueError"
    assert run.recoverable is True
    assert run.result is None
    assert "CSV parsing failed" in (run.error or "")


def test_recognizable_renamed_columns_recover_via_aliases(tmp_path):
    source = tmp_path / "renamed-columns.csv"
    rows = ["elapsed_seconds,pulse_ch4"]
    rows.extend(
        f"{index / 100:.2f},{math.sin(2 * math.pi * index / 100):.12f}"
        for index in range(200)
    )
    source.write_text("\n".join(rows), encoding="utf-8")

    result = LabAgent(build_lab_tool_registry()).analyze_csv(
        str(source),
        "找主要脉搏频率",
    )

    assert result.status == "complete"
    assert result.state["selected_columns"]["time"] == "elapsed_seconds"
    assert result.state["selected_columns"]["signal"] == "pulse_ch4"
    assert [step.tool_name for step in result.trajectory] == ["load_csv", "spectral_analysis"]
    assert all(step.status == "complete" for step in result.trajectory)
    assert "spectrum" in result.calculated_result
    assert any(ref.channel == "pulse_ch4" for ref in result.source_refs)


@pytest.mark.parametrize("bad_value", ["NaN", "inf"])
def test_non_finite_signal_returns_partial_and_never_a_spectrum(tmp_path, bad_value):
    source = tmp_path / f"non-finite-{bad_value.lower()}.csv"
    signal = ["0", "1", "2", "3", bad_value, "5", "6", "7", "8", "9"]
    rows = ["elapsed_seconds,pulse_ch4"] + [
        f"{index / 10:.1f},{value}" for index, value in enumerate(signal)
    ]
    source.write_text("\n".join(rows), encoding="utf-8")

    result = LabAgent(build_lab_tool_registry()).analyze_csv(
        str(source),
        "找主要脉搏频率",
        sample_rate=10,
    )

    assert result.status == "partial"
    assert "spectrum" not in result.calculated_result
    spectral_step = next(step for step in result.trajectory if step.tool_name == "spectral_analysis")
    assert spectral_step.status == "error"
    assert spectral_step.recoverable is True
    assert spectral_step.result is None
    assert result.limitations
    assert result.state["errors"]
    quality = result.measured_result["data_quality"]["pulse_ch4"]
    assert quality["valid_points"] == 9
    assert quality["nan_count"] == (1 if bad_value == "NaN" else 0)
    assert quality["inf_count"] == (1 if bad_value == "inf" else 0)
    assert "never silently" in result.measured_result["cleaning_policy"]


def test_csv_size_limit_accepts_exact_boundary_and_rejects_one_byte_over(tmp_path, monkeypatch):
    source = tmp_path / "boundary.csv"
    raw = b"x,y\n1,2\n"
    source.write_bytes(raw)
    registry = build_lab_tool_registry()

    monkeypatch.setattr(lab_tools, "MAX_CSV_BYTES", len(raw))
    exact = registry.execute("load_csv", {"file_path": str(source)})
    assert exact.status == "complete"

    monkeypatch.setattr(lab_tools, "MAX_CSV_BYTES", len(raw) - 1)
    oversized = registry.execute("load_csv", {"file_path": str(source)})
    assert oversized.status == "error"
    assert oversized.error_code == "ValueError"
    assert oversized.recoverable is True
    assert oversized.result is None
    assert "limit" in (oversized.error or "").lower()


def test_missing_sample_rate_is_partial_and_does_not_invent_frequency(tmp_path):
    source = tmp_path / "unknown-rate.csv"
    source.write_text(
        "pulse_ch4,channel\n1,4\n2,4\n3,4\n4,4\n5,4\n6,4\n7,4\n8,4\n",
        encoding="utf-8",
    )

    result = LabAgent(build_lab_tool_registry()).analyze_csv(
        str(source),
        "找主要脉搏频率",
    )

    assert result.status == "partial"
    assert "spectrum" not in result.calculated_result
    assert [step.tool_name for step in result.trajectory] == ["load_csv"]
    assert result.state["sample_rate"] is None
    assert any("sample rate" in limitation for limitation in result.limitations)


def test_invalid_filter_parameter_is_recoverable_and_has_no_signal_result():
    run = build_lab_tool_registry().execute(
        "filter_signal",
        {
            "signal": [0.0] * 32,
            "sample_rate": 10,
            "low_cut": 4,
            "high_cut": 2,
        },
    )

    assert run.status == "error"
    assert run.error_code == "invalid_arguments"
    assert run.recoverable is True
    assert run.result is None


def test_database_failure_returns_an_explicit_api_error_without_agent_output(monkeypatch):
    def unavailable_database():
        raise sqlite3.OperationalError("injected database unavailable")

    monkeypatch.setattr(app_module, "get_db", unavailable_database)
    response = app.test_client().post(
        "/api/analyze",
        data={
            "question": "只读概览",
            "file": (io.BytesIO(b"time_s,signal\n0,1\n1,2\n"), "measurement.csv"),
        },
        content_type="multipart/form-data",
    )

    payload = response.get_json()
    assert response.status_code >= 400
    assert payload is not None
    assert "injected database unavailable" in payload["error"]
    assert payload["errorCode"] == "database_error"
    assert payload["recoverable"] is True
    assert "agent" not in payload
    assert "calculatedResult" not in payload


def test_llm_timeout_returns_no_answer_and_records_failure(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "model_configuration",
        lambda: {
            "configured": True,
            "apiKey": "test-only",
            "baseUrl": "https://provider.invalid/v1",
            "model": "timeout-fixture",
        },
    )

    def timeout_request(*_args, **_kwargs):
        raise urllib.error.URLError(TimeoutError("injected timeout"))

    monkeypatch.setattr(app_module, "request_json", timeout_request)
    answer, error = app_module.model_synthesis(
        "这个信号说明什么？",
        [],
        {"track": "bioelectronics"},
    )

    observation = app_module.MODEL_CALL_OBSERVATION.get()
    assert answer is None
    assert error is not None and "TimeoutError" in error
    assert observation["status"] == "timeout"
    assert observation["attempts"] == 2
    assert observation["error"] == "TimeoutError"
    assert "actualModel" not in observation


def test_retrieval_no_result_is_an_explicit_empty_result_without_citations():
    run = app_module.build_application_tool_registry().execute(
        "search_knowledge_base",
        {"query": "quantum galactic zebrafish xyz", "limit": 3},
    )

    assert run.status == "complete"
    assert run.error is None
    assert run.result is not None
    assert run.result["items"] == []
    assert run.result["private_data_sent_externally"] is False
    assert "citation" not in run.result


class _EmptyInput(BaseModel):
    pass


class _EmptyOutput(BaseModel):
    pass


def test_tool_runtime_exception_is_structured_recoverable_and_result_free():
    registry = ToolRegistry()

    def broken_tool(_: _EmptyInput) -> _EmptyOutput:
        raise RuntimeError("injected tool failure")

    registry.register(
        ToolSpec(
            name="broken_tool",
            description="failure injection fixture",
            input_model=_EmptyInput,
            output_model=_EmptyOutput,
            handler=broken_tool,
            timeout_seconds=1,
        )
    )

    run = registry.execute("broken_tool", {})

    assert run.status == "error"
    assert run.error_code == "RuntimeError"
    assert run.error == "injected tool failure"
    assert run.recoverable is True
    assert run.result is None


def test_tool_timeout_is_structured_recoverable_and_result_free():
    registry = ToolRegistry()

    def slow_tool(_: _EmptyInput) -> _EmptyOutput:
        time.sleep(0.05)
        return _EmptyOutput()

    registry.register(
        ToolSpec(
            name="slow_tool",
            description="timeout injection fixture",
            input_model=_EmptyInput,
            output_model=_EmptyOutput,
            handler=slow_tool,
            timeout_seconds=0.001,
        )
    )

    run = registry.execute("slow_tool", {})

    assert run.status == "timeout"
    assert run.error_code == "timeout"
    assert run.recoverable is True
    assert run.result is None

