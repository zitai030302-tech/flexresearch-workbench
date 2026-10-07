"""Validated processing settings; no raw arrays or implicit scientific defaults."""

import re

from pydantic import Field, model_validator

from .schemas import StrictModel


class FilterParameters(StrictModel):
    low_cut: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    high_cut: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    order: int = Field(default=4, ge=1, le=10, strict=True)

    @model_validator(mode="after")
    def valid_band(self):
        if self.low_cut is None and self.high_cut is None:
            raise ValueError("请明确滤波截止频率。")
        if self.low_cut is not None and self.high_cut is not None and self.low_cut >= self.high_cut:
            raise ValueError("带通下限必须小于上限。")
        return self


class AnalysisParameters(StrictModel):
    filter: FilterParameters | None = None
    parameter_source_run_id: str | None = Field(default=None, min_length=1, max_length=100)


def requests_raw_signal(query: str) -> bool:
    return bool(re.search(r"不(?:再)?滤波|不用滤波|取消滤波|原始(?:信号|数据)|\braw\s+(?:signal|data)\b", query, re.I))


def requests_filter_reuse(query: str) -> bool:
    return bool(re.search(r"沿用|同样(?:的)?参数|(?:刚才|上次|之前|相同|上一轮)(?:的)?(?:滤波|参数)|继续滤波", query))


def is_parameter_only_reply(query: str) -> bool:
    """Only a short numeric clarification can resume a stored pending task."""
    if len(query) > 200 or not re.search(r"\d", query):
        return False
    tokens = r"采样率|sample\s*rate|fs|截止频率|截止|参数|补充|继续|使用|采用|按照|改为|改成|请|按|用|为|是|带通|低通|高通|滤波|bandpass|lowpass|highpass|filter|order|阶|赫兹|hz|[0-9eE.+,，。:：=~～–—/\s-]"
    return bool(re.fullmatch(rf"(?:{tokens})+", query, re.I))


def requests_signal_export(query: str, *, filtering: bool) -> bool:
    if re.search(r"不(?:要|用)?(?:再)?\s*(?:导出|保存|下载)|do not (?:export|save)", query, re.I):
        return False
    action = re.search(r"导出|保存|下载|export|save", query, re.I)
    return bool(action and ("csv" in query.lower() or (filtering and re.search(r"保存(?:处理)?结果|保存(?:滤波后|滤波)结果", query))))


def without_sample_rate(query: str) -> str:
    number = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
    text = re.sub(r"(?:采样率|sample\s*rate|\bfs)\s*(?:是|为|=|:|：)?\s*" + number + r"\s*(?:[km]?hz|赫兹)", "", query, flags=re.I)
    return re.sub(number + r"\s*(?:[km]?hz|赫兹)\s*(?:的)?采样率", "", text, flags=re.I)


def parse_filter_parameters(query: str) -> FilterParameters | None:
    """Parse explicit Hz cutoffs, never mistake a sampling rate for a cutoff."""
    if requests_raw_signal(query):
        return None
    text = query.lower()
    if not re.search(r"滤波|去噪|带通|低通|高通|filter|bandpass|lowpass|highpass|low-pass|high-pass", text):
        return None
    number = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
    text = without_sample_rate(text)
    order_match = re.search(r"(\d+)\s*阶|(?:order)\s*[=:]?\s*(\d+)", text)
    order = int(next(value for value in order_match.groups() if value)) if order_match else 4
    band = re.search(rf"({number})\s*(?:hz|赫兹)?\s*(?:[-–—~～]|到|至)\s*({number})\s*(?:hz|赫兹)", text)
    if band:
        return FilterParameters(low_cut=float(band[1]), high_cut=float(band[2]), order=order)
    kinds = [kind for kind, pattern in (("low", r"低通|low-?pass"), ("high", r"高通|high-?pass")) if re.search(pattern, text)]
    cutoffs = re.findall(rf"(?<![a-z0-9.+-])({number})\s*(?:hz|赫兹)", text)
    if len(kinds) == 1 and len(cutoffs) == 1:
        return FilterParameters(**{"high_cut" if kinds[0] == "low" else "low_cut": float(cutoffs[0])}, order=order)
    return None

