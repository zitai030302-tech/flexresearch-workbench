"""Read archived experiment context before deterministic GF/retention tools."""

import hashlib
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .agent import LabAgentResult
from .curve_features import feature_arguments, feature_kind
from .schemas import ProvenanceRef


def run_curve_analysis(registry, path: Path, question: str, experiment_id: int | None, file_id: int | None = None, output_dir: str | None = None) -> LabAgentResult:
    started, run_id = time.monotonic(), uuid.uuid4().hex
    trajectory, refs, measured, calculated, artifacts = [], [], {}, {}, []
    metadata, kind = {}, feature_kind(question)
    try:
        if experiment_id is not None:
            context = registry.execute("load_experiment_data", {"experiment_id": experiment_id})
            trajectory.append(context)
            if context.status != "complete" or not context.result:
                raise ValueError(context.error or "实验资料读取失败。")
            matching = [f for f in context.result["files"] if (file_id is None or f["file_id"] == file_id) and f["source_file"] == path.name and f["available"] and f["immutable"]]
            if len(matching) != 1 or matching[0]["sha256"] != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError("实验文件范围或SHA-256不一致，未分析曲线。")
            metadata = context.result["experiment"]["metadata"]
        loaded = registry.execute("load_csv", {"file_path": str(path)})
        trajectory.append(loaded)
        if loaded.status != "complete" or not loaded.result:
            raise ValueError(loaded.error or "CSV读取失败。")
        table = loaded.result
        if table["truncated"]:
            raise ValueError("曲线超出完整读取上限，未把截断数据作为完整实验。")
        measured = {key: table[key] for key in ("shape", "columns", "missing_counts", "data_quality", "cleaning_policy")}
        if re.search(r"滤波|去噪|带通|高通|低通|\bfilter", question, re.I):
            raise ValueError("GF/保持率工具使用原始曲线，不会忽略滤波要求；请先明确处理协议后分步执行。")
        args, selection = feature_arguments(kind, table["data"], question, metadata)
        execution = registry.execute("extract_features", args)
        trajectory.append(execution)
        if execution.status != "complete" or not execution.result:
            raise ValueError(execution.error or "曲线特征计算失败。")
        features = execution.result
        calculated["curve_features"] = features
        refs.append(ProvenanceRef(experiment_id=experiment_id, source_file=table["source_file"], source_sha256=table["source_sha256"], timestamp=datetime.now(UTC).isoformat(), channel=selection["y_column"], processing_method=features["algorithm_version"], parameters={**features["parameters"], **selection, "input_tool_run_id": loaded.tool_run_id}, tool_run_id=execution.tool_run_id))
        if re.search(r"画图|绘图|\bplot\b|\bgraph\b", question, re.I):
            plot = registry.execute("plot_signal", {"x": args["x"], "y": args["y"], "x_label": selection["x_column"], "y_label": selection["y_column"], "title": "Raw measurement curve", "output_dir": output_dir or str(path.parent/"artifacts"), "source_sha256": table["source_sha256"]})
            trajectory.append(plot)
            if plot.status != "complete" or not plot.result:
                raise ValueError(plot.error or "数值已计算，但曲线绘图未完成。")
            artifacts.append(plot.result)
            refs.append(ProvenanceRef(experiment_id=experiment_id, source_file=table["source_file"], source_sha256=table["source_sha256"], timestamp=datetime.now(UTC).isoformat(), channel=selection["y_column"], processing_method="Raw curve plot", parameters={**selection, "input_tool_run_id": loaded.tool_run_id}, tool_run_id=plot.tool_run_id))
        return LabAgentResult(agent_run_id=run_id, status="complete", intent="data_analysis", question=question, trajectory=trajectory, measured_result=measured, calculated_result=calculated, source_refs=refs, artifacts=artifacts, interpretation="数值由Python工具按明确单位、实测基线和目标点计算。", limitations=features["limitations"], state={"source_file": str(path), "experiment_id": experiment_id, "file_id": file_id, "feature_kind": kind}, stop_reason="completed", latency_ms=round((time.monotonic()-started)*1000))
    except (ValueError, OSError) as error:
        return LabAgentResult(agent_run_id=run_id, status="partial", intent="data_analysis", question=question, trajectory=trajectory, measured_result=measured, calculated_result=calculated, source_refs=refs, artifacts=artifacts, interpretation="曲线分析未完成；需要明确数据、单位或目标点。", limitations=[str(error)], state={"source_file": str(path), "experiment_id": experiment_id, "file_id": file_id, "feature_kind": kind}, stop_reason="needs_clarification", latency_ms=round((time.monotonic()-started)*1000))

