"""Read-only signal profiling and transparent, non-diagnostic quality heuristics."""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import Field, FiniteFloat, RootModel, model_validator

from .schemas import StrictModel
from .iv_analysis import IVCurveInput, IVAnalysisOutput, analyze_iv_curve


class AnalyzeSignalInput(StrictModel):
    signal: list[float | None] = Field(min_length=2, max_length=200_000)
    sample_rate: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    window_samples: int | None = Field(default=None, ge=2, le=200_000, strict=True)
    flat_min_samples: int | None = Field(default=None, ge=2, le=200_000, strict=True)
    jump_mad_multiplier: float = Field(default=12, gt=0, allow_inf_nan=False)
    window_std_multiplier: float = Field(default=4, gt=1, allow_inf_nan=False)
    flat_relative_tolerance: float = Field(default=1e-8, ge=0, le=1e-3, allow_inf_nan=False)
    iv_curve: IVCurveInput | None = None

    @model_validator(mode="after")
    def validate_iv_scope(self):
        if self.iv_curve is not None:
            if len(self.signal) != len(self.iv_curve.voltage):
                raise ValueError("I–V电压和电流必须等长。")
            if any(value is None or not np.isfinite(value) for value in self.signal):
                raise ValueError("I–V电流包含缺失或非有限值；未静默删除。")
            if self.sample_rate is not None or any(getattr(self, name) is not None for name in ("window_samples", "flat_min_samples")):
                raise ValueError("I–V偏压轴不是时间轴，不能混用时域质量参数。")
            if self.jump_mad_multiplier != 12 or self.window_std_multiplier != 4 or self.flat_relative_tolerance != 1e-8:
                raise ValueError("I–V不使用时域质量阈值，不能静默忽略显式修改的参数。")
        return self


class ArtifactInterval(StrictModel):
    start_sample: int
    end_sample_exclusive: int
    start_s: float | None = None
    end_s_exclusive: float | None = None
    reasons: list[Literal["nonfinite", "flat_segment", "abrupt_change", "high_window_variability"]]


class QualityMethod(StrictModel):
    version: Literal["signal-quality-heuristics-v1"] = "signal-quality-heuristics-v1"
    window_samples: int
    flat_min_samples: int
    flat_tolerance: FiniteFloat
    jump_mad_multiplier: FiniteFloat
    jump_threshold: FiniteFloat | None
    window_std_multiplier: FiniteFloat
    window_std_threshold: FiniteFloat | None
    sample_rate: float | None
    axis: Literal["relative_seconds", "sample_index"]
    score_definition: str = "100 * (1 - union_flagged_point_count / total_point_count); not a clinical quality probability"
    finite_policy: str = "Finite-only summary at original indices; no deletion, interpolation, filtering or raw-file changes"
    slope_definition: str = "Least-squares linear slope over finite samples at original indices; drift = slope * full axis span"


class AnalyzeSignalOutput(StrictModel):
    point_count: int
    valid_point_count: int
    nonfinite_count: int
    mean: FiniteFloat | None
    minimum: FiniteFloat | None
    maximum: FiniteFloat | None
    drift: FiniteFloat | None
    slope: FiniteFloat | None
    slope_axis_unit: Literal["second", "sample"]
    quality_score: float = Field(ge=0, le=100)
    flagged_point_count: int
    artifact_intervals: list[ArtifactInterval]
    interval_count: int
    intervals_truncated: bool
    quality_method: QualityMethod
    limitations: list[str]


class SignalAnalysisOutput(RootModel[AnalyzeSignalOutput | IVAnalysisOutput]):
    """Either the original time-signal profile or an explicit-unit I–V result."""


def _runs(mask: np.ndarray):
    """Contiguous true intervals, using half-open original sample indices."""
    changes = np.diff(np.r_[False, mask, False].astype(np.int8))
    return zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1))


def analyze_signal_tool(payload: AnalyzeSignalInput) -> AnalyzeSignalOutput | IVAnalysisOutput:
    if payload.iv_curve is not None:
        return analyze_iv_curve(payload.signal, payload.iv_curve)
    values = np.asarray(payload.signal, dtype=float)
    finite = np.isfinite(values)
    valid = values[finite]
    count = len(values)
    rate = payload.sample_rate
    # These are algorithm defaults, NOT inferred experimental settings.
    window = payload.window_samples or max(2, min(200_000, round(rate) if rate else 100))
    flat_min = payload.flat_min_samples or max(2, min(200_000, round(.2 * rate) if rate else 20))
    masks = {name: np.zeros(count, dtype=bool) for name in ("nonfinite", "flat_segment", "abrupt_change", "high_window_variability")}
    masks["nonfinite"] = ~finite
    scale = float(np.max(np.abs(valid))) if len(valid) else 0.0
    tolerance = max(scale * payload.flat_relative_tolerance, np.finfo(float).eps * max(scale, 1.0))
    differences = np.zeros(count - 1)
    pairs = finite[:-1] & finite[1:]
    with np.errstate(over="raise", invalid="raise"):
        differences[pairs] = values[1:][pairs] - values[:-1][pairs]
        for start, end in _runs(pairs & (np.abs(differences) <= tolerance)):
            if end - start + 1 >= flat_min:
                masks["flat_segment"][start:end + 1] = True
        jump_threshold = None
        if pairs.any():
            median = float(np.median(differences[pairs]))
            mad = float(np.median(np.abs(differences[pairs] - median)))
            jump_threshold = max(payload.jump_mad_multiplier * mad, tolerance)
            masks["abrupt_change"][1:] = pairs & (np.abs(differences - median) > jump_threshold)
        windows = [(start, min(start + window, count)) for start in range(0, count, window)]
        # Only full, finite windows enter the reference distribution. Missing or
        # short windows are not silently filled or compared on unequal support.
        stds = [(start, end, float(np.std(values[start:end], ddof=0))) for start, end in windows if end-start == window and finite[start:end].all()]
        std_threshold = None
        if len(stds) >= 3:
            std_threshold = max(payload.window_std_multiplier * float(np.median([item[2] for item in stds])), tolerance)
            for start, end, std in stds:
                if std > std_threshold:
                    masks["high_window_variability"][start:end] = True
        mean = float(np.mean(valid)) if len(valid) else None
        minimum = float(np.min(valid)) if len(valid) else None
        maximum = float(np.max(valid)) if len(valid) else None
        slope = drift = None
        if len(valid) >= 2:
            x = np.flatnonzero(finite).astype(float) / (rate or 1)
            centered = x - x.mean()
            slope = float(np.dot(centered, valid - mean) / np.dot(centered, centered))
            drift = slope * (count - 1) / (rate or 1)
    union = np.logical_or.reduce(list(masks.values()))
    all_intervals = list(_runs(union))
    intervals = [ArtifactInterval(
        start_sample=int(start), end_sample_exclusive=int(end),
        start_s=float(start/rate) if rate else None, end_s_exclusive=float(end/rate) if rate else None,
        reasons=[name for name, mask in masks.items() if mask[start:end].any()],
    ) for start, end in all_intervals[:500]]
    limitations = [
        "启发式可疑区段，不证明运动伪差、疾病或信号可用；真实生理变化也可能触发。",
        "阈值未经实验室真实标注数据校准；全程噪声或多数窗口受污染时可能漏检。",
        "时间为首样本起算的相对时间；漂移是线性拟合变化量，不是因果解释。",
    ]
    if len(stds) < 3:
        limitations.append("完整且有限的窗口不足 3 个，未执行局部波动比较。")
    if len(all_intervals) > 500:
        limitations.append("仅展示前 500 个可疑区段；计数与未标记比例仍覆盖全部样本。")
    return AnalyzeSignalOutput(
        point_count=count, valid_point_count=int(finite.sum()), nonfinite_count=int((~finite).sum()),
        mean=mean, minimum=minimum, maximum=maximum, slope=slope, drift=drift,
        slope_axis_unit="second" if rate else "sample", quality_score=100 * (1 - float(union.mean())),
        flagged_point_count=int(union.sum()), artifact_intervals=intervals,
        interval_count=len(all_intervals), intervals_truncated=len(all_intervals) > 500,
        quality_method=QualityMethod(window_samples=window, flat_min_samples=flat_min, flat_tolerance=tolerance,
            jump_mad_multiplier=payload.jump_mad_multiplier, jump_threshold=jump_threshold,
            window_std_multiplier=payload.window_std_multiplier, window_std_threshold=std_threshold,
            sample_rate=rate, axis="relative_seconds" if rate else "sample_index"),
        limitations=limitations,
    )

