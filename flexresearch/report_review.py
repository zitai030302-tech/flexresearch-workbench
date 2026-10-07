"""Bounded report-content rubric, separate from numerical algorithm tests.

Recognises declared scientific statement families. Unknown prose is not an
entailment proof. Never labels the whole report scientifically validated.
"""

import math
import re
from typing import Literal

from pydantic import Field

from .schemas import StrictModel


class ReportCriterion(StrictModel):
    name: str
    status: Literal["pass", "fail", "not_evaluated"]
    evidence: list[str] = Field(default_factory=list)


class ReportReview(StrictModel):
    version: Literal["report-content-rules-v1"] = "report-content-rules-v1"
    track: Literal["semantic_rule_based"] = "semantic_rule_based"
    status: Literal["supported_within_rubric", "needs_revision", "needs_human_review"]
    criteria: list[ReportCriterion]
    recognized_claim_count: int
    human_review_required: bool = True
    limitations: list[str] = Field(default_factory=lambda: ["仅覆盖主峰、阻抗均值、两组均值差、质量标记点数、GF、保持率和零偏微分电阻等已声明表述；不是开放文本蕴含证明。", "检查数字/单位/工具绑定、条件性措辞和章节；研究意义、可读性、方法适用性仍需人工评审。", "禁止用本评分替代数学真值测试、原文件完整性检查或医学验证。"])


NUMBER = r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
FAMILIES = [
    (r"脉率候选\s*(?:为|是|[:：])\s*" + NUMBER + r"\s*(BPM)\b", "spectrum", "pulse_rate_bpm", "spectral_analysis", "BPM"),
    (r"(?:FFT\s*主峰|频谱主峰|主要频率)\s*(?:为|是|[:：])\s*" + NUMBER + r"\s*(Hz|kHz)\b", "spectrum", "dominant_frequency_hz", "spectral_analysis", "Hz"),
    (r"(?:阻抗幅值均值|平均阻抗幅值)\s*(?:为|是|[:：])\s*" + NUMBER + r"\s*(kΩ|Ω|ohm)", "bioz", "magnitude_mean_ohm", "calculate_bioz_features", "Ω"),
    (r"(?:两组均值差|均值差)\s*(?:为|是|[:：])\s*" + NUMBER + r"\s*(kΩ|Ω|mV|V|mA|A|a\.u\.|ohm)?", "comparison", "mean_delta", "compare_experiments", ""),
    (r"(?:规则标记样本|标记样本)\s*(?:为|是|[:：])\s*" + NUMBER + r"\s*(点)", "signal_quality", "flagged_point_count", "analyze_signal", "点"),
    (r"GF\s*(?:为|是|[:：])\s*" + NUMBER, "curve_features", "gauge_factor", "extract_features", ""),
    (r"目标循环保持率\s*(?:为|是|[:：])\s*" + NUMBER + r"\s*(%)", "curve_features", "retention_percent", "extract_features", "%"),
    (r"零偏附近微分电阻\s*(?:为|是|[:：])\s*" + NUMBER + r"\s*(kΩ|Ω|ohm)", "iv", "differential_resistance_ohm", "analyze_signal", "Ω"),
]


def _section(markdown: str, heading: str) -> str:
    match = re.search(r"^## " + re.escape(heading) + r"\s*\n(.*?)(?=^## |\Z)", markdown, re.M | re.S)
    return match.group(1).strip() if match else ""


def review_report_content(markdown: str, results: list[dict]) -> ReportReview:
    interpretation = _section(markdown, "Agent Interpretation")
    limitations = _section(markdown, "Limitations")
    expected = []
    for result in results:
        calc = result.get("calculated_result", {})
        for _, category, field, tool, unit in FAMILIES:
            if category == "comparison":
                unit = calc.get("alignment", {}).get("unit", "")
            value = calc.get(category, {}).get(field)
            if type(value) not in {int, float} or not math.isfinite(value):
                continue
            actual_tool = "compare_distributions" if category == "comparison" and calc[category].get("alignment") == "independent_samples" else tool
            ids = [item["tool_run_id"] for item in result.get("trajectory", []) if item.get("tool_name") == actual_tool and item.get("status") == "complete"]
            if category == "bioz":
                ids = ids[:1]
            for ref in result.get("source_refs", []):
                if ref.get("tool_run_id") in ids and re.fullmatch(r"[0-9a-f]{64}", ref.get("source_sha256") or ""):
                    expected.append((category, float(value), unit, ref["tool_run_id"], ref.get("channel")))
    recognized, errors, matched, extra_numeric = 0, [], set(), []
    # Ignore headings but not prose. JSON archives are not assessed as prose.
    prose = re.sub(r"^###.*$", "", interpretation, flags=re.M)
    prose = re.sub(r"(`{3,})[^\n]*\n.*?\n\1", "", prose, flags=re.S)
    for paragraph in re.split(r"\n\s*\n", prose):
        remaining = paragraph
        for pattern, category, _, _, expected_unit in FAMILIES:
            for match in re.finditer(pattern, paragraph, re.I):
                recognized += 1
                value = float(match.group(1))
                unit = (match.group(2) or "") if match.lastindex > 1 else ""
                if unit == "ohm":
                    unit = "Ω"
                cited = set(re.findall(r"依据工具\s*`([a-f0-9]{32})`", paragraph))
                channel_match = re.search(r"通道\s*([^：:\n]+)[:：]", paragraph)
                channel = channel_match.group(1).strip() if channel_match else None
                support = [item for item in expected if item[0] == category and item[2] == unit and item[3] in cited and item[4] == channel and math.isclose(value, item[1], rel_tol=1e-5, abs_tol=1e-9)]
                if not support:
                    errors.append(f"数值、单位、通道或工具来源不匹配：{match.group(0)}")
                matched.update((item[0], item[2], item[3]) for item in support)
            remaining = re.sub(pattern, "", remaining, flags=re.I)
        remaining = re.sub(r"`[a-f0-9]{32}`", "", remaining)
        remaining = re.sub(r"通道\s*[\w,-]+\s*[:：]", "", remaining)
        if re.search(r"\d", remaining):
            extra_numeric.append(remaining.strip()[:160])
    required = {(item[0], item[2], item[3]) for item in expected}
    complete = bool(required) and required <= matched
    medical_claims = []
    for sentence in re.split(r"[。.!！\n]", prose):
        for match in re.finditer(r"确诊|证明.*(?:疾病|因果)|临床有效|可以诊断|医学诊断|导致.*(?:改善|下降|升高)|已(?:经)?确认.*伪差|证实.*(?:运动伪差|疾病)", sentence):
            prefix = sentence[max(0, match.start()-16):match.start()]
            if not re.search(r"不|不能|无法|未|尚未|不是|不等同", prefix):
                medical_claims.append(sentence.strip())
    bounded = bool(re.search(r"不能|不等同|不代表|需要人工|不可", prose))
    required_sections = ("Experiment Metadata", "Data Quality", "Processing Methods", "Measured Result", "Calculated Result", "Agent Interpretation", "Limitations", "Source & Provenance", "Figures & Derived Artifacts")
    sections_ok = all(_section(markdown, heading) for heading in required_sections)
    disclosed = bool(limitations) and not re.fullmatch(r"-?\s*No limitations were recorded by the deterministic run\.", limitations)
    incomplete = any(result.get("status") != "complete" for result in results)
    failure_disclosed = not incomplete or bool(re.search(r"未完整|部分结果|未完成", prose))
    criteria = [
        ReportCriterion(name="metric_and_source_support", status="fail" if errors else "pass" if recognized else "not_evaluated", evidence=errors or [f"核对 {recognized} 条已识别数值表述"]),
        ReportCriterion(name="result_explanation_completeness", status="pass" if complete else "fail" if required else "not_evaluated", evidence=[f"已解释 {len(matched)}/{len(required)} 个可转述结果"]),
        ReportCriterion(name="scope_and_noncausal_language", status="fail" if medical_claims or not bounded else "pass", evidence=medical_claims or ["存在明确的适用范围/非诊断或非因果边界"]),
        ReportCriterion(name="limitations_disclosed", status="pass" if disclosed else "fail", evidence=["有实质限制段落" if disclosed else "缺少限制或只声称未记录限制"]),
        ReportCriterion(name="result_categories_separated", status="pass" if sections_ok else "fail", evidence=["要求九类非空章节"]),
        ReportCriterion(name="failure_state_disclosed", status="pass" if failure_disclosed else "fail", evidence=["未把部分/失败运行写成全部成功"]),
        ReportCriterion(name="unrecognized_numeric_prose", status="not_evaluated" if extra_numeric else "pass", evidence=extra_numeric or ["未发现已识别表述之外的数字"]),
    ]
    status = "needs_revision" if any(item.status == "fail" for item in criteria) else "needs_human_review" if any(item.status == "not_evaluated" for item in criteria) else "supported_within_rubric"
    return ReportReview(status=status, criteria=criteria, recognized_claim_count=recognized)

