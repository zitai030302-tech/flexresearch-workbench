"""Independent analytical oracles; all curves are synthetic, not lab samples."""

import numpy as np
import pandas as pd
import pytest

import app as app_module
from flexresearch.curve_features import ExtractFeaturesInput, extract_features_tool, iv_differential_resistance


@pytest.mark.parametrize("unit,axis", [("percent", [0, 1, 2, 5, 10]), ("fraction", [0, .01, .02, .05, .1])])
def test_gf2_uses_zero_strain_not_first_three_loaded_points(unit, axis):
    result = extract_features_tool(ExtractFeaturesInput(kind="gauge_factor", x=axis, y=[100, 102, 104, 110, 120], strain_unit=unit, baseline_definition="mean_at_zero_strain"))
    assert result.gauge_factor == pytest.approx(2, rel=1e-12)
    assert result.parameters["baseline_resistance"] == 100
    assert result.parameters["baseline_indices"] == [0]
    assert result.parameters["strain_fraction"] == pytest.approx(.1)


def test_gf_zero_and_endpoint_replicates_are_explicit():
    result = extract_features_tool(ExtractFeaturesInput(kind="gauge_factor", x=[0, 0, 5, 10, 10], y=[99, 101, 110, 119, 121], strain_unit="percent", baseline_definition="mean_at_zero_strain"))
    assert result.gauge_factor == pytest.approx(2)
    assert result.parameters["baseline_indices"] == [0, 1]
    assert result.parameters["endpoint_indices"] == [3, 4]


def test_retention_uses_requested_1000_not_last_1500():
    result = extract_features_tool(ExtractFeaturesInput(kind="cycle_retention", x=[0, 250, 500, 1000, 1500], y=[100, 98, 96, 92, 70], baseline_definition="first_observed_cycle", target_cycle=1000))
    assert result.retention_percent == pytest.approx(92, abs=1e-12)
    assert result.parameters["initial_point"] == {"index": 0, "cycle": 0, "value": 100}
    assert result.parameters["final_point"] == {"index": 3, "cycle": 1000, "value": 92}


@pytest.mark.parametrize("voltage_unit,v_scale,current_unit,i_scale", [("V", 1, "A", 1), ("mV", 1000, "mA", 1000), ("V", 1, "uA", 1e6), ("V", 1, "nA", 1e9)])
def test_iv_1000_ohm_unit_conversion_and_current_offset(voltage_unit, v_scale, current_unit, i_scale):
    volts = np.array([-1, -.1, 0, .1, 1])
    amps = volts / 1000 + 2e-6
    resistance, parameters = iv_differential_resistance(volts*v_scale, amps*i_scale, f"voltage_{voltage_unit}", f"current_{current_unit}")
    assert resistance == pytest.approx(1000, rel=1e-12)
    assert parameters["conductance_S"] == pytest.approx(.001)
    assert parameters["point_count"] == 3
    assert parameters["output_unit"] == "ohm"


def test_iv_zero_current_does_not_fabricate_finite_resistance():
    resistance, parameters = iv_differential_resistance(np.array([-1, -.1, 0, .1, 1]), np.zeros(5), "voltage_V", "current_A")
    assert resistance is None
    assert parameters["conductance_S"] == 0


def test_legacy_gf_card_uses_same_correct_baseline():
    result = app_module.analyze(pd.DataFrame({"strain_percent": [0, 5, 10], "resistance_ohm": [100, 110, 120]}))
    assert next(item["value"] for item in result["metrics"] if item["label"] == "估算 GF") == "2"
    assert result["featureParameters"]["baseline_resistance"] == 100


def test_legacy_iv_card_is_in_ohms_not_volts_per_milliamp():
    result = app_module.analyze(pd.DataFrame({"voltage_V": [-1, -.1, 0, .1, 1], "current_mA": [-1, -.1, 0, .1, 1]}))
    item = next(item for item in result["metrics"] if item["label"] == "零偏附近微分电阻")
    assert item["value"] == "1000" and "Ω" in item["note"]

