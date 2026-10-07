"""Typed I–V tool contracts, distinct from HTTP integration tests."""

import pytest

from flexresearch.lab_tools import build_lab_tool_registry


def arguments():
    return {"signal": [-.998, -.098, .002, .102, 1.002], "iv_curve": {
        "voltage": [-1, -.1, 0, .1, 1], "voltage_column": "voltage_V", "current_column": "current_mA"}}


def test_iv_typed_tool_returns_ohms_without_temporal_quality_fields():
    result = build_lab_tool_registry().execute("analyze_signal", arguments())
    assert result.status == "complete"
    assert result.result["differential_resistance_ohm"] == pytest.approx(1000)
    assert result.result["parameters"]["selected_indices"] == [1, 2, 3]
    assert result.result["parameters"]["window_half_width_V"] == .1
    assert result.result["algorithm_version"] == "iv-zero-bias-ols-v1"
    assert "quality_score" not in result.result and "sample_rate" not in result.result


@pytest.mark.parametrize("fault", ["mismatch", "missing", "infinite", "sample_rate", "window", "threshold", "unknown_unit", "duplicate_bias", "no_zero_window"])
def test_iv_tool_rejects_ambiguous_or_invalid_inputs(fault):
    args = arguments()
    if fault == "mismatch":
        args["signal"].pop()
    elif fault == "missing":
        args["signal"][2] = None
    elif fault == "infinite":
        args["iv_curve"]["voltage"][2] = float("inf")
    elif fault == "sample_rate":
        args["sample_rate"] = 100
    elif fault == "window":
        args["window_samples"] = 3
    elif fault == "threshold":
        args["jump_mad_multiplier"] = 3
    elif fault == "unknown_unit":
        args["iv_curve"]["current_column"] = "current"
    elif fault == "duplicate_bias":
        args["iv_curve"]["voltage"][2] = -.1
    else:
        args["iv_curve"]["voltage"] = [1, 2, 3, 4, 5]
    result = build_lab_tool_registry().execute("analyze_signal", args)
    assert result.status == "error" and result.result is None


def test_original_signal_quality_contract_still_has_typed_output():
    result = build_lab_tool_registry().execute("analyze_signal", {"signal": [2, 4, 6, 8, 10], "sample_rate": 2})
    assert result.status == "complete" and result.result["slope"] == 4
    assert "iv" not in result.result and "differential_resistance_ohm" not in result.result

