import pytest
from pydantic import ValidationError

import app as application
from flexresearch.analysis_context import AnalysisContext, AnalysisGoalRequired, requested_analysis_tasks
from flexresearch.experiment_tools import ExperimentSessionState


@pytest.mark.parametrize("query,tasks", [
    ("继续用刚才的 100 Hz 采样率分析通道 4。", []),
    ("计算通道4均值", ["statistics"]),
    ("分析脉搏主峰", ["spectrum"]),
    ("检查脉搏运动伪差", ["quality"]),
    ("基础统计", ["statistics"]),
    ("分析FFT和均值", ["spectrum", "statistics"]),
])
def test_only_explicit_scientific_goals_are_recognized(query, tasks):
    assert requested_analysis_tasks(query) == tasks


@pytest.mark.parametrize("value", [
    {"tasks": ["diagnosis"]}, {"tasks": ["spectrum", "spectrum"]},
    {"source_run_id": "orphan"}, {"tasks": ["spectrum"], "source_run_id": ""},
])
def test_analysis_context_rejects_unsupported_or_unbound_tasks(value):
    with pytest.raises(ValidationError):
        AnalysisContext.model_validate(value)


def test_old_session_json_is_compatible_but_does_not_invent_a_goal():
    previous = ExperimentSessionState.model_validate({"experiment_id": 3, "file_id": 7, "sample_rate": 100, "channel": "2"})
    assert previous.analysis_context.tasks == []
    with pytest.raises(AnalysisGoalRequired):
        application.experiment_analysis_arguments("继续用刚才的 100 Hz 采样率分析通道 4。", previous)


def test_explicit_new_task_wins_over_previous_goal():
    previous = ExperimentSessionState(experiment_id=3, file_id=7, channel="2", sample_rate=100,
        last_analysis_run_id="prior", analysis_context=AnalysisContext(tasks=["spectrum"]))
    args = application.experiment_analysis_arguments("继续计算通道4均值", previous)
    assert args.analysis_context == AnalysisContext(tasks=["statistics"])
    assert args.channel == "4" and args.sample_rate == 100


@pytest.mark.parametrize("query", ["实验4继续分析通道4", "实验3文件8继续分析通道4"])
def test_goal_does_not_cross_experiment_or_file_scope(query):
    previous = ExperimentSessionState(experiment_id=3, file_id=7, channel="2", sample_rate=100,
        last_analysis_run_id="prior", analysis_context=AnalysisContext(tasks=["spectrum"]))
    with pytest.raises(AnalysisGoalRequired):
        application.experiment_analysis_arguments(query, previous)

