"""Known synthetic anomalies test heuristics, not clinical classification."""

import json

import numpy as np
import pytest

from flexresearch.lab_tools import build_lab_tool_registry
from flexresearch.signal_quality import AnalyzeSignalInput, analyze_signal_tool


def test_normal_sine_and_known_burst_intervals():
    time = np.arange(3000) / 100
    clean = np.sin(2 * np.pi * time)
    result = analyze_signal_tool(AnalyzeSignalInput(signal=clean.tolist(), sample_rate=100))
    assert result.quality_score == 100
    assert result.artifact_intervals == []
    noisy = clean.copy()
    noisy[1200:1600] += 8 * np.sin(2 * np.pi * 10 * time[1200:1600])
    result = analyze_signal_tool(AnalyzeSignalInput(signal=noisy.tolist(), sample_rate=100))
    detected = np.zeros(3000, dtype=bool)
    for item in result.artifact_intervals:
        detected[item.start_sample:item.end_sample_exclusive] = True
        assert item.start_s == item.start_sample / 100
        assert item.end_s_exclusive == item.end_sample_exclusive / 100
    truth = np.zeros(3000, dtype=bool)
    truth[1200:1600] = True
    assert (detected & truth).sum() / (detected | truth).sum() > .95
    assert result.quality_score == pytest.approx(100 * (1 - detected.mean()))
    assert result.quality_method.window_std_threshold == pytest.approx(4 / np.sqrt(2))
    assert any("不能" in item or "不证明" in item for item in result.limitations)


def test_finite_statistics_keep_original_indices_and_do_not_impute():
    result = analyze_signal_tool(AnalyzeSignalInput(signal=[0, 2, None, 6, float('inf'), 10], sample_rate=2))
    assert result.valid_point_count == 4 and result.nonfinite_count == 2
    assert result.mean == 4.5 and result.minimum == 0 and result.maximum == 10
    assert result.slope == pytest.approx(4) and result.drift == pytest.approx(10)
    assert result.slope_axis_unit == "second"
    assert [(i.start_sample, i.end_sample_exclusive, i.reasons) for i in result.artifact_intervals] == [(2, 3, ['nonfinite']), (4, 5, ['nonfinite'])]
    json.dumps(result.model_dump(), allow_nan=False)


def test_flat_signal_is_flagged_not_called_healthy():
    result = analyze_signal_tool(AnalyzeSignalInput(signal=[3] * 100))
    assert result.quality_score == 0 and result.flagged_point_count == 100
    assert result.artifact_intervals[0].reasons == ['flat_segment']
    assert result.artifact_intervals[0].start_s is None
    assert result.quality_method.axis == 'sample_index'
    assert result.slope == 0 and result.drift == 0


def test_all_invalid_values_are_reported_without_fabricated_statistics():
    result = analyze_signal_tool(AnalyzeSignalInput(signal=[None, float('nan'), float('inf')]))
    assert result.valid_point_count == 0 and result.quality_score == 0
    assert result.mean is result.minimum is result.maximum is result.drift is result.slope is None
    json.dumps(result.model_dump(), allow_nan=False)


def test_single_spike_is_detected_and_input_is_unchanged():
    signal = np.sin(2*np.pi*np.arange(1000)/100)
    signal[500] += 100
    original = signal.copy()
    result = analyze_signal_tool(AnalyzeSignalInput(signal=signal.tolist(), sample_rate=100))
    assert any(i.start_sample <= 500 < i.end_sample_exclusive and 'abrupt_change' in i.reasons for i in result.artifact_intervals)
    assert np.array_equal(signal, original)


def test_many_missing_intervals_cap_display_but_count_all():
    signal = [None if index % 2 else float(index) for index in range(2000)]
    result = analyze_signal_tool(AnalyzeSignalInput(signal=signal))
    assert result.interval_count == 1000 and len(result.artifact_intervals) == 500
    assert result.intervals_truncated and result.flagged_point_count == 1000
    assert result.quality_score == 50


@pytest.mark.parametrize('extra', [{'sample_rate': float('inf')}, {'sample_rate': 0}, {'window_samples': True}, {'jump_mad_multiplier': -1}, {'window_std_multiplier': float('nan')}])
def test_invalid_parameters_are_tool_errors(extra):
    result = build_lab_tool_registry().execute('analyze_signal', {'signal': [1, 2, 3], **extra})
    assert result.status == 'error' and result.error_code == 'invalid_arguments'


def test_explicit_algorithm_settings_are_reported():
    result = analyze_signal_tool(AnalyzeSignalInput(signal=list(range(100)), window_samples=25, flat_min_samples=5, jump_mad_multiplier=8, window_std_multiplier=3))
    assert result.quality_method.window_samples == 25
    assert result.quality_method.flat_min_samples == 5
    assert result.quality_method.jump_mad_multiplier == 8
    assert result.quality_method.window_std_multiplier == 3


def test_numeric_overflow_is_failure_not_fake_finite_result():
    result = build_lab_tool_registry().execute('analyze_signal', {'signal': [1e308, -1e308]})
    assert result.status == 'error' and result.result is None

