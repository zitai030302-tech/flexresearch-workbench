import pytest

from flexresearch.lab_tools import build_lab_tool_registry


@pytest.mark.parametrize("slope,expected", [(1e-3, 1000), (-2e-3, -500), (0, None)])
def test_typed_iv_uses_near_zero_derivative_not_endpoints_or_offset(slope, expected):
    # Outer values deliberately disagree with the near-zero linear derivative.
    volts = [-1, -.1, 0, .1, 1]
    current = [-4, (-.1*slope+3e-6)*1000, 3e-3, (.1*slope+3e-6)*1000, 5]
    result = build_lab_tool_registry().execute("analyze_signal", {"signal": current,
        "iv_curve": {"voltage": volts, "voltage_column": "voltage_V", "current_column": "current_mA"}})
    assert result.status == "complete"
    value = result.result["differential_resistance_ohm"]
    assert value is None if expected is None else value == pytest.approx(expected, rel=1e-12)
    assert result.result["parameters"]["conductance_S"] == pytest.approx(slope, abs=1e-15)
    assert result.result["parameters"]["selected_indices"] == [1, 2, 3]

