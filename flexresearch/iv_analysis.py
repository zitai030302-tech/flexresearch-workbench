"""Explicit-unit I–V analysis; never interpret a voltage sweep as elapsed time."""

import re
from typing import Any, Literal

import numpy as np
from pydantic import Field, FiniteFloat

from .curve_features import iv_differential_resistance
from .schemas import StrictModel


class IVCurveInput(StrictModel):
    voltage: list[FiniteFloat] = Field(min_length=2, max_length=200_000)
    voltage_column: str = Field(min_length=1)
    current_column: str = Field(min_length=1)


class IVAnalysisOutput(StrictModel):
    analysis_kind: Literal["iv_differential_resistance"] = "iv_differential_resistance"
    algorithm_version: Literal["iv-zero-bias-ols-v1"] = "iv-zero-bias-ols-v1"
    point_count: int
    differential_resistance_ohm: FiniteFloat | None
    parameters: dict[str, Any]
    limitations: list[str]


def is_iv_request(question: str) -> bool:
    return bool(re.search(r"零偏.*(?:电阻|resistance)|微分电阻|differential\s+resistance|zero[ -]?bias\s+resistance", question, re.I))


def iv_arguments(data: dict[str, list], question: str, channel: str | None = None) -> dict:
    if channel is not None:
        raise ValueError("I–V需要唯一电压/电流列；请先明确电流通道并拆分曲线，未猜选通道。")
    if re.search(r"滤波|去噪|带通|高通|低通|\bfilter", question, re.I):
        raise ValueError("零偏电阻使用原始I–V曲线；不能忽略额外滤波要求，请先明确处理协议。")
    voltage = [name for name in data if re.search(r"voltage|电压|偏压", name, re.I)]
    current = [name for name in data if re.search(r"current|电流", name, re.I)]
    if len(voltage) != 1 or len(current) != 1 or voltage[0] == current[0]:
        raise ValueError("需要唯一且带单位的电压/电流列，例如voltage_V与current_mA；未从多曲线猜选。")
    return {"signal": data[current[0]], "iv_curve": {
        "voltage": data[voltage[0]], "voltage_column": voltage[0], "current_column": current[0]}}


def analyze_iv_curve(signal: list[float | None], curve: IVCurveInput) -> IVAnalysisOutput:
    resistance, parameters = iv_differential_resistance(
        np.asarray(curve.voltage, dtype=float), np.asarray(signal, dtype=float),
        curve.voltage_column, curve.current_column,
    )
    return IVAnalysisOutput(point_count=len(signal), differential_resistance_ohm=resistance,
        parameters={**parameters, "voltage_column": curve.voltage_column, "current_column": curve.current_column,
            "unit_source": "explicit_column_headers", "input": "raw I-V curve"},
        limitations=["微分电阻是所列近零偏窗口内OLS电导的倒数，不是任意偏压下的精确导数。",
            "窗口为最大绝对实测偏压的10%；未执行滤波、删除缺失值、外推或合并重复电压支路。",
            "单次曲线不证明器件总体性能、重复性或医学结论。"] +
            (["拟合电导为零，没有有限微分电阻；未把无穷大写为一个数值。"] if resistance is None else []))

