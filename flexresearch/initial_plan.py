"""A reviewable Bio-Z sweep draft, not an executable or validated protocol."""

import hashlib
import re

from .history import DraftFrequencySweep, DraftSampling, ExperimentPlan, InitialPlanBasis


def is_initial_bioz_plan_request(question: str) -> bool:
    # Explicit history requests must still resolve their scope; never quietly
    # replace a failed history lookup with a generic plan.
    if re.search(r"论文|文献|paper|literature", question, re.I):
        return False
    if re.search(r"历史|之前|上次|上一|刚才|前\s*(?:\d+|[一二三几])\s*次|最近|实验\s*#?\s*\d+|项目\s*\d+|(?:根据|基于).*(?:结果|实验)", question):
        return False
    return bool(re.search(r"bio[ -]?z|生物阻抗", question, re.I) and re.search(r"多频|扫频|frequency\s+sweep|multifrequency", question, re.I) and re.search(r"方案|计划|草案|plan|draft", question, re.I))


def build_initial_bioz_plan(question: str) -> ExperimentPlan:
    if not is_initial_bioz_plan_request(question):
        raise ValueError("此分支只生成未指定历史依据的 Bio-Z 多频扫描草案；历史依据需另行选定。")
    return ExperimentPlan(
        experiment_ids=[], status="draft", mode="initial_bioz_sweep_rules",
        objective="建立柔性 Bio-Z 多频扫描的可复核采集流程，记录每个通道/频点的阻抗幅值、相位及质量信息；先完成台架检查，再讨论正式采集。",
        observations=[], recommendations=[],
        variables=[
            {"name": "frequency_sweep_hz", "role": "planned_independent_variable", "values": [], "status": "requires_confirmation", "description": "扫频频点、顺序与范围由测量目标、设备设置和已审核 SOP 确认。"},
            {"name": "selected_channels", "role": "planned_scan_dimension", "values": [], "status": "requires_confirmation", "description": "核对电极—MUX—CSV列的通道映射，明确扫描顺序；不假定所有通道有效。"},
        ],
        controls=[
            "先使用已表征的参考负载检查通道映射和测量链路，保存参考值及校准记录；参考负载数值由实验室提供。",
            "固定器件、固件、接线、电极几何、材料、接触方式及环境条件；记录任何偏离，不据草案认定因果。",
            "按预先审核的顺序安排独立重复和参考测量，保留每次原始数据，不把重复测量自动视为独立样本。",
        ],
        sample_rate=DraftSampling(requirements=[
            "分别记录 ADC 采样设置、阻抗结果输出率和每通道有效更新率；扫频频率不是这些采样率的替代值。",
            "结合目标信号带宽、解调/滤波设置、MUX切换及稳定等待，核对每通道实际时间戳；具体值待设备手册和 SOP 确认。",
        ]),
        frequency_sweep=DraftFrequencySweep(requirements=[
            "明确研究目标后，由负责人确认频点列表、范围、顺序、每频点稳定等待及独立重复次数；此处不生成默认数值。",
            "在参考负载上核查所选频点的幅相、重复性和通道切换后稳定性，再决定正式扫频配置。",
        ]),
        quality_checks=[
            "每条记录保存时间戳、通道、激励频率、幅值/相位及单位；检查列名、缺失/非有限值、饱和及采样间隔。",
            "标注接触变化、通道切换和运动事件；保留原始数据，不把候选异常自动删除或视作病理。",
            "记录参考负载误差、重复测量差异与漂移；验收阈值由校准要求和审核协议预先规定。",
            "归档原始文件哈希、设备/固件/协议版本及处理参数；分析结果保存新文件，不能覆盖原始测量。",
        ],
        safety=[
            "本草案不可直接执行，也不构成人体测量许可；激励、电极连接和停机条件必须由实验负责人依据设备说明及已审核 SOP 确认。",
            "先完成台架、连接和设备状态检查；涉及人体时，须遵守所在机构适用的伦理、知情同意和安全流程。",
            "发生异常接触、设备报错或不适时停止采集并按审核流程处理；草案不判断医学安全或给出诊断。",
        ],
        unresolved_parameters=["selected_channels", "electrode_geometry", "device_and_firmware", "adc_sample_rate_hz", "per_channel_output_rate_hz", "frequency_sweep_hz", "settling_time_ms", "repetitions", "excitation_settings", "reference_load", "quality_acceptance_thresholds", "sop_reference"],
        basis=InitialPlanBasis(request_text=question, request_sha256=hashlib.sha256(question.encode()).hexdigest()),
        limitations=["依据本轮请求与内置规则生成草案；本次未读取历史实验、论文或 SOP，未产生实验结果。", "完成的是草案结构，不是采集协议审批；所有数值配置均待确认，输入中的数值也不自动视为已审核参数。", "未进行功效分析、设备校准或人体安全验证；不自动执行实验。"],
    )


def initial_plan_markdown(plan: ExperimentPlan) -> str:
    """Render the saved structured snapshot, with unknown values kept explicit."""
    if plan.mode != "initial_bioz_sweep_rules":
        raise ValueError("不是初始多频扫描草案。")
    lines = ["# Bio-Z 多频扫描方案草案", "", "待负责人审核；不可直接执行。未使用历史实验或外部文献。", "", "## objective · 目标", plan.objective, "", "## variables · 变量"]
    lines += [f"- {item['name']}：{item['description']}" for item in plan.variables]
    for title, items in [("controls · 对照", plan.controls), ("sample_rate · 采样率（未确定）", plan.sample_rate.requirements), ("frequency_sweep · 扫频（频点与参数未确定）", plan.frequency_sweep.requirements), ("quality_checks · 质量检查", plan.quality_checks), ("safety · 安全与执行前确认", plan.safety), ("approval_required · 审核要求", ["必须由负责人审核，并补齐以下参数；本系统不授权执行。", *plan.unresolved_parameters]), ("limitations · 边界", plan.limitations)]:
        lines += ["", f"## {title}", *[f"- {item}" for item in items]]
    # Quoting each line keeps request text from injecting a Markdown section.
    lines += ["", "## basis · 请求来源", *["> " + line for line in plan.basis.request_text.splitlines()], "", "SHA-256: " + plan.basis.request_sha256, ""]
    return "\n".join(lines)

