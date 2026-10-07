"""Readable, source-bound statements rendered from saved Python results."""

import math
import re


def result_narrative(result: dict) -> str:
    calculated = result.get("calculated_result", {})
    statements = []
    specifications = [
        ("spectrum", "dominant_frequency_hz", "spectral_analysis", "FFT 主峰", "Hz", "这是频谱主峰，不等同于已验证的心率或医学诊断。"),
        ("spectrum", "pulse_rate_bpm", "spectral_analysis", "脉率候选", "BPM", "仅按频谱主峰换算，不等同于已验证心率；谐波、运动伪差及非脉搏输入可能产生错误候选。"),
        ("bioz", "magnitude_mean_ohm", "calculate_bioz_features", "阻抗幅值均值", "Ω", "这是文件所列频点的描述性均值，不代表疾病或血管功能结论。"),
        ("comparison", "mean_delta", "compare_experiments", "两组均值差", "", "这是描述性差异，不能证明因果；需检查对照、采集条件与重复实验。"),
        ("signal_quality", "flagged_point_count", "analyze_signal", "规则标记样本", "点", "这是可疑区段候选，不能确认或排除运动伪差；需要人工核对采集记录。"),
        ("curve_features", "gauge_factor", "extract_features", "GF", "", "这是实测零应变到最大应变的割线估计，不能证明重复性、迟滞或温漂性能。"),
        ("curve_features", "retention_percent", "extract_features", "目标循环保持率", "%", "这是目标循环与首个实测循环的响应比值，不代表疲劳寿命或统计显著性。"),
        ("iv", "differential_resistance_ohm", "analyze_signal", "零偏附近微分电阻", "Ω", "这是所列近零窗口的拟合估计，不代表全偏压范围或器件总体性能。"),
    ]
    for category, field, tool, label, unit, boundary in specifications:
        value = calculated.get(category, {}).get(field)
        if not isinstance(value, (float, int)) or isinstance(value, bool) or not math.isfinite(value):
            continue
        if category == "comparison" and calculated[category].get("alignment") == "independent_samples":
            tool = "compare_distributions"
        if category == "comparison":
            unit = calculated.get("alignment", {}).get("unit", "")
        ids = {step["tool_run_id"] for step in result.get("trajectory", []) if step.get("tool_name") == tool and step.get("status") == "complete"}
        refs = [ref for ref in result.get("source_refs", []) if ref.get("tool_run_id") in ids and re.fullmatch(r"[0-9a-f]{64}", ref.get("source_sha256") or "")]
        # A number without a matching successful tool and provenance is not
        # promoted from storage into a claimed result.
        if not refs:
            statements.append(f"{label}缺少匹配的工具来源，暂不写成可核验结论。")
            continue
        ref = refs[0]
        # Multi-channel Bio-Z's representative mean belongs to the first
        # computed channel, matching the first successful tool in trajectory.
        if category == "bioz":
            ids_in_order = [step["tool_run_id"] for step in result.get("trajectory", []) if step.get("tool_name") == tool and step.get("status") == "complete"]
            ref = next((ref for ref in refs if ref["tool_run_id"] == ids_in_order[0]), ref)
        channel = f"通道 {ref['channel']}：" if ref.get("channel") else ""
        statements.append(f"{channel}{label}为 {value:.6g} {unit}。{boundary} 依据工具 `{ref['tool_run_id']}`。")
    if not statements:
        statements.append("本次没有可转述的受支持科学指标；请查看运行状态和数据概览，不能据此下实验结论。")
    if result.get("status") != "complete":
        statements.append("本次运行未完整完成；以上仅是已完成工具的部分结果，不能视为全部分析成功。")
    return "\n\n".join(statements)

