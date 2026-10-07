import numpy as np
import pytest

from flexresearch.lab_tools import build_lab_tool_registry


def sine(frequency: float, sample_rate: float = 100.0, seconds: float = 10.0) -> tuple[np.ndarray, np.ndarray]:
    time = np.arange(0, seconds, 1 / sample_rate)
    return time, np.sin(2 * np.pi * frequency * time)


def test_fft_finds_one_hz_ground_truth():
    _, signal = sine(1.0)
    run = build_lab_tool_registry().execute("spectral_analysis", {"signal": signal.tolist(), "sample_rate": 100.0})
    assert run.status == "complete"
    assert run.result["dominant_frequency_hz"] == pytest.approx(1.0, abs=0.05)


def test_fft_finds_one_hz_under_seeded_noise():
    _, signal = sine(1.0)
    noisy = signal + np.random.default_rng(7).normal(0, 0.25, len(signal))
    run = build_lab_tool_registry().execute("spectral_analysis", {"signal": noisy.tolist(), "sample_rate": 100.0})
    assert run.result["dominant_frequency_hz"] == pytest.approx(1.0, abs=0.05)


def test_fft_identifies_two_known_peaks():
    time, first = sine(0.8, seconds=20)
    signal = first + 0.8 * np.sin(2 * np.pi * 1.2 * time)
    run = build_lab_tool_registry().execute("spectral_analysis", {"signal": signal.tolist(), "sample_rate": 100.0, "max_peaks": 2})
    frequencies = sorted(peak["frequency_hz"] for peak in run.result["peaks"])
    assert frequencies == pytest.approx([0.8, 1.2], abs=0.05)


def test_bandpass_suppresses_twenty_hz_and_preserves_one_hz():
    time, low = sine(1.0)
    mixed = low + np.sin(2 * np.pi * 20 * time)
    filtered = build_lab_tool_registry().execute("filter_signal", {"signal": mixed.tolist(), "sample_rate": 100.0, "low_cut": 0.5, "high_cut": 3.0, "order": 4})
    assert filtered.status == "complete"
    output = np.asarray(filtered.result["filtered_signal"])
    spectrum = np.abs(np.fft.rfft(output - output.mean()))
    frequencies = np.fft.rfftfreq(len(output), 0.01)
    amplitude_1 = spectrum[np.argmin(abs(frequencies - 1))]
    amplitude_20 = spectrum[np.argmin(abs(frequencies - 20))]
    assert amplitude_1 > amplitude_20 * 100
    assert np.corrcoef(low, output)[0, 1] > 0.98


def test_bioz_magnitude_and_phase_match_complex_ground_truth():
    run = build_lab_tool_registry().execute("calculate_bioz_features", {"frequency_hz": [10, 100], "real_ohm": [3, 5], "imaginary_ohm": [4, 12], "channel": "ch4"})
    assert run.status == "complete"
    assert run.result["magnitude_ohm"] == pytest.approx([5, 13])
    assert run.result["phase_deg"] == pytest.approx([53.130102, 67.380135], rel=1e-5)
    assert run.result["channel"] == "ch4"


def test_compare_experiments_matches_known_delta_and_rmse():
    run = build_lab_tool_registry().execute("compare_experiments", {"baseline": [10, 10, 10], "comparison": [12, 12, 12], "metric_name": "magnitude_ohm"})
    assert run.status == "complete"
    assert run.result["mean_delta"] == pytest.approx(2)
    assert run.result["relative_change_percent"] == pytest.approx(20)
    assert run.result["rmse"] == pytest.approx(2)

