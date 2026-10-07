import numpy as np
import pytest

from flexresearch.curve_features import ExtractFeaturesInput, extract_features_tool, feature_arguments, feature_kind, iv_differential_resistance
from flexresearch.lab_tools import build_lab_tool_registry


@pytest.mark.parametrize("updates", [
    {"strain_unit": None}, {"strain_unit": "guess"}, {"y": [100]}, {"x": [0, float("inf")]},
    {"y": [100, float("nan")]}, {"baseline_definition": "first_three"}, {"target_cycle": 1000},
])
def test_feature_schema_rejects_invalid_parameters(updates):
    args = {"kind": "gauge_factor", "x": [0, 10], "y": [100, 120], "strain_unit": "percent", "baseline_definition": "mean_at_zero_strain", **updates}
    execution = build_lab_tool_registry().execute("extract_features", args)
    assert execution.status == "error" and execution.error_code == "invalid_arguments"
    assert execution.result is None


@pytest.mark.parametrize("x,y", [([1, 10], [102, 120]), ([0, 0], [100, 100]), ([0, 10], [0, 20]), ([0, 10, 0], [100, 120, 105]), ([-1, 0, 10], [98, 100, 120])])
def test_gf_refuses_missing_baseline_or_mixed_loading(x, y):
    with pytest.raises(ValueError):
        extract_features_tool(ExtractFeaturesInput(kind="gauge_factor", x=x, y=y, strain_unit="percent", baseline_definition="mean_at_zero_strain"))


@pytest.mark.parametrize("x,y,target", [([0, 900], [100, 92], 1000), ([0, 1000, 1000], [100, 92, 91], 1000), ([0, 1000], [0, 92], 1000), ([1000, 0], [92, 100], 1000), ([0, 1000.5], [100, 92], 1000)])
def test_retention_refuses_missing_or_ambiguous_target(x, y, target):
    with pytest.raises(ValueError):
        extract_features_tool(ExtractFeaturesInput(kind="cycle_retention", x=x, y=y, baseline_definition="first_observed_cycle", target_cycle=target))


@pytest.mark.parametrize("column,metadata", [("strain", {}), ("strain_percent", {"strain_unit": "fraction"}), ("strain", {"strain_unit": "microstrain"})])
def test_strain_unit_not_guessed_and_conflicts_rejected(column, metadata):
    with pytest.raises(ValueError):
        feature_arguments("gauge_factor", {column: [0, 10], "resistance": [100, 120]}, "计算GF", metadata)


@pytest.mark.parametrize("query", ["计算保持率", "比较1000次循环和1500次循环的保持率"])
def test_target_cycle_must_be_unambiguous(query):
    with pytest.raises(ValueError):
        feature_arguments("cycle_retention", {"cycle": [0, 1000], "response": [100, 92]}, query)


@pytest.mark.parametrize("query,expected", [("计算GF。", "gauge_factor"), ("计算 GF。", "gauge_factor"), ("说明TGFbeta", None), ("计算1000次循环保持率", "cycle_retention")])
def test_curve_request_recognizes_chinese_adjacent_gf(query, expected):
    assert feature_kind(query) == expected


@pytest.mark.parametrize("x,y,vcol,icol", [([-1, 0, 1], [-.001, 0, .001], "voltage", "current_A"), ([-1, 0, 1], [-.001, 0, .001], "voltage_V", "current"), ([.01, .1, 1], [1e-5, 1e-4, .001], "voltage_V", "current_A"), ([-1, 0, 0, 1], [-.001, 0, 0, .001], "voltage_V", "current_A"), ([-1, 0, 1], [-.001, float("nan"), .001], "voltage_V", "current_A")])
def test_iv_requires_units_finite_unambiguous_zero_window(x, y, vcol, icol):
    with pytest.raises(ValueError):
        iv_differential_resistance(np.array(x), np.array(y), vcol, icol)

