"""Deterministic curve features with explicit units and observed endpoints."""

from __future__ import annotations

import re
from typing import Any, Literal

import numpy as np
from pydantic import Field, FiniteFloat, model_validator

from .schemas import StrictModel


class ExtractFeaturesInput(StrictModel):
    kind: Literal["gauge_factor", "cycle_retention"]
    x: list[FiniteFloat] = Field(min_length=2, max_length=200_000)
    y: list[FiniteFloat] = Field(min_length=2, max_length=200_000)
    strain_unit: Literal["percent", "fraction"] | None = None
    baseline_definition: Literal["mean_at_zero_strain", "first_observed_cycle"]
    target_cycle: int | None = Field(default=None, ge=0, strict=True)

    @model_validator(mode="after")
    def check_contract(self):
        if len(self.x) != len(self.y):
            raise ValueError("x and y must have equal length")
        if self.kind == "gauge_factor":
            if self.strain_unit is None or self.baseline_definition != "mean_at_zero_strain" or self.target_cycle is not None:
                raise ValueError("GF requires explicit strain_unit and mean_at_zero_strain baseline")
        elif self.strain_unit is not None or self.baseline_definition != "first_observed_cycle" or self.target_cycle is None:
            raise ValueError("retention requires an explicit target_cycle and first_observed_cycle baseline")
        return self


class ExtractFeaturesOutput(StrictModel):
    kind: Literal["gauge_factor", "cycle_retention"]
    algorithm_version: Literal["curve-features-v1"] = "curve-features-v1"
    point_count: int
    gauge_factor: FiniteFloat | None = None
    retention_percent: FiniteFloat | None = None
    parameters: dict[str, Any]
    limitations: list[str]


def extract_features_tool(payload: ExtractFeaturesInput) -> ExtractFeaturesOutput:
    x, y = np.asarray(payload.x), np.asarray(payload.y)
    if np.any(x < 0) or np.any(np.diff(x) < 0):
        raise ValueError("横轴必须非负且按采集顺序非递减；未排序或混合加载/卸载支路。")
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        if payload.kind == "gauge_factor":
            if not np.any(x == 0) or x[-1] <= 0:
                raise ValueError("GF需要实测零应变基线和正应变端点；未外推或用前几个加载点替代。")
            if np.any(y <= 0):
                raise ValueError("电阻必须为正，不能计算零/负基线GF。")
            baseline_indices = np.flatnonzero(x == 0)
            endpoint_indices = np.flatnonzero(x == x[-1])
            baseline = float(np.mean(y[baseline_indices]))
            endpoint = float(np.mean(y[endpoint_indices]))
            strain = float(x[-1] / (100 if payload.strain_unit == "percent" else 1))
            relative = (endpoint - baseline) / baseline
            return ExtractFeaturesOutput(kind=payload.kind, point_count=len(x), gauge_factor=relative / strain,
                parameters={"strain_unit": payload.strain_unit, "baseline_definition": payload.baseline_definition,
                    "baseline_indices": baseline_indices.tolist(), "baseline_resistance": baseline,
                    "endpoint_indices": endpoint_indices.tolist(), "endpoint_resistance": endpoint,
                    "maximum_strain_input": float(x[-1]), "strain_fraction": strain, "relative_resistance_change": relative},
                limitations=["GF为从实测零应变到最大应变的割线估计，不是局部灵敏度拟合；电阻沿用输入列单位。", "单条加载曲线不证明重复性、迟滞、温漂或器件总体性能。"])
        if np.any(x != np.floor(x)) or len(set(payload.x)) != len(x):
            raise ValueError("循环编号必须是唯一整数；重复周期需先明确聚合协议。")
        matches = np.flatnonzero(x == payload.target_cycle)
        if len(matches) != 1 or payload.target_cycle <= x[0]:
            raise ValueError(f"需要在初始记录之后实测到第{payload.target_cycle}次循环；未插值或以其他末点替代。")
        final_index = int(matches[0])
        if y[0] <= 0 or y[final_index] < 0:
            raise ValueError("保持率需要正的初始响应和非负的目标响应。")
        return ExtractFeaturesOutput(kind=payload.kind, point_count=len(x), retention_percent=float(100 * y[final_index] / y[0]),
            parameters={"baseline_definition": payload.baseline_definition, "target_cycle": payload.target_cycle,
                "initial_point": {"index": 0, "cycle": int(x[0]), "value": float(y[0])},
                "final_point": {"index": final_index, "cycle": payload.target_cycle, "value": float(y[final_index])}},
            limitations=["保持率为目标循环响应/首个实测循环响应×100%；未推断未采集的循环。", "首末比值不证明疲劳寿命或统计显著性，需重复样本与统一测试条件。"])


def feature_kind(question: str) -> str | None:
    if re.search(r"(?<![a-z])gf(?![a-z])|gauge[ -]?factor|应变.*灵敏", question, re.I):
        return "gauge_factor"
    if re.search(r"保持率|retention", question, re.I):
        return "cycle_retention"
    return None


def strain_unit_from_column(column: str) -> str | None:
    name = column.lower()
    if any(token in name for token in ("percent", "%", "pct")):
        return "percent"
    if any(token in name for token in ("fraction", "ratio", "mm/mm", "m/m")):
        return "fraction"
    return None


def feature_arguments(kind: str, data: dict[str, list], question: str, metadata: dict | None = None) -> tuple[dict, dict]:
    metadata = metadata or {}
    x_candidates = [c for c in data if re.search(r"strain|应变" if kind == "gauge_factor" else r"cycle|循环", c, re.I)]
    y_candidates = [c for c in data if c not in x_candidates and (kind != "gauge_factor" or re.search(r"resistance|resist|ohm|电阻", c, re.I))]
    if len(x_candidates) != 1 or len(y_candidates) != 1:
        raise ValueError("请提供唯一横轴与响应列；不会从多通道/多曲线中猜选。")
    x_col, y_col = x_candidates[0], y_candidates[0]
    args = {"kind": kind, "x": data[x_col], "y": data[y_col]}
    if kind == "gauge_factor":
        header_unit = strain_unit_from_column(x_col)
        stored_unit = metadata.get("strain_unit")
        if stored_unit is not None and stored_unit not in {"percent", "fraction"}:
            raise ValueError("strain_unit必须为percent或fraction。")
        if header_unit and stored_unit and header_unit != stored_unit:
            raise ValueError("应变列单位与实验metadata冲突；未计算GF。")
        unit = stored_unit or header_unit
        if unit is None:
            raise ValueError("请在列名或实验metadata明确应变单位percent/fraction；不能根据数值大小猜单位。")
        args.update(strain_unit=unit, baseline_definition="mean_at_zero_strain")
    else:
        targets = re.findall(r"(?:第\s*)?(\d+)\s*(?:次\s*循环|cycles?)", question, re.I)
        if len(set(targets)) != 1:
            raise ValueError("请明确目标循环编号，例如“1000次循环后的保持率”。")
        args.update(target_cycle=int(targets[0]), baseline_definition="first_observed_cycle")
    return args, {"x_column": x_col, "y_column": y_col, "unit_source": "experiment_metadata" if metadata.get("strain_unit") else "column_header" if kind == "gauge_factor" else "cycle_number"}


def iv_differential_resistance(x: np.ndarray, y: np.ndarray, voltage_column: str, current_column: str) -> tuple[float | None, dict]:
    """Near-zero OLS dI/dV, inverted in SI units; no invented unit conversion."""
    def unit_scale(column, scales):
        unit = re.split(r"[_\s(\[]", column.rstrip(")]"))[-1]
        if unit not in scales:
            raise ValueError("I–V列名需明确电压/电流单位，例如voltage_V与current_A。")
        return scales[unit]
    voltage = np.asarray(x, dtype=float) * unit_scale(voltage_column, {"V": 1., "mV": .001})
    current = np.asarray(y, dtype=float) * unit_scale(current_column, {"A": 1., "mA": .001, "uA": 1e-6, "µA": 1e-6, "nA": 1e-9})
    if not np.isfinite(voltage).all() or not np.isfinite(current).all():
        raise ValueError("I–V包含缺失/非有限值；未静默删除后拟合。")
    if len(np.unique(voltage)) != len(voltage):
        raise ValueError("I–V存在重复电压或多个支路，请先明确待拟合曲线。")
    window = float(np.max(np.abs(voltage))) * .1
    selected = np.abs(voltage) <= window + np.finfo(float).eps * max(window, 1e-12)
    v, i = voltage[selected], current[selected]
    if len(v) < 2 or not (np.min(v) <= 0 <= np.max(v)) or np.ptp(v) == 0:
        raise ValueError("近零窗口内需有至少两个不同电压且覆盖零偏；未外推微分电阻。")
    centered = v - v.mean()
    slope = float(np.dot(centered, i - i.mean()) / np.dot(centered, centered))
    resistance = 1 / slope if slope != 0 else None
    if resistance is not None and not np.isfinite(resistance):
        raise ValueError("微分电阻超出有限数值范围。")
    return resistance, {"method": "near-zero OLS dI/dV inverse", "window_half_width_V": window,
        "window_fraction_of_max_abs_bias": .1, "selected_indices": np.flatnonzero(selected).tolist(),
        "point_count": len(v), "conductance_S": slope, "output_unit": "ohm"}

