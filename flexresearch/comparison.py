"""Stored-experiment comparison with explicit units, alignment and two-source lineage."""

import re
import time
import uuid
from datetime import UTC, datetime
from typing import Literal

import numpy as np
from pydantic import Field, model_validator, field_validator

from .agent import LabAgent, LabAgentResult
from .lab_tools import build_lab_tool_registry
from .schemas import ProvenanceRef, StrictModel
from .tooling import ToolSpec


class CompareStoredInput(StrictModel):
    experiment_id_1: int = Field(gt=0)
    experiment_id_2: int = Field(gt=0)
    file_id_1: int | None = Field(default=None, gt=0)
    file_id_2: int | None = Field(default=None, gt=0)
    channel: str | None = Field(default=None, min_length=1, max_length=80)
    metric: Literal["bioz_magnitude", "signal_mean"] = "bioz_magnitude"
    unit: str | None = Field(default=None, max_length=20)
    question: str = Field(default="比较实验", max_length=1200)

    @field_validator("channel", mode="before", json_schema_input_type=str | int | None)
    @classmethod
    def normalize_channel(cls, value):
        return str(value) if type(value) is int and value >= 0 else value

    @model_validator(mode="after")
    def distinct_experiments(self):
        if self.experiment_id_1 == self.experiment_id_2:
            raise ValueError("比较需要两个不同的实验编号。")
        return self


class CompareStoredOutput(StrictModel):
    experiment_ids: list[int]
    file_ids: list[int]
    measurement_ids: list[int]
    result: LabAgentResult


class DistributionInput(StrictModel):
    baseline: list[float] = Field(min_length=2)
    comparison: list[float] = Field(min_length=2)
    metric_name: str


class DistributionOutput(StrictModel):
    baseline_count: int
    comparison_count: int
    mean_baseline: float
    mean_comparison: float
    mean_delta: float
    relative_change_percent: float | None
    rmse: None = None
    correlation: None = None
    metric_name: str
    alignment: Literal["independent_samples"] = "independent_samples"


def compare_distributions_tool(payload: DistributionInput) -> DistributionOutput:
    one, two = np.asarray(payload.baseline), np.asarray(payload.comparison)
    if not np.all(np.isfinite(one)) or not np.all(np.isfinite(two)):
        raise ValueError("比较数据含 NaN/Inf；未静默删行。")
    a, b = float(one.mean()), float(two.mean())
    return DistributionOutput(baseline_count=len(one), comparison_count=len(two), mean_baseline=a, mean_comparison=b, mean_delta=b-a, relative_change_percent=(b-a)/abs(a)*100 if a else None, metric_name=payload.metric_name)


def unit_scale(unit: str) -> tuple[str, float]:
    units = {"ohm": ("Ω", 1), "ohms": ("Ω", 1), "Ω": ("Ω", 1), "kohm": ("Ω", 1000), "kΩ": ("Ω", 1000), "V": ("V", 1), "mV": ("V", .001), "uV": ("V", .000001), "A": ("A", 1), "mA": ("A", .001), "uA": ("A", .000001), "a.u.": ("a.u.", 1)}
    normalized = unit.strip().replace("µ", "u").replace("μ", "u")
    if normalized not in units:
        raise ValueError(f"不支持或不明确的单位 {unit!r}；请明确 Ω/kΩ、V/mV/uV、A/mA/uA 或 a.u.。")
    return units[normalized]


def column_unit(column: str, metadata: dict, explicit: str | None):
    declared = metadata.get("units", {}).get(column) if isinstance(metadata.get("units"), dict) else None
    suffix = re.search(r"(?:_|\[|\()(kohm|ohms?|kΩ|Ω|uV|mV|V|uA|mA|A)(?:\]|\))?$", column)
    candidates = [str(value) for value in (declared, suffix.group(1) if suffix else None, explicit) if value]
    if not candidates:
        raise ValueError(f"列 {column} 没有单位；请在实验 metadata.units 中注明，或在问题中明确共同单位。")
    resolved = [unit_scale(value) for value in candidates]
    if len(set(resolved)) != 1:
        raise ValueError(f"列 {column} 的单位声明互相冲突，未比较。")
    return resolved[0]


def compare_stored(payload: CompareStoredInput, resolve_csv, output_dir: str) -> CompareStoredOutput:
    started = time.monotonic()
    audit = {key: [] for key in ("trajectory", "refs", "tables", "file_ids", "measurement_ids")}
    try:
        return _compare_stored(payload, resolve_csv, output_dir, audit)
    except ValueError as exc:
        # Retain successful reads and the failed numeric call. A validation
        # failure must not make the already-executed trajectory disappear.
        result = LabAgentResult(
            agent_run_id=uuid.uuid4().hex, status="partial" if audit["trajectory"] else "error",
            intent="experiment_comparison", question=payload.question, trajectory=audit["trajectory"],
            measured_result={"loaded_file_count": len(audit["tables"]), "data_quality": {str(index): table["data_quality"] for index, table in enumerate(audit["tables"])}, "cleaning_policy": "No silent dropping, imputation or interpolation."},
            calculated_result={}, interpretation="比较未完成，未生成差异或医学结论。", limitations=[str(exc)],
            source_refs=audit["refs"], artifacts=[],
            state={"phase": "stopped", "experiment_ids": [payload.experiment_id_1, payload.experiment_id_2], "step_count": len(audit["trajectory"]), "stop_reason": "comparison_validation_failed"},
            stop_reason="comparison_validation_failed", latency_ms=round((time.monotonic()-started)*1000),
        )
        return CompareStoredOutput(experiment_ids=[payload.experiment_id_1, payload.experiment_id_2], file_ids=audit["file_ids"], measurement_ids=audit["measurement_ids"], result=result)


def _compare_stored(payload: CompareStoredInput, resolve_csv, output_dir: str, audit: dict) -> CompareStoredOutput:
    started = time.monotonic()
    registry = build_lab_tool_registry()
    registry.register(ToolSpec("compare_distributions", "Compare means of independent numeric samples; never invent paired RMSE or correlation.", DistributionInput, DistributionOutput, compare_distributions_tool))
    trajectory, refs, tables = audit["trajectory"], audit["refs"], audit["tables"]
    file_ids, measurement_ids = audit["file_ids"], audit["measurement_ids"]
    series, axes, units, artifacts = [], [], [], []
    experiment_ids = [payload.experiment_id_1, payload.experiment_id_2]
    selected_channel = payload.channel

    def execute(name, args):
        step = registry.execute(name, args)
        trajectory.append(step)
        if step.status != "complete" or not step.result:
            raise ValueError(step.error or f"{name} failed")
        return step

    for experiment_id, file_id in zip(experiment_ids, [payload.file_id_1, payload.file_id_2]):
        path, record, metadata = resolve_csv(experiment_id, file_id)
        load = execute("load_csv", {"file_path": str(path)})
        table = load.result
        if table["source_sha256"] != record["sha256"]:
            raise ValueError("文件在读取期间发生变化，SHA-256 不一致。")
        if table["truncated"]:
            raise ValueError("CSV 超过读取行数上限；不使用截断数据比较。")
        file_ids.append(record["id"])
        measurement_ids.append(record["measurement_id"])
        tables.append(table)
        if selected_channel is None:
            if payload.metric == "bioz_magnitude":
                available = [pair[0] for pair in LabAgent._bioz_pairs(table["numeric_columns"])]
            else:
                available = [col for col in table["numeric_columns"] if col.lower() not in {"time", "time_s", "timestamp", "frequency_hz", "freq_hz"}]
            if len(available) != 1:
                raise ValueError("有多个候选通道，请明确通道或列名；未任意选择。")
            selected_channel = available[0]
            numeric_id = re.match(r"^(?:ch|channel)[ _-]*(\d+)(?:_|$)", selected_channel, re.I)
            if numeric_id:
                selected_channel = numeric_id.group(1)
        reference = ProvenanceRef(experiment_id=experiment_id, source_file=table["source_file"], source_sha256=table["source_sha256"], timestamp=datetime.now(UTC).isoformat(), channel=selected_channel, processing_method="Read-only CSV profile", parameters={"file_id": record["id"]}, tool_run_id=load.tool_run_id)
        refs.append(reference)
        channel_id = re.sub(r"^(?:通道|channel|ch)[ _-]*", "", selected_channel, flags=re.I)
        if payload.metric == "bioz_magnitude":
            pairs = [pair for pair in LabAgent._bioz_pairs(table["numeric_columns"]) if re.sub(r"^(?:channel|ch)[ _-]*", "", pair[0], flags=re.I) == channel_id]
            if len(pairs) != 1:
                raise ValueError(f"实验 {experiment_id} 通道 {payload.channel} 的实部/虚部配对不唯一。")
            _, real, imag = pairs[0]
            real_unit, real_scale = column_unit(real, metadata, payload.unit)
            imag_unit, imag_scale = column_unit(imag, metadata, payload.unit)
            if real_unit != "Ω" or imag_unit != "Ω":
                raise ValueError("阻抗比较需要电阻单位，不能把其他量当 Ω。")
            frequency_columns = [col for col in table["numeric_columns"] if col.lower() in {"frequency_hz", "freq_hz", "frequency_khz", "freq_khz"}]
            if len(frequency_columns) != 1:
                raise ValueError("频率列必须明确且唯一：frequency_hz 或 frequency_khz。")
            freq_col = frequency_columns[0]
            frequency = np.asarray(table["data"][freq_col], dtype=float) * (1000 if freq_col.lower().endswith("khz") else 1)
            if not np.all(np.isfinite(frequency)) or np.any(frequency <= 0) or len(np.unique(frequency)) != len(frequency):
                raise ValueError("频点必须为正、有限且不重复；请先明确重复扫频的聚合方法。")
            order = np.argsort(frequency)
            step = execute("calculate_bioz_features", {"frequency_hz": frequency[order].tolist(), "real_ohm": (np.asarray(table["data"][real], dtype=float)[order] * real_scale).tolist(), "imaginary_ohm": (np.asarray(table["data"][imag], dtype=float)[order] * imag_scale).tolist(), "channel": selected_channel})
            values = step.result["magnitude_ohm"]
            axes.append(frequency[order])
            unit = "Ω"
            refs.append(reference.model_copy(update={"tool_run_id": step.tool_run_id, "processing_method": "Complex magnitude after explicit unit normalization and frequency sorting", "parameters": {"real_column": real, "imag_column": imag, "real_to_ohm": real_scale, "imag_to_ohm": imag_scale, "frequency_column": freq_col, "input_tool_run_id": load.tool_run_id}}))
        else:
            candidates = [col for col in table["numeric_columns"] if col == selected_channel or re.fullmatch(rf"(?:ch|channel)[ _-]*{re.escape(channel_id)}(?:_(?:uV|mV|V|uA|mA|A))?", col)]
            if len(candidates) != 1:
                raise ValueError(f"实验 {experiment_id} 必须选择唯一数值列。")
            col = candidates[0]
            unit, factor = column_unit(col, metadata, payload.unit)
            values = (np.asarray(table["data"][col], dtype=float) * factor).tolist()
            refs.append(reference.model_copy(update={"processing_method": "Signal selection and explicit unit normalization", "parameters": {"column": col, "scale_to_canonical_unit": factor, "canonical_unit": unit, "file_id": record["id"], "input_tool_run_id": load.tool_run_id}}))
            axes.append(None)
        series.append(values)
        units.append(unit)
    if units[0] != units[1]:
        raise ValueError("两次实验的物理量单位不一致；未比较。")
    paired = payload.metric == "bioz_magnitude"
    if paired and (len(axes[0]) != len(axes[1]) or not np.allclose(axes[0], axes[1], rtol=1e-9, atol=1e-9)):
        raise ValueError("两次实验频点不一致；未按行错配，也未自动插值。请提供共同频点或明确插值方案。")
    comparison = execute("compare_experiments" if paired else "compare_distributions", {"baseline": series[0], "comparison": series[1], "metric_name": f"{payload.metric} ({units[0]})"})
    for index, table in enumerate(tables):
        refs.append(ProvenanceRef(experiment_id=experiment_ids[index], source_file=table["source_file"], source_sha256=table["source_sha256"], timestamp=datetime.now(UTC).isoformat(), channel=payload.channel, processing_method="Matched-frequency comparison" if paired else "Independent-sample mean comparison", parameters={"role": "baseline" if index == 0 else "comparison", "file_id": file_ids[index], "unit": units[index], "alignment": "sorted_frequency_hz; rtol=atol=1e-9; no interpolation" if paired else "independent_samples; no paired error", "input_tool_run_ids": [step.tool_run_id for step in trajectory[:-1]], "experiment_ids": experiment_ids}, tool_run_id=comparison.tool_run_id))
    if paired and any(term in payload.question.lower() for term in ("画图", "绘图", "plot", "曲线")):
        plot = execute("plot_signal", {"x": axes[0].tolist(), "y": (np.asarray(series[1])-np.asarray(series[0])).tolist(), "output_dir": output_dir, "title": f"Experiment {experiment_ids[1]} minus {experiment_ids[0]}", "x_label": "frequency_hz", "y_label": "magnitude difference (ohm)", "filename_prefix": "experiment-comparison"})
        artifacts.append(plot.result)
        refs.extend(ref.model_copy(update={"tool_run_id": plot.tool_run_id, "processing_method": "Plot aligned magnitude difference", "parameters": {"input_tool_run_id": comparison.tool_run_id, "experiment_ids": experiment_ids}}) for ref in list(refs) if ref.tool_run_id == comparison.tool_run_id)
    result = LabAgentResult(agent_run_id=uuid.uuid4().hex, status="complete", intent="experiment_comparison", question=payload.question, trajectory=trajectory, measured_result={"experiments": [{"experiment_id": identifier, "file_id": file_id, "shape": table["shape"]} for identifier, file_id, table in zip(experiment_ids, file_ids, tables)], "data_quality": {str(identifier): table["data_quality"] for identifier, table in zip(experiment_ids, tables)}, "cleaning_policy": "No silent dropping, imputation or interpolation."}, calculated_result={"comparison": comparison.result, "alignment": {"mode": "matched_frequency" if paired else "independent_samples", "unit": units[0]}}, interpretation="差异来自确定性 Python 工具；不能由单次前后对比推断因果关系或医学结论。", limitations=["描述性比较，不包含统计显著性、因果或临床推断。"], source_refs=refs, artifacts=artifacts, state={"phase": "stopped", "experiment_ids": experiment_ids, "file_ids": file_ids, "channel": payload.channel, "unit": units[0], "step_count": len(trajectory), "stop_reason": "completed"}, stop_reason="completed", latency_ms=round((time.monotonic()-started)*1000))
    result.state["channel"] = selected_channel
    result.calculated_result["alignment"].update({"matched_points": len(series[0]) if paired else None, "unmatched_points": 0 if paired else None})
    result.source_refs = [ref.model_copy(update={"channel": selected_channel}) for ref in refs]
    return CompareStoredOutput(experiment_ids=experiment_ids, file_ids=file_ids, measurement_ids=measurement_ids, result=result)

