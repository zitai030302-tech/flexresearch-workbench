import hashlib
import time

import pytest
from pydantic import BaseModel

from flexresearch.lab_tools import build_lab_tool_registry
from flexresearch.tooling import ToolRegistry, ToolSpec


def test_registry_exposes_typed_openai_function_schemas():
    registry = build_lab_tool_registry()
    schemas = {item["function"]["name"]: item for item in registry.openai_schemas()}
    assert set(schemas) == {"load_csv", "analyze_signal", "extract_features", "filter_signal", "spectral_analysis", "calculate_bioz_features", "plot_signal", "compare_experiments", "export_signal"}
    assert schemas["filter_signal"]["function"]["parameters"]["properties"]["sample_rate"]["exclusiveMinimum"] == 0


def test_load_csv_reports_schema_stats_missingness_and_hash(tmp_path):
    source = tmp_path / "bioz.csv"
    raw = b"frequency_hz,z_real_ohm,z_imag_ohm\n10,3,4\n20,6,8\n"
    source.write_bytes(raw)
    run = build_lab_tool_registry().execute("load_csv", {"file_path": str(source)})
    assert run.status == "complete"
    assert run.result["shape"] == [2, 3]
    assert run.result["basic_stats"]["z_real_ohm"]["mean"] == pytest.approx(4.5)
    assert run.result["source_sha256"] == hashlib.sha256(raw).hexdigest()


def test_load_csv_reports_non_finite_quality_without_silent_cleaning(tmp_path):
    source = tmp_path / "quality.csv"
    source.write_text("time_s,signal\n0,1\n1,NaN\n2,inf\n", encoding="utf-8")

    run = build_lab_tool_registry().execute("load_csv", {"file_path": str(source)})

    assert run.status == "complete"
    assert run.result["data_quality"]["signal"] == {
        "total_points": 3,
        "valid_points": 1,
        "nan_count": 1,
        "inf_count": 1,
        "finite_fraction": pytest.approx(1 / 3),
    }
    assert "never silently" in run.result["cleaning_policy"]


def test_invalid_filter_arguments_return_recoverable_error():
    run = build_lab_tool_registry().execute("filter_signal", {"signal": [0.0] * 20, "sample_rate": 10, "low_cut": 4, "high_cut": 2})
    assert run.status == "error"
    assert run.error_code == "invalid_arguments"
    assert run.recoverable is True


class Empty(BaseModel):
    pass


def test_tool_timeout_is_observable():
    registry = ToolRegistry()

    def slow(_: Empty) -> Empty:
        time.sleep(0.05)
        return Empty()

    registry.register(ToolSpec("slow", "timeout fixture", Empty, Empty, slow, timeout_seconds=0.001))
    run = registry.execute("slow", {})
    assert run.status == "timeout"
    assert run.error_code == "timeout"


def test_unknown_tool_does_not_raise_or_fabricate_result():
    run = build_lab_tool_registry().execute("not_registered", {})
    assert run.status == "error"
    assert run.result is None
    assert run.error_code == "tool_not_found"


def test_unexpected_tool_bug_stays_inside_structured_agent_boundary():
    registry = ToolRegistry()

    def buggy(_: Empty) -> Empty:
        raise ZeroDivisionError("sensitive internal detail")

    registry.register(ToolSpec("buggy", "unexpected bug fixture", Empty, Empty, buggy))
    run = registry.execute("buggy", {})

    assert run.status == "error"
    assert run.error_code == "unexpected_tool_error"
    assert run.recoverable is False
    assert run.result is None
    assert run.error == "ZeroDivisionError: tool execution failed"
    assert "sensitive internal detail" not in run.error

