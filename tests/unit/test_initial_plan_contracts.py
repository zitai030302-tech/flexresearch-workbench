import copy

import pytest
from pydantic import ValidationError

from flexresearch.history import ExperimentPlanningInput, ExperimentPlan
from flexresearch.initial_plan import build_initial_bioz_plan, initial_plan_markdown, is_initial_bioz_plan_request


PROMPT = "为柔性 Bio-Z 多频扫描写一个下一次实验方案草案。"


@pytest.mark.parametrize("query,expected", [
    (PROMPT, True), ("写一份生物阻抗扫频方案", True),
    ("draft a Bio-Z frequency sweep plan", True),
    ("根据实验3结果，为Bio-Z多频扫描写下次方案", False),
    ("根据前3次实验结果建议下一次Bio-Z多频扫描方案", False),
    ("基于刚才的数据写Bio-Z多频扫描方案", False),
    ("根据项目2最近3次实验写Bio-Z扫频方案", False),
    ("帮我找Bio-Z多频扫描方案相关论文", False),
    ("分析Bio-Z多频扫描数据", False),
])
def test_initial_plan_routing_contract(query, expected):
    assert is_initial_bioz_plan_request(query) is expected


@pytest.mark.parametrize("arguments", [
    {}, {"experiment_ids": [1, 1]}, {"experiment_ids": [True]},
    {"mode": "initial_bioz_sweep_rules"},
    {"mode": "initial_bioz_sweep_rules", "question": PROMPT, "experiment_ids": [1]},
    {"mode": "initial_bioz_sweep_rules", "question": PROMPT, "comparison_run_ids": ["invented"]},
])
def test_plan_input_rejects_missing_or_mixed_scope(arguments):
    with pytest.raises(ValidationError):
        ExperimentPlanningInput.model_validate(arguments)


def test_history_input_remains_compatible():
    assert ExperimentPlanningInput(experiment_ids=[1, 2]).mode == "history_grounded_rules"


@pytest.mark.parametrize("mutation", ["history", "numeric", "approval", "hash", "missing_section"])
def test_initial_output_rejects_fabricated_or_incomplete_contract(mutation):
    output = copy.deepcopy(build_initial_bioz_plan(PROMPT).model_dump())
    if mutation == "history":
        output["observations"] = [{"experiment_id": 1, "result": "improved"}]
    elif mutation == "numeric":
        output["sample_rate"]["adc_sample_rate_hz"] = 100
    elif mutation == "approval":
        output["approval_required"] = False
    elif mutation == "hash":
        output["basis"]["request_sha256"] = "0" * 64
    else:
        output["safety"] = []
    with pytest.raises(ValidationError):
        ExperimentPlan.model_validate(output)


def test_complete_draft_has_no_acquisition_values_or_history_claims():
    plan = build_initial_bioz_plan(PROMPT)
    assert plan.experiment_ids == plan.observations == plan.comparisons == []
    assert plan.sample_rate.adc_sample_rate_hz is None
    assert plan.sample_rate.per_channel_output_rate_hz is None
    assert plan.frequency_sweep.frequencies_hz == []
    assert plan.frequency_sweep.settling_time_ms is None
    assert not plan.executable and plan.approval_required
    markdown = initial_plan_markdown(plan)
    for section in ["objective", "variables", "controls", "sample_rate", "frequency_sweep", "quality_checks", "safety", "approval_required", "basis"]:
        assert f"## {section}" in markdown
    assert "未使用历史实验" in markdown
    with pytest.raises(ValueError):
        build_initial_bioz_plan("根据实验3写下次方案")

