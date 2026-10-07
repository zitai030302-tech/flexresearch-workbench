"""Frequency-to-rate conversion is arithmetic, not clinical validation."""

import numpy as np
import pytest

from flexresearch.lab_tools import build_lab_tool_registry


@pytest.mark.parametrize("frequency,bpm", [(0.8, 48), (1.2, 72), (2.0, 120)])
def test_explicit_pulse_rate_matches_independent_sine_truth(frequency, bpm):
    time = np.arange(2000) / 100
    values = np.sin(2*np.pi*frequency*time)
    result = build_lab_tool_registry().execute("spectral_analysis", {
        "signal": values.tolist(), "sample_rate": 100, "estimate_pulse_rate": True,
    })
    assert result.status == "complete"
    assert result.result["dominant_frequency_hz"] == pytest.approx(frequency, abs=.025)
    assert result.result["pulse_rate_bpm"] == pytest.approx(bpm, abs=1.5)
    assert result.result["pulse_rate_method"] == "dominant-frequency-hz-times-60-v1"


@pytest.mark.parametrize("value", [0, 3, -7])
def test_constant_signal_never_produces_a_pulse_rate(value):
    result = build_lab_tool_registry().execute("spectral_analysis", {
        "signal": [value]*1000, "sample_rate": 100, "estimate_pulse_rate": True,
    })
    assert result.status == "error" and result.result is None


def test_generic_fft_does_not_claim_pulse_rate():
    time = np.arange(1000) / 100
    result = build_lab_tool_registry().execute("spectral_analysis", {
        "signal": np.sin(2*np.pi*1.2*time).tolist(), "sample_rate": 100,
    })
    assert result.status == "complete"
    assert result.result["pulse_rate_bpm"] is None and result.result["pulse_rate_method"] is None

