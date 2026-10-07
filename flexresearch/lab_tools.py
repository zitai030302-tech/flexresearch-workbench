"""Deterministic scientific tools. LLMs never perform these calculations."""

from __future__ import annotations

import hashlib
import csv
import math
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import butter, find_peaks, sosfiltfilt

from .schemas import (
    BioZFeaturesInput,
    BioZFeaturesOutput,
    ColumnQuality,
    ColumnStats,
    CompareExperimentsInput,
    CompareExperimentsOutput,
    FilterSignalInput,
    FilterSignalOutput,
    ExportSignalInput,
    ExportSignalOutput,
    LoadCSVInput,
    LoadCSVOutput,
    PlotSignalInput,
    PlotSignalOutput,
    SpectralAnalysisInput,
    SpectralAnalysisOutput,
    SpectralPeak,
)
from .tooling import ToolRegistry, ToolSpec
from .signal_quality import AnalyzeSignalInput, SignalAnalysisOutput, analyze_signal_tool
from .curve_features import ExtractFeaturesInput, ExtractFeaturesOutput, extract_features_tool
from .csv_input import read_csv_bytes


MAX_CSV_BYTES = 64 * 1024 * 1024


def _finite(values: list[float], label: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{label} contains NaN or infinite values")
    return array


def load_csv_tool(payload: LoadCSVInput) -> LoadCSVOutput:
    path = Path(payload.file_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"CSV file does not exist: {path.name}")
    if path.suffix.lower() != ".csv":
        raise ValueError("load_csv accepts .csv files only")
    if path.stat().st_size > MAX_CSV_BYTES:
        raise ValueError("CSV exceeds the 64 MiB tool limit")
    raw = path.read_bytes()
    if len(raw) > MAX_CSV_BYTES:
        raise ValueError("CSV exceeds the 64 MiB tool limit")
    try:
        frame = read_csv_bytes(raw, nrows=payload.max_rows + 1)
    except (UnicodeDecodeError, csv.Error, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError(f"CSV parsing failed: {type(exc).__name__}") from exc
    if frame.empty or not len(frame.columns):
        raise ValueError("CSV contains no data rows")
    truncated = len(frame) > payload.max_rows
    frame = frame.iloc[: payload.max_rows].copy()
    numeric = frame.select_dtypes(include=np.number)
    stats: dict[str, ColumnStats] = {}
    quality: dict[str, ColumnQuality] = {}
    for column in numeric.columns:
        values = pd.to_numeric(numeric[column], errors="coerce")
        finite_mask = np.isfinite(values)
        finite = values[finite_mask]
        nan_count = int(values.isna().sum())
        inf_count = int(np.isinf(values.to_numpy(dtype=float, na_value=np.nan)).sum())
        stats[str(column)] = ColumnStats(
            count=int(finite.count()),
            mean=float(finite.mean()) if len(finite) else None,
            std=float(finite.std(ddof=0)) if len(finite) else None,
            minimum=float(finite.min()) if len(finite) else None,
            maximum=float(finite.max()) if len(finite) else None,
        )
        quality[str(column)] = ColumnQuality(
            total_points=len(values),
            valid_points=int(finite_mask.sum()),
            nan_count=nan_count,
            inf_count=inf_count,
            finite_fraction=float(finite_mask.sum() / len(values)) if len(values) else 0.0,
        )
    json_frame = frame.astype(object).where(pd.notna(frame), None)
    return LoadCSVOutput(
        shape=(len(frame), len(frame.columns)),
        columns=[str(column) for column in frame.columns],
        numeric_columns=[str(column) for column in numeric.columns],
        missing_counts={str(column): int(count) for column, count in frame.isna().sum().items()},
        basic_stats=stats,
        data_quality=quality,
        cleaning_policy="Profile only: NaN and infinite values are reported, never silently imputed or dropped before a scientific tool call.",
        data={str(column): json_frame[column].tolist() for column in frame.columns},
        truncated=truncated,
        source_file=str(path),
        source_sha256=hashlib.sha256(raw).hexdigest(),
    )


def filter_signal_tool(payload: FilterSignalInput) -> FilterSignalOutput:
    signal = _finite(payload.signal, "signal")
    if len(signal) <= 3 * (2 * payload.order + 1):
        raise ValueError("signal is too short for stable zero-phase filtering")
    nyquist = payload.sample_rate / 2
    if payload.low_cut is not None and payload.high_cut is not None:
        cutoff: float | list[float] = [payload.low_cut / nyquist, payload.high_cut / nyquist]
        kind = "bandpass"
    elif payload.low_cut is not None:
        cutoff, kind = payload.low_cut / nyquist, "highpass"
    else:
        cutoff, kind = float(payload.high_cut) / nyquist, "lowpass"
    sos = butter(payload.order, cutoff, btype=kind, output="sos")
    filtered = sosfiltfilt(sos, signal)
    return FilterSignalOutput(filtered_signal=filtered.tolist(), parameters={"sample_rate": payload.sample_rate, "low_cut": payload.low_cut, "high_cut": payload.high_cut, "order": payload.order, "filter": f"Butterworth {kind} zero-phase"}, point_count=len(filtered))


def spectral_analysis_tool(payload: SpectralAnalysisInput) -> SpectralAnalysisOutput:
    signal = _finite(payload.signal, "signal")
    centered = signal - float(np.mean(signal))
    if payload.estimate_pulse_rate and np.ptp(signal) <= np.finfo(float).eps * np.max(np.abs(signal)):
        raise ValueError("信号无可分辨变化，不能从常量信号估计脉率。")
    frequencies = np.fft.rfftfreq(len(centered), d=1 / payload.sample_rate)
    amplitudes = 2 * np.abs(np.fft.rfft(centered)) / len(centered)
    upper = payload.max_frequency if payload.max_frequency is not None else payload.sample_rate / 2
    mask = (frequencies >= payload.min_frequency) & (frequencies <= upper)
    candidate_indices = np.where(mask)[0]
    if not len(candidate_indices):
        raise ValueError("frequency bounds contain no FFT bins")
    local_peaks, _ = find_peaks(amplitudes[candidate_indices])
    indexes = candidate_indices[local_peaks]
    if not len(indexes):
        indexes = np.array([candidate_indices[int(np.argmax(amplitudes[candidate_indices]))]])
    ranked = indexes[np.argsort(amplitudes[indexes])[::-1]][: payload.max_peaks]
    peaks = [SpectralPeak(frequency_hz=float(frequencies[index]), amplitude=float(amplitudes[index])) for index in ranked]
    dominant = peaks[0].frequency_hz if peaks else None
    pulse_rate = dominant * 60 if payload.estimate_pulse_rate and dominant is not None and dominant > 0 else None
    return SpectralAnalysisOutput(peaks=peaks, dominant_frequency_hz=dominant, frequency_resolution_hz=float(payload.sample_rate / len(signal)), sample_rate=payload.sample_rate, point_count=len(signal), pulse_rate_bpm=pulse_rate, pulse_rate_method="dominant-frequency-hz-times-60-v1" if pulse_rate is not None else None)


def calculate_bioz_features_tool(payload: BioZFeaturesInput) -> BioZFeaturesOutput:
    frequency = _finite(payload.frequency_hz, "frequency_hz")
    real = _finite(payload.real_ohm, "real_ohm")
    imaginary = _finite(payload.imaginary_ohm, "imaginary_ohm")
    if np.any(frequency <= 0):
        raise ValueError("frequency_hz must be positive")
    magnitude = np.hypot(real, imaginary)
    phase = np.degrees(np.arctan2(imaginary, real))
    return BioZFeaturesOutput(
        frequency_hz=frequency.tolist(), magnitude_ohm=magnitude.tolist(), phase_deg=phase.tolist(),
        magnitude_mean_ohm=float(np.mean(magnitude)), magnitude_std_ohm=float(np.std(magnitude)),
        phase_mean_deg=float(np.mean(phase)), frequency_min_hz=float(np.min(frequency)), frequency_max_hz=float(np.max(frequency)),
        point_count=len(frequency), channel=payload.channel,
        quality_metrics={"finite_fraction": 1.0, "frequency_monotonic": "yes" if bool(np.all(np.diff(frequency) >= 0)) else "no", "duplicate_frequency_count": int(len(frequency) - len(np.unique(frequency)))},
    )


def plot_signal_tool(payload: PlotSignalInput) -> PlotSignalOutput:
    x = _finite(payload.x, "x")
    y = _finite(payload.y, "y")
    output_dir = Path(payload.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_prefix = re.sub(r"[^A-Za-z0-9._-]+", "-", payload.filename_prefix).strip("-.") or "signal"
    target = output_dir / f"{safe_prefix}-{uuid.uuid4().hex[:10]}.png"
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["font.family"] = ["Arial Unicode MS", "Hiragino Sans GB", "DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    from matplotlib import pyplot as plt
    figure, axis = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
    axis.plot(x, y, linewidth=1.4)
    axis.set(title=payload.title, xlabel=payload.x_label, ylabel=payload.y_label)
    axis.grid(alpha=0.25)
    figure.savefig(target, dpi=160)
    plt.close(figure)
    metadata: dict[str, str | int] = {
        "title": payload.title,
        "x_label": payload.x_label,
        "y_label": payload.y_label,
        "point_count": len(x),
        "format": "png",
        "algorithm_version": "matplotlib-line-v1",
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }
    if payload.source_sha256:
        metadata["parent_source_sha256"] = payload.source_sha256
    return PlotSignalOutput(plot_path=str(target), metadata=metadata)


def compare_experiments_tool(payload: CompareExperimentsInput) -> CompareExperimentsOutput:
    baseline = _finite(payload.baseline, "baseline")
    comparison = _finite(payload.comparison, "comparison")
    delta = comparison - baseline
    baseline_mean, comparison_mean = float(np.mean(baseline)), float(np.mean(comparison))
    relative = (comparison_mean - baseline_mean) / abs(baseline_mean) * 100 if baseline_mean else None
    correlation = float(np.corrcoef(baseline, comparison)[0, 1]) if np.std(baseline) > 0 and np.std(comparison) > 0 else None
    return CompareExperimentsOutput(point_count=len(baseline), mean_baseline=baseline_mean, mean_comparison=comparison_mean, mean_delta=float(np.mean(delta)), relative_change_percent=relative, rmse=float(math.sqrt(float(np.mean(delta ** 2)))), correlation=correlation, metric_name=payload.metric_name)


def export_signal_tool(payload: ExportSignalInput) -> ExportSignalOutput:
    """Write a new numeric CSV only; source integrity and lineage are explicit."""
    axis = _finite(payload.x, "axis")
    signal = _finite(payload.signal, "signal")
    source = Path(payload.source_file).expanduser().resolve()
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != payload.source_sha256:
        raise ValueError("Source SHA-256 changed or source is missing; no derived CSV exported.")
    directory = Path(payload.output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"filtered-signal-{uuid.uuid4().hex}.csv"
    # Exclusive creation prevents overwrite even if a filename is ever reused.
    frame = pd.DataFrame({payload.axis_name: axis, "filtered_signal": signal})
    frame.to_csv(target, index=False, mode="x", float_format="%.17g")
    metadata = {
        "format": "csv", "point_count": len(signal), "columns": list(frame.columns),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "parent_source_sha256": payload.source_sha256,
        "source_file": source.name, "channel": payload.channel,
        "experiment_id": payload.experiment_id,
        "input_tool_run_id": payload.input_tool_run_id,
        "processing_method": "Export validated filtered signal without resampling",
        "processing_parameters": payload.processing_parameters,
        "created_at": datetime.now(UTC).isoformat(),
    }
    return ExportSignalOutput(file_path=str(target), metadata=metadata)


def build_lab_tool_registry(observer=None) -> ToolRegistry:
    registry = ToolRegistry(observer=observer)
    registry.register(ToolSpec("extract_features", "Calculate GF from observed zero-strain resistance and explicit strain units, or retention at an explicitly measured target cycle; never extrapolate missing endpoints.", ExtractFeaturesInput, ExtractFeaturesOutput, extract_features_tool, 10))
    registry.register(ToolSpec("load_csv", "Read a CSV without modifying it and return schema, missingness, numeric statistics and data.", LoadCSVInput, LoadCSVOutput, load_csv_tool, 10))
    registry.register(ToolSpec("analyze_signal", "Profile raw time-signal statistics/quality, or calculate zero-bias differential resistance when explicit-unit iv_curve is supplied; no medical diagnosis.", AnalyzeSignalInput, SignalAnalysisOutput, analyze_signal_tool, 10))
    registry.register(ToolSpec("filter_signal", "Apply a validated zero-phase Butterworth filter to a numeric signal.", FilterSignalInput, FilterSignalOutput, filter_signal_tool, 10))
    registry.register(ToolSpec("spectral_analysis", "Calculate deterministic FFT peaks from a signal and sample rate.", SpectralAnalysisInput, SpectralAnalysisOutput, spectral_analysis_tool, 10))
    registry.register(ToolSpec("calculate_bioz_features", "Calculate Bio-Z magnitude, phase, ranges and quality metrics from real/imaginary impedance.", BioZFeaturesInput, BioZFeaturesOutput, calculate_bioz_features_tool, 10))
    registry.register(ToolSpec("plot_signal", "Create a new PNG plot artifact without modifying the source data.", PlotSignalInput, PlotSignalOutput, plot_signal_tool, 20))
    registry.register(ToolSpec("compare_experiments", "Compare equal-length baseline and follow-up numeric series.", CompareExperimentsInput, CompareExperimentsOutput, compare_experiments_tool, 10))
    registry.register(ToolSpec("export_signal", "Save validated filtered values in a new CSV with source hash and processing lineage; never overwrite raw data.", ExportSignalInput, ExportSignalOutput, export_signal_tool, 10))
    return registry

