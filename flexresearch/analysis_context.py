"""Explicit, scoped analysis goals; never infer a scientific task from fs alone."""

import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .schemas import StrictModel


class AnalysisContext(StrictModel):
    tasks: list[Literal["spectrum", "statistics", "quality"]] = Field(default_factory=list, max_length=3)
    source_run_id: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("tasks")
    @classmethod
    def unique_tasks(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("分析目标不能重复。")
        return value

    @model_validator(mode="after")
    def source_has_task(self):
        if self.source_run_id and not self.tasks:
            raise ValueError("分析目标来源不能脱离明确目标。")
        return self


class AnalysisGoalRequired(ValueError):
    """A continuation lacks a successful scoped task to continue."""
    field = "analysis_goal"


class AnalysisProcessingRequired(AnalysisGoalRequired):
    """Continuing a goal must not silently drop a previous filter."""
    field = "analysis_parameters.filter"


def requested_analysis_tasks(query: str) -> list[str]:
    query = query.lower()
    quality = any(term in query for term in ("伪差", "异常", "质量", "artifact", "quality", "基础统计"))
    statistics = any(term in query for term in ("均值", "平均", "统计", "mean", "statistics"))
    spectrum = any(term in query for term in ("fft", "frequency", "频率", "峰值", "主峰", "peak")) or (
        not quality and any(term in query for term in ("脉搏", "pulse", "脉率", "心率", "bpm", "heart rate"))
    )
    # Statistics already includes the quality tool; do not save a duplicate goal.
    return [name for name, needed in (("spectrum", spectrum), ("statistics", statistics), ("quality", quality and not statistics)) if needed]


def requests_analysis_continuation(query: str) -> bool:
    continuation = re.search(r"继续|刚才|同样|换到|改成|改为|上次|上一轮", query)
    analysis = re.search(r"分析|计算|\banaly[sz]e\b", query, re.I)
    explicit_other_action = re.search(r"比较|对比|微分电阻|保持率|应变|\b(?:compare|gf)\b", query, re.I)
    return bool(continuation and analysis and not explicit_other_action)


def successful_analysis_context(result) -> AnalysisContext:
    """Persist goals only after their actual numeric outputs succeeded."""
    context = AnalysisContext.model_validate(result.state.get("analysis_context") or {})
    outputs = {"spectrum": "spectrum", "statistics": "statistics", "quality": "signal_quality"}
    if result.status != "complete" or not all(outputs[task] in result.calculated_result for task in context.tasks):
        return AnalysisContext()
    return context

