"""History-grounded report and planning contracts, independent of a web route."""

import json
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .schemas import StrictModel
from .comparison import CompareStoredInput
from .report_narrative import result_narrative


CONDITION_LABELS = {"material": "材料", "posture": "姿态", "activity_condition": "活动条件", "temperature_c": "温度", "device_id": "设备", "electrode_geometry": "电极几何", "sample_rate_hz": "采样率", "frequency_sweep_hz": "扫频频点", "excitation_current": "激励电流", "sop_reference": "SOP"}


class ExperimentHistoryInput(StrictModel):
    experiment_ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def valid_ids(self):
        if any(type(value) is not int or value <= 0 for value in self.experiment_ids) or len(set(self.experiment_ids)) != len(self.experiment_ids):
            raise ValueError("实验编号必须是不同的正整数。")
        return self


class HistoricalRun(StrictModel):
    run_id: str
    status: str
    created_at: str
    result: dict


class HistoricalExperiment(StrictModel):
    experiment_id: int
    name: str
    metadata: dict
    files: list[dict]
    runs: list[HistoricalRun]
    runs_truncated: bool = False
    started_at: str = ""


class HistoryPlanningInput(ExperimentHistoryInput):
    comparison_run_ids: list[str] = Field(default_factory=list, max_length=9)


class ExperimentPlanningInput(StrictModel):
    mode: Literal["history_grounded_rules", "initial_bioz_sweep_rules"] = "history_grounded_rules"
    experiment_ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(default_factory=list, max_length=10)
    comparison_run_ids: list[str] = Field(default_factory=list, max_length=9)
    question: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def scope(self):
        if self.mode == "history_grounded_rules":
            HistoryPlanningInput(experiment_ids=self.experiment_ids, comparison_run_ids=self.comparison_run_ids)
        elif self.experiment_ids or self.comparison_run_ids or not self.question.strip():
            raise ValueError("初始方案必须有明确问题，且不得混入历史实验或比较来源。")
        return self


class DraftSampling(StrictModel):
    status: Literal["requires_confirmation"] = "requires_confirmation"
    adc_sample_rate_hz: None = None
    per_channel_output_rate_hz: None = None
    requirements: list[str] = Field(min_length=1)


class DraftFrequencySweep(StrictModel):
    status: Literal["requires_confirmation"] = "requires_confirmation"
    frequencies_hz: list[float] = Field(default_factory=list, max_length=0)
    settling_time_ms: None = None
    repetitions: None = None
    requirements: list[str] = Field(min_length=1)


class InitialPlanBasis(StrictModel):
    source_kind: Literal["user_request"] = "user_request"
    request_text: str = Field(min_length=1)
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    history_used: Literal[False] = False
    sop_verified: Literal[False] = False


class InitialPlanVariable(StrictModel):
    name: Literal["frequency_sweep_hz", "selected_channels"]
    role: Literal["planned_independent_variable", "planned_scan_dimension"]
    values: list = Field(default_factory=list, max_length=0)
    status: Literal["requires_confirmation"]
    description: str = Field(min_length=1)


class PlanComparison(StrictModel):
    experiment_ids: list[int]
    comparison_run_id: str
    source_run_ids: list[str]
    source_file_ids: list[int]
    calculated_result: dict
    source_refs: list[dict]
    changed_conditions: list[dict] = Field(default_factory=list)
    missing_conditions: list[str] = Field(default_factory=list)


class ExperimentReport(StrictModel):
    experiment_ids: list[int]
    created_at: str
    history: list[HistoricalExperiment]
    source_run_ids: list[str]
    markdown: str
    status: Literal["complete", "partial"]
    limitations: list[str]


class PlanRecommendation(StrictModel):
    action: str
    reason: str
    source_run_ids: list[str]
    source_file_ids: list[int]
    category: Literal["integrity", "data_quality", "analysis", "protocol", "replication", "comparison", "controlled_followup"]


class ExperimentPlan(StrictModel):
    experiment_ids: list[int]
    status: Literal["draft", "needs_evidence"]
    objective: str = Field(min_length=1)
    observations: list[dict]
    recommendations: list[PlanRecommendation]
    unresolved_parameters: list[str]
    approval_required: Literal[True] = True
    mode: Literal["history_grounded_rules", "initial_bioz_sweep_rules"] = "history_grounded_rules"
    limitations: list[str]
    comparisons: list[PlanComparison] = Field(default_factory=list)
    comparison_notes: list[str] = Field(default_factory=list)
    variables: list[dict] = Field(default_factory=list)
    controls: list[str] = Field(default_factory=list)
    quality_checks: list[str] = Field(default_factory=list)
    sample_rate: DraftSampling | None = None
    frequency_sweep: DraftFrequencySweep | None = None
    safety: list[str] = Field(default_factory=list)
    basis: InitialPlanBasis | None = None
    executable: Literal[False] = False

    @model_validator(mode="after")
    def initial_plan_boundary(self):
        if self.mode == "initial_bioz_sweep_rules":
            if self.experiment_ids or self.observations or self.comparisons or self.comparison_notes:
                raise ValueError("初始草案不能声称已读取历史或进行实验比较。")
            if any(item.source_run_ids or item.source_file_ids for item in self.recommendations):
                raise ValueError("初始草案不能伪造历史来源。")
            if not all((self.sample_rate, self.frequency_sweep, self.safety, self.basis, self.controls, self.quality_checks, self.variables, self.unresolved_parameters)):
                raise ValueError("初始草案必须明确方案章节、未知参数与请求来源。")
            variables = [InitialPlanVariable.model_validate(item) for item in self.variables]
            if len(variables) != 2 or {item.name for item in variables} != {"frequency_sweep_hz", "selected_channels"}:
                raise ValueError("初始草案需要扫频与通道两个待确认维度。")
            import hashlib
            if hashlib.sha256(self.basis.request_text.encode()).hexdigest() != self.basis.request_sha256:
                raise ValueError("草案请求来源哈希不一致。")
        return self


def latest_source_run(item: HistoricalExperiment) -> HistoricalRun | None:
    """Comparisons summarize other runs; they are not new acquisition attempts."""
    return next((run for run in item.runs if run.result.get("intent") != "experiment_comparison"), None)


def planning_comparison_inputs(history: list[HistoricalExperiment]) -> tuple[list[CompareStoredInput], list[str]]:
    """Use latest single-experiment analysis, with no guessing of file/channel."""
    if len(history) < 2:
        return [], ["只有一个实验，未生成跨实验差异。"]
    selected = []
    for item in sorted(history, key=lambda item: (item.started_at, item.experiment_id)):
        latest = latest_source_run(item)
        if latest is None or latest.status != "complete":
            return [], [f"实验 {item.experiment_id} 最新分析未完成，先恢复该次分析再比较。"]
        if any(file["integrity"] != "verified" for file in item.files):
            return [], [f"实验 {item.experiment_id} 文件完整性未通过，未自动比较。"]
        result = latest.result
        if "bioz" not in result.get("calculated_result", {}):
            return [], ["自动历史比较目前支持 Bio-Z 幅值；当前历史含其他分析类型，未擅自把信号均值当作脉搏特征。"]
        refs = [ref for ref in result.get("source_refs", []) if "impedance" in ref.get("processing_method", "").lower()]
        channels = {ref.get("channel") for ref in refs}
        hashes = {ref.get("source_sha256") for ref in refs}
        files = [file for file in item.files if file["source_sha256"] in hashes]
        if len(channels) != 1 or None in channels or len(files) != 1:
            return [], [f"实验 {item.experiment_id} 最新结果未唯一确定通道和源文件，请先单独分析目标通道。"]
        selected.append((item, latest, channels.pop(), files[0]["file_id"]))
    baseline, _, channel, baseline_file = selected[0]
    # ch4 and 4 denote the same requested channel; no fuzzy numerical matching.
    import re
    canonical = lambda value: re.sub(r"^(?:ch|channel)[ _-]*", "", value, flags=re.I)
    if any(canonical(item[2]) != canonical(channel) for item in selected):
        return [], ["最新分析选择了不同通道，未自动跨通道比较。"]
    return [CompareStoredInput(experiment_id_1=baseline.experiment_id, experiment_id_2=item.experiment_id, file_id_1=baseline_file, file_id_2=file_id, channel=channel, metric="bioz_magnitude", question="历史 Bio-Z 描述性比较；最早选定实验为参考，不推断因果。") for item, _, _, file_id in selected[1:]], []


def json_block(value):
    # Four-backtick fences keep ordinary triple-backtick notes inert in reports.
    return ["````json", json.dumps(value, ensure_ascii=False, indent=2), "````", ""]


def build_experiment_report(history: list[HistoricalExperiment], created_at: str) -> ExperimentReport:
    limitations = ["本报告汇集历史已保存结果，不重新计算，也不合并不同通道/频点/单位的指标。", "完整性状态只表示生成报告时的检查；历史解释不等于新验证的科学结论。"]
    for item in history:
        if not item.files:
            limitations.append(f"实验 {item.experiment_id} 没有关联原始文件，无法校验来源完整性。")
        if not item.runs:
            limitations.append(f"实验 {item.experiment_id} 没有已保存科学分析。")
        if item.runs_truncated:
            limitations.append(f"实验 {item.experiment_id} 超过 100 次分析；仅汇集最近 100 次。")
        if any(file["integrity"] != "verified" for file in item.files):
            limitations.append(f"实验 {item.experiment_id} 存在缺失或哈希不一致文件；相关历史结果不可视为当前已验证数据。")
    lines = ["# FlexResearch — Experiment History Report", "", f"Snapshot: {created_at}", "", "## Experiment Metadata", ""]
    lines += json_block([{"experiment_id": item.experiment_id, "name": item.name, "metadata": item.metadata} for item in history])
    lines += ["## Data Quality", ""]
    lines += json_block([{"experiment_id": item.experiment_id, "files": item.files} for item in history])
    lines += json_block([{"experiment_id": item.experiment_id, "run_id": run.run_id, "status": run.status, "quality": run.result.get("measured_result", {}).get("data_quality", {}), "cleaning_policy": run.result.get("measured_result", {}).get("cleaning_policy")} for item in history for run in item.runs])
    sections = [("Processing Methods", "source_refs"), ("Measured Result", "measured_result"), ("Calculated Result", "calculated_result")]
    for heading, key in sections:
        lines += [f"## {heading}", ""]
        for item in history:
            for run in item.runs:
                lines += [f"### Experiment {item.experiment_id} · run {run.run_id} · {run.status}", ""]
                lines += json_block(run.result.get(key, {}))
    lines += ["## Agent Interpretation", ""]
    for item in history:
        for run in item.runs:
            lines += [f"### Experiment {item.experiment_id} · run {run.run_id} · {run.status}", "", result_narrative(run.result), "", "运行时解释原文（历史记录，不是额外验证）：", ""]
            lines += json_block(run.result.get("interpretation", ""))
    lines += ["## Figures & Derived Artifacts", ""]
    seen_artifacts = set()
    for item in history:
        for run in item.runs:
            for artifact in run.result.get("artifacts", []):
                url = artifact.get("url", "")
                if url.startswith("/artifacts/") and url not in seen_artifacts:
                    seen_artifacts.add(url)
                    lines += [f"- [Artifact from run {run.run_id}]({url})", ""]
                    lines += json_block(artifact.get("metadata", {}))
    if not seen_artifacts:
        lines += ["No saved figures or derived artifacts.", ""]
    lines += ["## Limitations", ""] + [f"- {text}" for text in limitations] + [""]
    for item in history:
        for run in item.runs:
            lines += json_block({"run_id": run.run_id, "limitations": run.result.get("limitations", []), "signal_quality_limitations": run.result.get("calculated_result", {}).get("signal_quality", {}).get("limitations", []), "stop_reason": run.result.get("stop_reason")})
    lines += ["## Source & Provenance", ""]
    for item in history:
        for run in item.runs:
            lines += [f"- [Experiment {item.experiment_id}: run {run.run_id}](/api/agent-runs/{run.run_id}/report.md)", ""]
            lines += json_block(run.result.get("source_refs", []))
    return ExperimentReport(experiment_ids=[item.experiment_id for item in history], created_at=created_at, history=history, source_run_ids=list(dict.fromkeys(run.run_id for item in history for run in item.runs)), markdown="\n".join(lines), status="partial" if len(limitations) > 2 else "complete", limitations=limitations)


def build_experiment_plan(history: list[HistoricalExperiment], comparisons: list[PlanComparison] | None = None, comparison_notes: list[str] | None = None) -> ExperimentPlan:
    recommendations, observations, unresolved = [], [], []
    for item in history:
        # The latest saved run is authoritative for what was most recently
        # attempted, including failures. Never silently select an older success.
        latest = latest_source_run(item)
        run_ids = [latest.run_id] if latest else []
        file_ids = [file["file_id"] for file in item.files]
        def recommend(category, action, reason):
            recommendations.append(PlanRecommendation(category=category, action=action, reason=reason, source_run_ids=run_ids, source_file_ids=file_ids))
        if not item.files or any(file["integrity"] != "verified" for file in item.files):
            recommend("integrity", f"先核对实验 {item.experiment_id} 的原始文件，暂不据此调整实验条件。", "当前文件缺失或哈希校验未通过。")
            continue
        if latest is None:
            recommend("analysis", f"先为实验 {item.experiment_id} 选择通道并完成分析。", "已有文件，但没有可追溯的科学分析结果。")
            continue
        result = latest.result
        observations.append({"experiment_id": item.experiment_id, "source_run_id": latest.run_id, "status": latest.status, "calculated_result": result.get("calculated_result", {}), "limitations": result.get("limitations", [])})
        quality = result.get("measured_result", {}).get("data_quality", {})
        def has_bad_points(value):
            return isinstance(value, dict) and (any(isinstance(value.get(key), (int, float)) and value[key] > 0 for key in ("nan_count", "inf_count")) or any(has_bad_points(child) for child in value.values()))
        if has_bad_points(quality):
            recommend("data_quality", f"复查实验 {item.experiment_id} 的缺失/非有限值及采集日志，再决定重采或明确清洗策略。", "最新分析的数据质量字段记录了 NaN/Inf；不自动删点。")
        elif latest.status != "complete" or not result.get("calculated_result"):
            recommend("analysis", f"先补齐实验 {item.experiment_id} 最新分析的缺失输入，再继续比较。", "最新运行未完整完成或只有数据概览；具体原因保留在 observations。")
        else:
            recommend("replication", f"以实验 {item.experiment_id} 的已记录条件作为候选基线，先验证重复性，再选择一个待检验变量。", "最新运行有可追溯计算结果且文件校验通过；本建议不宣称统计显著或因果。")
        for parameter in ("sample_rate_hz", "frequency_sweep_hz", "excitation_current", "electrode_geometry", "sop_reference"):
            if item.metadata.get(parameter) in (None, "", []):
                unresolved.append(f"实验 {item.experiment_id}: {parameter}")
        if unresolved and any(value.startswith(f"实验 {item.experiment_id}:") for value in unresolved):
            recommend("protocol", f"补录实验 {item.experiment_id} 的采集协议和 SOP 引用。", "实验元数据缺少一个或多个关键条件；未用通用默认参数填充。")
    comparisons = comparisons or []
    if comparisons:
        # The actual comparison has already selected its reference experiment;
        # don't simultaneously describe every acquisition as another baseline.
        recommendations = [item for item in recommendations if item.category != "replication"]
    variables = []
    for comparison in comparisons:
        values = comparison.calculated_result["comparison"]
        unit = comparison.calculated_result["alignment"]["unit"]
        baseline, after = comparison.experiment_ids
        delta = values["mean_delta"]
        if comparison.changed_conditions or comparison.missing_conditions:
            action = f"复核实验 {baseline} 与 {after} 的条件差异，再做匹配条件的重复测量。"
        else:
            action = f"按实验 {baseline} 与 {after} 已记录的相同条件做独立重复，检查本次幅值差异是否重现。"
        recommendations.append(PlanRecommendation(category="comparison", action=action, reason=f"按共同频点和统一单位计算：幅值均值差 {delta:.6g} {unit}，RMSE {values['rmse']:.6g} {unit}。这些是描述量，不是显著性或因果证据。", source_run_ids=[*comparison.source_run_ids, comparison.comparison_run_id], source_file_ids=comparison.source_file_ids))
        unresolved.extend(comparison.missing_conditions)
        for change in comparison.changed_conditions:
            variables.append({**change, "source_run_ids": [*comparison.source_run_ids, comparison.comparison_run_id], "experiment_ids": comparison.experiment_ids, "status": "observed_condition_difference_not_a_causal_effect"})
        if len(comparison.changed_conditions) == 1 and not comparison.missing_conditions:
            variable = comparison.changed_conditions[0]["name"]
            label = CONDITION_LABELS.get(variable, variable)
            recommendations.append(PlanRecommendation(category="controlled_followup", action=f"验证{label}变化是否可重复，其他已记录条件保持一致。", reason=f"仅{label}这一已检查字段发生变化。经负责人确认后，交错安排参考条件与变化条件的独立重复；重复次数和执行参数由统计设计及 SOP 确定。未记录的因素仍可能造成混杂。", source_run_ids=[*comparison.source_run_ids, comparison.comparison_run_id], source_file_ids=comparison.source_file_ids))
        elif len(comparison.changed_conditions) > 1:
            recommendations.append(PlanRecommendation(category="controlled_followup", action="先固定其他已变化条件，一次只检验一个变量；不要把本次差异归因给其中任一因素。", reason="历史记录同时改变多个条件，存在混杂。", source_run_ids=[*comparison.source_run_ids, comparison.comparison_run_id], source_file_ids=comparison.source_file_ids))
    merged = {}
    for item in recommendations:
        key = (item.category, item.action, item.reason)
        if key in merged:
            merged[key].source_run_ids = list(dict.fromkeys([*merged[key].source_run_ids, *item.source_run_ids]))
            merged[key].source_file_ids = list(dict.fromkeys([*merged[key].source_file_ids, *item.source_file_ids]))
        else:
            merged[key] = item
    recommendations = list(merged.values())
    usable = bool(observations) and not any(item.category in {"integrity", "analysis", "data_quality"} for item in recommendations)
    return ExperimentPlan(experiment_ids=[item.experiment_id for item in history], status="draft" if usable else "needs_evidence", objective="基于指定实验的真实历史结果，确定下一次实验前的证据补齐、质量检查与候选基线。", observations=observations, recommendations=recommendations, unresolved_parameters=list(dict.fromkeys(unresolved)), comparisons=comparisons, comparison_notes=comparison_notes or [], variables=variables, controls=["参考实验只是描述性基线，不自动等同随机对照组。", "匹配通道、频点、器件、电极几何与测量条件；缺失信息须先补齐。", "不自动确定或提高人体激励电流，所有执行参数遵守已审核 SOP。"], quality_checks=["核对原始文件哈希、缺失点和通道映射。", "记录每次重复的接触状态、运动情况和测量顺序。", "独立重复与不确定度评估后，再判断差异是否可重复。"], limitations=["规则驱动的历史比较与审阅草案，不是 LLM 自主实验设计；没有自动执行实验。", "仅在单位、通道、频点验证后比较 Bio-Z；不推荐未经 SOP 审核的人体实验参数。", "建议需由实验负责人确认；不构成临床或因果结论。"])

