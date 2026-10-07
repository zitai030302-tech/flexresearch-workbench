"""Analytical y=2+4t validates means, drift and original-index slopes."""

import pytest

from flexresearch.signal_quality import AnalyzeSignalInput, analyze_signal_tool


@pytest.mark.parametrize("values,valid", [([2, 4, 6, 8, 10], 5), ([2, 4, None, 8, 10], 4)])
@pytest.mark.parametrize("rate,slope,unit", [(2, 4, "second"), (None, 2, "sample")])
def test_finite_statistics_keep_original_indices(values, valid, rate, slope, unit):
    output = analyze_signal_tool(AnalyzeSignalInput(signal=values, sample_rate=rate))
    assert output.valid_point_count == valid
    assert output.mean == 6 and output.minimum == 2 and output.maximum == 10
    assert output.slope == pytest.approx(slope) and output.drift == pytest.approx(8)
    assert output.slope_axis_unit == unit

