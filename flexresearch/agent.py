"""A small, stateful, deterministic laboratory tool orchestrator."""

from __future__ import annotations

import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from .schemas import ProvenanceRef
from .analysis_parameters import AnalysisParameters, parse_filter_parameters, requests_raw_signal, requests_signal_export
from .analysis_context import AnalysisContext, requested_analysis_tasks
from .tooling import ToolExecution, ToolRegistry
from .iv_analysis import is_iv_request, iv_arguments


class LabAgentResult(BaseModel):
    agent_run_id: str
    status: str
    intent: str
    question: str
    trajectory: list[ToolExecution]
    measured_result: dict[str, Any] = Field(default_factory=dict)
    calculated_result: dict[str, Any] = Field(default_factory=dict)
    interpretation: str
    limitations: list[str] = Field(default_factory=list)
    source_refs: list[ProvenanceRef] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    state: dict[str, Any] = Field(default_factory=dict)
    stop_reason: str
    latency_ms: int
    clarification_fields: list[str] = Field(default_factory=list)


class LabAgentState(BaseModel):
    """Serializable execution state used for persistence, replay and eval."""

    phase: Literal["planning", "acting", "observing", "stopped", "failed"]
    step_count: int = 0
    max_steps: int = 40
    source_file: str
    selected_columns: dict[str, str | None] = Field(default_factory=dict)
    sample_rate: float | None = None
    analysis_parameters: AnalysisParameters = Field(default_factory=AnalysisParameters)
    analysis_context: AnalysisContext = Field(default_factory=AnalysisContext)
    completed_tools: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    stop_reason: str | None = None


class LabAgent:
    """Choose validated numeric tools, observe results, and stop explicitly.

    This runtime is intentionally deterministic. The LLM may explain a validated
    result later, but it never computes FFT, filters, impedance or statistics.
    """

    def __init__(self, registry: ToolRegistry, *, max_steps: int = 40) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        self.registry = registry
        self.max_steps = max_steps

    def analyze_csv(
        self,
        file_path: str,
        question: str = "",
        sample_rate: float | None = None,
        output_dir: str | None = None,
        experiment_id: int | None = None,
        channel: str | None = None,
        analysis_parameters: AnalysisParameters | None = None,
        analysis_context: AnalysisContext | None = None,
        expected_source_sha256: str | None = None,
    ) -> LabAgentResult:
        started = time.monotonic()
        run_id = uuid.uuid4().hex
        trajectory: list[ToolExecution] = []
        load = self.registry.execute("load_csv", {"file_path": file_path})
        trajectory.append(load)
        if load.status != "complete" or not load.result:
            return self._failed(run_id, question, trajectory, load.error or "CSV load failed", started, self.max_steps)
        table = load.result
        if expected_source_sha256 is not None and table["source_sha256"] != expected_source_sha256:
            return self._failed(run_id, question, trajectory, "读取字节与实验归档SHA-256不一致，未执行计算。", started, self.max_steps)
        numeric = table["numeric_columns"]
        measured = {
            "shape": table["shape"],
            "columns": table["columns"],
            "missing_counts": table["missing_counts"],
            "data_quality": table["data_quality"],
            "cleaning_policy": table["cleaning_policy"],
        }
        source_refs = [
            self._provenance(
                table,
                load,
                experiment_id=experiment_id,
                method="CSV parse and profile",
                parameters={"max_rows": load.arguments.get("max_rows", 200_000)},
            )
        ]
        normalized_columns = {column.lower(): column for column in numeric}
        frequency_col = self._find_column(normalized_columns, ("frequency", "freq", "hz"))
        real_col = self._find_column(normalized_columns, ("real", "resistance", "z_real", "re_z"))
        imag_col = self._find_column(normalized_columns, ("imag", "reactance", "z_imag", "im_z"))
        bioz_pairs = self._bioz_pairs(numeric) if frequency_col else []
        requested_channel = re.sub(r"^(?:通道|channel|ch)[ _-]*", "", (channel or "").strip(), flags=re.I)
        if channel is not None and bioz_pairs:
            bioz_pairs = [pair for pair in bioz_pairs if re.sub(r"^(?:channel|ch)[ _-]*", "", pair[0], flags=re.I) == requested_channel]
            if not bioz_pairs:
                return self._failed(run_id, question, trajectory, f"未找到通道 {channel} 的实部/虚部配对。", started, self.max_steps)
        if bioz_pairs:
            _, real_col, imag_col = bioz_pairs[0]
        time_col = self._find_column(normalized_columns, ("time", "timestamp", "second", "sec"))
        state = LabAgentState(
            phase="acting",
            step_count=1,
            max_steps=self.max_steps,
            source_file=table["source_file"],
            selected_columns={"frequency": frequency_col, "real": real_col, "imaginary": imag_col, "time": time_col},
            completed_tools=["load_csv"],
        )
        if is_iv_request(question):
            return self._analyze_iv(table, load, measured, state, run_id, question, started,
                trajectory, source_refs, experiment_id, channel, output_dir)
        query = question.lower()
        calculated: dict[str, Any] = {"basic_stats": table["basic_stats"]}
        artifacts: list[dict[str, Any]] = []
        limitations: list[str] = []
        clarification_fields: list[str] = []
        intent = "data_profile"
        if frequency_col and bioz_pairs:
            intent = "bioz_multichannel" if len(bioz_pairs) > 1 else "bioz_features"
            channel_summaries: dict[str, Any] = {}
            for channel, channel_real, channel_imag in bioz_pairs[:32]:
                execution = self._execute(state, "calculate_bioz_features", {"frequency_hz": table["data"][frequency_col], "real_ohm": table["data"][channel_real], "imaginary_ohm": table["data"][channel_imag], "channel": channel})
                trajectory.append(execution)
                if execution.status == "complete" and execution.result:
                    if "bioz" not in calculated:
                        calculated["bioz"] = execution.result
                    channel_summaries[channel] = {key: value for key, value in execution.result.items() if key not in {"frequency_hz", "magnitude_ohm", "phase_deg"}}
                    source_refs.append(self._provenance(table, execution, experiment_id=experiment_id, channel=channel, method="Complex impedance magnitude and phase", parameters={"frequency_column": frequency_col, "real_column": channel_real, "imaginary_column": channel_imag}))
                else:
                    limitations.append(f"{channel}: {execution.error or 'Bio-Z feature calculation failed'}")
            if len(bioz_pairs) > 1:
                calculated["bioz_channels"] = channel_summaries
        explicit_tasks = requested_analysis_tasks(question)
        state.analysis_context = AnalysisContext(tasks=explicit_tasks) if explicit_tasks else (analysis_context or AnalysisContext())
        tasks = state.analysis_context.tasks
        wants_quality = "quality" in tasks or "基础统计" in query
        wants_statistics = "statistics" in tasks
        wants_frequency = "spectrum" in tasks
        bioz_columns = {column for _, channel_real, channel_imag in self._bioz_pairs(numeric) for column in (channel_real, channel_imag)} if frequency_col else set()
        channel_metadata = {name for name in numeric if name.lower() in {"channel", "channel_id", "channelid", "通道", "通道编号"}}
        if any(len(set(table["data"][name])) > 1 for name in channel_metadata):
            return self._failed(run_id, question, trajectory, "检测到逐行混合通道的长表，请先按通道拆分文件或转换为每通道一列；未混合计算。", started, self.max_steps)
        signal_col = self._signal_column(numeric, {frequency_col, real_col, imag_col, time_col, *bioz_columns, *channel_metadata})
        if channel is not None and not bioz_pairs:
            candidates = [name for name in numeric if name not in {frequency_col, time_col} and (name == channel or bool(re.search(rf"(?:^|[_ -])(?:ch(?:annel)?[_ -]?|通道\s*){re.escape(requested_channel)}(?:$|[_ -])", name, re.I)))]
            if len(candidates) != 1:
                return self._failed(run_id, question, trajectory, f"通道 {channel} 必须对应唯一数值列；请提供完整列名。", started, self.max_steps)
            signal_col = candidates[0]
        elif not bioz_pairs:
            candidates = [name for name in numeric if name not in {frequency_col, time_col, *channel_metadata}]
            asks_signal = wants_frequency or wants_quality or any(term in query for term in ("均值", "平均", "统计", "mean", "filter", "滤波", "画图", "绘图", "plot"))
            asks_comparison = any(term in query for term in ("compare", "比较", "对比"))
            if len(candidates) > 1 and asks_signal and not asks_comparison:
                return self._failed(run_id, question, trajectory, "存在多个数值通道，请指定通道或完整列名：" + "、".join(candidates), started, self.max_steps)
        inferred_rate = sample_rate
        if inferred_rate is None and time_col:
            time_values = np.asarray(table["data"][time_col], dtype=float)
            diffs = np.diff(time_values)
            if len(diffs) and np.all(np.isfinite(diffs)) and np.all(diffs > 0) and np.allclose(diffs, np.median(diffs), rtol=0.01, atol=1e-9):
                inferred_rate = 1 / float(np.median(diffs))
            elif len(diffs):
                limitations.append("时间列不等间隔或非递增，未据此推断采样率。")
        signal_values = table["data"][signal_col] if signal_col else None
        if (wants_quality or wants_statistics) and not bioz_pairs:
            if signal_col:
                intent = "signal_analysis"
                execution = self._execute(state, "analyze_signal", {"signal": signal_values, "sample_rate": inferred_rate})
                trajectory.append(execution)
                if execution.status == "complete" and execution.result:
                    calculated["signal_quality"] = execution.result
                    source_refs.append(self._provenance(table, execution, experiment_id=experiment_id, channel=signal_col, method="Raw signal quality heuristics v1", parameters={**execution.result["quality_method"], "input": "raw signal", "input_tool_run_id": load.tool_run_id}))
                else:
                    limitations.append(execution.error or "Signal quality check failed")
            else:
                limitations.append("未找到可检查的数值信号列，请指定通道或列名。")
        elif wants_quality:
            limitations.append("当前为阻抗扫频表，尚未实现从扫频表判断时域伪差；请提供对应时间序列。")
        if signal_col and wants_statistics and not bioz_pairs and "signal_quality" in calculated:
            intent = "signal_statistics"
            quality = calculated["signal_quality"]
            calculated["statistics"] = {
                "column": signal_col, **table["basic_stats"][signal_col],
                "valid_point_count": quality["valid_point_count"], "mean": quality["mean"],
                "min": quality["minimum"], "max": quality["maximum"],
                "drift": quality["drift"], "slope": quality["slope"],
                "slope_axis_unit": quality["slope_axis_unit"],
                "method": quality["quality_method"]["slope_definition"],
                "tool_run_id": execution.tool_run_id,
            }
        parameters = analysis_parameters or AnalysisParameters()
        wants_filter = not requests_raw_signal(query) and (parameters.filter is not None or any(term in query for term in ("filter", "滤波", "去噪", "带通", "低通", "高通")))
        if wants_filter and signal_col:
            intent = "signal_filter"
            try:
                settings = parameters.filter or parse_filter_parameters(query)
            except ValueError as exc:
                settings = None
                limitations.append(str(exc))
            if settings is None:
                clarification_fields.append("analysis_parameters.filter")
            if inferred_rate is None:
                limitations.append("缺少 sample rate 或可推断的时间列，未执行滤波。")
                clarification_fields.append("sample_rate_hz")
            elif settings is None:
                limitations.append("滤波需要明确截止频率，例如“0.5–3 Hz 带通滤波”；未使用默认参数。")
                clarification_fields.append("analysis_parameters.filter")
            else:
                filter_arguments: dict[str, Any] = {"signal": signal_values, "sample_rate": inferred_rate, **settings.model_dump(exclude_none=True)}
                execution = self._execute(state, "filter_signal", filter_arguments)
                trajectory.append(execution)
                if execution.status == "complete" and execution.result:
                    calculated["filter"] = {key: value for key, value in execution.result.items() if key != "filtered_signal"}
                    signal_values = execution.result["filtered_signal"]
                    state.analysis_parameters = AnalysisParameters(filter=settings, parameter_source_run_id=parameters.parameter_source_run_id)
                    source_refs.append(self._provenance(table, execution, experiment_id=experiment_id, channel=signal_col, method=execution.result["parameters"]["filter"], parameters={**execution.result["parameters"], "input_tool_run_id": load.tool_run_id, "parameter_source_run_id": parameters.parameter_source_run_id}))
                else:
                    limitations.append(execution.error or "Signal filtering failed")
        processing_ready = not wants_filter or "filter" in calculated
        if wants_filter and not processing_ready:
            limitations.append("滤波未完成，未用原始信号冒充滤波结果继续做 FFT 或绘图。")
        if wants_frequency and signal_col and processing_ready:
            intent = "signal_spectrum"
            if inferred_rate is None:
                limitations.append("缺少 sample rate 或可推断的时间列，未执行频谱分析。")
                clarification_fields.append("sample_rate_hz")
                if not wants_quality and not wants_statistics:
                    calculated = {}
            else:
                pulse_requested = bool(re.search(r"脉搏|脉率|心率|\bpulse\b|\bbpm\b|heart\s*rate", query, re.I))
                spectrum_arguments = {"signal": signal_values, "sample_rate": inferred_rate, "max_peaks": 3}
                if pulse_requested:
                    spectrum_arguments["estimate_pulse_rate"] = True
                execution = self._execute(state, "spectral_analysis", spectrum_arguments)
                trajectory.append(execution)
                if execution.status == "complete":
                    calculated["spectrum"] = execution.result
                    upstream = next((step for step in reversed(trajectory[:-1]) if step.tool_name == "filter_signal" and step.status == "complete"), load)
                    source_refs.append(self._provenance(table, execution, experiment_id=experiment_id, channel=signal_col, method="One-sided FFT after mean removal", parameters={"sample_rate": inferred_rate, "max_peaks": 3, "input": "filtered signal" if upstream.tool_name == "filter_signal" else "raw signal", "input_tool_run_id": upstream.tool_run_id, "algorithm_version": execution.result["algorithm_version"], "pulse_rate_method": execution.result.get("pulse_rate_method")}))
                else:
                    limitations.append(execution.error or "Spectral analysis failed")
        wants_compare = any(term in query for term in ("compare", "comparison", "比较", "对比", "变化率"))
        if wants_compare:
            baseline_col = self._find_column(normalized_columns, ("baseline", "before", "control", "基线", "处理前", "对照"))
            comparison_col = self._find_column(normalized_columns, ("comparison", "after", "treated", "处理后", "实验组"))
            if baseline_col and comparison_col:
                intent = "experiment_comparison"
                execution = self._execute(state, "compare_experiments", {"baseline": table["data"][baseline_col], "comparison": table["data"][comparison_col], "metric_name": f"{baseline_col} vs {comparison_col}"})
                trajectory.append(execution)
                if execution.status == "complete":
                    calculated["comparison"] = execution.result
                    source_refs.append(self._provenance(table, execution, experiment_id=experiment_id, channel=f"{baseline_col},{comparison_col}", method="Paired experiment comparison", parameters={"baseline_column": baseline_col, "comparison_column": comparison_col}))
                else:
                    limitations.append(execution.error or "Experiment comparison failed")
            else:
                limitations.append("比较需要可识别的 baseline/before 与 comparison/after 数值列。")
        wants_plot = any(term in query for term in ("plot", "画图", "绘图", "曲线", "graph")) or bool(re.search(r"画.{0,8}(?:信号|图)", query))
        wants_export = requests_signal_export(query, filtering=wants_filter)
        if wants_export:
            filter_step = next((step for step in reversed(trajectory) if step.tool_name == "filter_signal" and step.status == "complete"), None)
            if filter_step is None:
                limitations.append("未完成滤波，未导出或冒充已处理的 CSV；请明确滤波参数。")
            else:
                # A rate is validated by filter_signal. Generate seconds from
                # that rate instead of relabelling an ambiguous input time unit.
                export = self._execute(state, "export_signal", {
                    "x": (np.arange(len(signal_values)) / inferred_rate).tolist(),
                    "signal": signal_values, "axis_name": "time_s",
                    "source_file": table["source_file"], "source_sha256": table["source_sha256"],
                    "output_dir": output_dir or str(Path(file_path).resolve().parent / "artifacts"),
                    "channel": signal_col, "experiment_id": experiment_id,
                    "input_tool_run_id": filter_step.tool_run_id,
                    "processing_parameters": {**filter_step.result["parameters"], "time_origin": "relative zero; generated from sample rate"},
                })
                trajectory.append(export)
                if export.status == "complete" and export.result:
                    artifacts.append(export.result)
                    source_refs.append(self._provenance(table, export, experiment_id=experiment_id, channel=signal_col, method="Derived filtered CSV export", parameters=export.result["metadata"]))
                else:
                    limitations.append(export.error or "Derived CSV export failed")
        if wants_plot and signal_col and processing_ready:
            x_col = time_col or frequency_col
            x_values = table["data"][x_col] if x_col else list(range(len(table["data"][signal_col])))
            target_dir = output_dir or str(Path(file_path).resolve().parent / "artifacts")
            execution = self._execute(state, "plot_signal", {"x": x_values, "y": signal_values, "output_dir": target_dir, "title": question[:120] or signal_col, "x_label": x_col or "sample", "y_label": signal_col, "filename_prefix": Path(file_path).stem, "source_sha256": table["source_sha256"]})
            trajectory.append(execution)
            if execution.status == "complete" and execution.result:
                artifacts.append(execution.result)
                input_step = next((step for step in reversed(trajectory[:-1]) if step.tool_name == "filter_signal" and step.status == "complete"), load)
                source_refs.append(self._provenance(table, execution, experiment_id=experiment_id, channel=signal_col, method="Line plot rendering", parameters={**execution.result.get("metadata", {}), "input_tool_run_id": input_step.tool_run_id, "input": "filtered signal" if input_step.tool_name == "filter_signal" else "raw signal"}))
            else:
                limitations.append(execution.error or "Plot generation failed")
        if not numeric:
            return self._failed(run_id, question, trajectory, "CSV does not contain numeric columns", started, self.max_steps)
        limitations = list(dict.fromkeys(limitations))
        clarification_fields = list(dict.fromkeys(clarification_fields))
        status = "partial" if limitations else "complete"
        state.phase = "stopped"
        if state.stop_reason is None:
            state.stop_reason = "needs_clarification" if clarification_fields else "completed_with_limitations" if limitations else "completed"
        state.sample_rate = inferred_rate
        state.selected_columns["signal"] = signal_col
        state.errors = limitations.copy()
        if intent == "data_profile":
            interpretation = "已完成只读数据概览。请指定通道、采样率和分析目标后再执行科学计算。"
        elif intent == "bioz_features":
            interpretation = "已由 Python 工具计算阻抗幅值、相位和数据质量指标；这些数值不是由 LLM 推算。"
        elif intent == "bioz_multichannel":
            interpretation = f"已由 Python 工具逐通道计算 {len(calculated.get('bioz_channels', {}))} 组阻抗特征；通道差异仍需结合电极位置、接触阻抗和重复实验解释。"
        elif intent == "experiment_comparison":
            interpretation = "已由 Python 工具完成成对实验比较；差值不等同于因果效应，仍需结合重复数、对照与不确定度解释。"
        elif intent == "signal_statistics":
            interpretation = "有效样本统计与线性漂移由Python工具计算；斜率轴单位和有限值处理策略见结果。"
        elif "signal_quality" in calculated:
            interpretation = "已检查原始信号并标记可疑区段；这些启发式标记不能确认运动伪差或医学异常。"
        elif "spectrum" not in calculated:
            interpretation = "已执行的处理和绘图见工具记录；本轮没有完成频谱计算。"
        else:
            interpretation = "已由 Python 工具执行频谱分析；主峰必须结合采样率、运动伪差和采集协议解释。"
        return LabAgentResult(agent_run_id=run_id, status=status, intent=intent, question=question, trajectory=trajectory, measured_result=measured, calculated_result=calculated, interpretation=interpretation, limitations=limitations, source_refs=source_refs, artifacts=artifacts, state=state.model_dump(mode="json"), stop_reason=state.stop_reason, latency_ms=round((time.monotonic() - started) * 1000), clarification_fields=clarification_fields)

    def _analyze_iv(self, table, load, measured, state, run_id, question, started,
                    trajectory, refs, experiment_id, channel, output_dir) -> LabAgentResult:
        calculated, artifacts, limitations, fields = {}, [], [], []
        status, stop = "complete", "completed"
        try:
            if table["truncated"]:
                raise ValueError("I–V数据超过完整读取上限；未用截断范围定义零偏拟合窗口。")
            args = iv_arguments(table["data"], question, channel)
            selection = args["iv_curve"]
            state.selected_columns.update(voltage=selection["voltage_column"], current=selection["current_column"], signal=selection["current_column"])
            execution = self._execute(state, "analyze_signal", args)
            trajectory.append(execution)
            if execution.status != "complete" or not execution.result:
                raise ValueError(execution.error or "I–V工具未完成，未生成电阻。")
            values = execution.result
            calculated["iv"] = values
            limitations.extend(values["limitations"])
            refs.append(self._provenance(table, execution, experiment_id=experiment_id,
                channel=selection["current_column"], method=values["algorithm_version"],
                parameters={**values["parameters"], "input_tool_run_id": load.tool_run_id}))
            if values["differential_resistance_ohm"] is None:
                status, stop = "partial", "undefined_differential_resistance"
            if re.search(r"画图|绘图|\bplot\b|\bgraph\b", question, re.I):
                plot = self._execute(state, "plot_signal", {"x": selection["voltage"], "y": args["signal"],
                    "output_dir": output_dir or str(Path(table["source_file"]).parent / "artifacts"),
                    "title": "Raw I-V curve", "x_label": selection["voltage_column"], "y_label": selection["current_column"],
                    "source_sha256": table["source_sha256"]})
                trajectory.append(plot)
                if plot.status != "complete" or not plot.result:
                    raise ValueError(plot.error or "电阻已计算，曲线图未完成。")
                artifacts.append(plot.result)
                refs.append(self._provenance(table, plot, experiment_id=experiment_id, channel=selection["current_column"],
                    method="Raw I-V curve plot", parameters={**plot.result["metadata"], "input_tool_run_id": load.tool_run_id}))
        except ValueError as error:
            limitations.append(str(error))
            status = "partial"
            stop = state.stop_reason or ("tool_error" if trajectory[-1].status == "timeout" else "needs_clarification")
            if stop == "needs_clarification" and not calculated:
                fields = ["iv_curve"]
        state.phase, state.stop_reason = "stopped", stop
        state.errors = [] if status == "complete" else [limitations[-1]]
        return LabAgentResult(agent_run_id=run_id, status=status, intent="iv_analysis", question=question,
            trajectory=trajectory, measured_result=measured, calculated_result=calculated,
            interpretation="电阻由Python工具按明确单位与记录的零偏拟合窗口计算；不代表器件总体性能。" if calculated else "I–V计算未完成，没有生成电阻结论。",
            limitations=limitations, source_refs=refs, artifacts=artifacts,
            state=state.model_dump(mode="json"), stop_reason=stop,
            latency_ms=round((time.monotonic()-started)*1000), clarification_fields=fields)

    def _execute(self, state: LabAgentState, name: str, arguments: dict[str, Any]) -> ToolExecution:
        """Execute one action only while the run still has an explicit step budget."""
        if state.step_count >= state.max_steps:
            state.phase = "stopped"
            state.stop_reason = "step_budget_exhausted"
            error = f"Agent step budget exhausted at {state.max_steps} tool call(s)"
            state.errors.append(error)
            return ToolExecution(
                tool_run_id=uuid.uuid4().hex,
                tool_name=name,
                status="error",
                arguments=arguments,
                error_code="step_budget_exhausted",
                error=error,
                recoverable=True,
                latency_ms=0,
            )
        execution = self.registry.execute(name, arguments)
        self._observe(state, execution)
        return execution

    @staticmethod
    def _observe(state: LabAgentState, execution: ToolExecution) -> None:
        state.phase = "observing"
        state.step_count += 1
        if execution.status == "complete":
            state.completed_tools.append(execution.tool_name)
        elif execution.error:
            state.errors.append(execution.error)
        state.phase = "acting"

    @staticmethod
    def _filter_band(query: str) -> tuple[float | None, float | None] | None:
        settings = parse_filter_parameters(query)
        return (settings.low_cut, settings.high_cut) if settings else None

    @staticmethod
    def _provenance(
        table: dict[str, Any],
        execution: ToolExecution,
        *,
        experiment_id: int | None,
        method: str,
        parameters: dict[str, Any],
        channel: str | None = None,
    ) -> ProvenanceRef:
        return ProvenanceRef(
            experiment_id=experiment_id,
            source_file=table["source_file"],
            source_sha256=table["source_sha256"],
            timestamp=datetime.now(UTC).replace(microsecond=0).isoformat(),
            channel=channel,
            processing_method=method,
            parameters=parameters,
            tool_run_id=execution.tool_run_id,
        )

    @staticmethod
    def _find_column(columns: dict[str, str], aliases: tuple[str, ...]) -> str | None:
        return next((original for lowered, original in columns.items() if any(alias in lowered for alias in aliases)), None)

    @staticmethod
    def _bioz_pairs(columns: list[str]) -> list[tuple[str, str, str]]:
        """Pair common `chN_real/chN_imag` and `z_real_chN/z_imag_chN` names."""
        real_markers = r"z[_-]?real|resistance|real|(?:^|[_-])z?re(?:[_-]|$)"
        imag_markers = r"z[_-]?(?:imaginary|imag)|reactance|imaginary|imag|(?:^|[_-])z?im(?:[_-]|$)"

        def identity(name: str, markers: str) -> str:
            stripped = re.sub(markers, "", name.lower())
            stripped = re.sub(r"(?:ohms?|ω)", "", stripped)
            return re.sub(r"[^a-z0-9]+", "", stripped) or "default"

        real_by_id: dict[str, str] = {}
        imag_by_id: dict[str, str] = {}
        for column in columns:
            lowered = column.lower()
            is_real = "real" in lowered or "resistance" in lowered or bool(re.search(r"(?:^|[_-])z?re(?:[_-]|$)", lowered))
            is_imag = "imag" in lowered or "reactance" in lowered or bool(re.search(r"(?:^|[_-])z?im(?:[_-]|$)", lowered))
            if is_real:
                real_by_id.setdefault(identity(lowered, real_markers), column)
            if is_imag:
                imag_by_id.setdefault(identity(lowered, imag_markers), column)
        pairs = []
        for channel_id in sorted(real_by_id.keys() & imag_by_id.keys()):
            label_match = re.search(r"(?:ch(?:annel)?[_-]?)?\d+", channel_id, re.I)
            label = label_match.group(0) if label_match else channel_id
            pairs.append((label or "default", real_by_id[channel_id], imag_by_id[channel_id]))
        return pairs

    @staticmethod
    def _signal_column(numeric: list[str], excluded: set[str | None]) -> str | None:
        candidates = [column for column in numeric if column not in excluded]
        preferred = next((column for column in candidates if re.search(r"signal|pulse|amplitude|current|voltage|magnitude|impedance|bioz", column, re.I)), None)
        return preferred or (candidates[0] if candidates else None)

    @staticmethod
    def _failed(run_id: str, question: str, trajectory: list[ToolExecution], error: str, started: float, max_steps: int) -> LabAgentResult:
        state = {"phase": "failed", "step_count": len(trajectory), "max_steps": max_steps, "source_file": "", "selected_columns": {}, "sample_rate": None, "completed_tools": [step.tool_name for step in trajectory if step.status == "complete"], "errors": [error], "stop_reason": "input_or_tool_error"}
        return LabAgentResult(agent_run_id=run_id, status="error", intent="data_analysis", question=question, trajectory=trajectory, interpretation="未生成实验结论。请修复输入后重试。", limitations=[error], state=state, stop_reason="input_or_tool_error", latency_ms=round((time.monotonic() - started) * 1000))

