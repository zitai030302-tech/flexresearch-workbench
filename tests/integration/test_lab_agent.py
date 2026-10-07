from pathlib import Path

import pytest

from flexresearch import LabAgent, build_lab_tool_registry


def test_csv_to_fft_plot_and_provenance_without_mutating_source(tmp_path):
    source = tmp_path / "pulse.csv"
    rows = ["time_s,signal"] + [f"{index / 100},{__import__('math').sin(2 * __import__('math').pi * 1.2 * index / 100)}" for index in range(1000)]
    source.write_text("\n".join(rows), encoding="utf-8")
    before = source.read_bytes()
    result = LabAgent(build_lab_tool_registry()).analyze_csv(str(source), "帮我找主要脉搏频率并画图", output_dir=str(tmp_path / "artifacts"))
    assert result.status == "complete"
    assert [step.tool_name for step in result.trajectory] == ["load_csv", "spectral_analysis", "plot_signal"]
    assert result.calculated_result["spectrum"]["dominant_frequency_hz"] == pytest.approx(1.2, abs=0.05)
    assert Path(result.artifacts[0]["plot_path"]).is_file()
    assert result.artifacts[0]["metadata"]["parent_source_sha256"] == result.source_refs[0].source_sha256
    assert result.source_refs[0].source_sha256
    assert result.stop_reason == "completed"
    assert result.state["stop_reason"] == "completed"
    assert {item.processing_method for item in result.source_refs} >= {"CSV parse and profile", "One-sided FFT after mean removal", "Line plot rendering"}
    assert source.read_bytes() == before


def test_bioz_csv_uses_impedance_tool(tmp_path):
    source = tmp_path / "bioz.csv"
    source.write_text("frequency_hz,z_real_ohm,z_imag_ohm\n10,3,4\n100,5,12\n", encoding="utf-8")
    result = LabAgent(build_lab_tool_registry()).analyze_csv(str(source), "计算阻抗幅值和相位")
    assert result.status == "complete"
    assert result.intent == "bioz_features"
    assert result.calculated_result["bioz"]["magnitude_ohm"] == pytest.approx([5, 13])
    assert "basic_stats" not in result.measured_result
    assert result.calculated_result["basic_stats"]["z_real_ohm"]["mean"] == pytest.approx(4)
    assert result.trajectory[0].tool_name == "load_csv"
    assert result.source_refs[0].tool_run_id == result.trajectory[0].tool_run_id


def test_multichannel_bioz_pairs_each_real_imag_channel_with_provenance(tmp_path):
    source = tmp_path / "bioz-24ch-slice.csv"
    source.write_text("frequency_hz,ch1_real,ch1_imag,ch2_real,ch2_imag\n10,3,4,5,12\n100,6,8,8,15\n", encoding="utf-8")
    result = LabAgent(build_lab_tool_registry()).analyze_csv(str(source), "逐通道计算多通道 Bio-Z")
    assert result.status == "complete"
    assert result.intent == "bioz_multichannel"
    assert [step.tool_name for step in result.trajectory] == ["load_csv", "calculate_bioz_features", "calculate_bioz_features"]
    assert set(result.calculated_result["bioz_channels"]) == {"ch1", "ch2"}
    assert result.calculated_result["bioz_channels"]["ch1"]["magnitude_mean_ohm"] == pytest.approx(7.5)
    assert {ref.channel for ref in result.source_refs} >= {"ch1", "ch2"}


def test_missing_sample_rate_returns_partial_result_not_invented_frequency(tmp_path):
    source = tmp_path / "signal.csv"
    source.write_text("signal,channel\n1,4\n2,4\n3,4\n4,4\n5,4\n6,4\n7,4\n8,4\n", encoding="utf-8")
    result = LabAgent(build_lab_tool_registry()).analyze_csv(str(source), "找主要频率")
    assert result.status == "partial"
    assert "spectrum" not in result.calculated_result
    assert "sample rate" in result.limitations[0]
    assert result.stop_reason == "needs_clarification"
    assert result.clarification_fields == ["sample_rate_hz"]
    assert result.calculated_result == {}


def test_missing_file_stops_after_load_tool_and_has_no_result(tmp_path):
    result = LabAgent(build_lab_tool_registry()).analyze_csv(str(tmp_path / "missing.csv"), "分析")
    assert result.status == "error"
    assert len(result.trajectory) == 1
    assert result.trajectory[0].status == "error"
    assert not result.calculated_result
    assert result.stop_reason == "input_or_tool_error"


def test_step_budget_is_enforced_before_a_second_tool_call(tmp_path):
    source = tmp_path / "limited.csv"
    source.write_text(
        "time_s,signal\n" + "\n".join(f"{index / 20},{index % 3}" for index in range(40)),
        encoding="utf-8",
    )

    result = LabAgent(build_lab_tool_registry(), max_steps=1).analyze_csv(
        str(source),
        "找主要频率",
    )

    assert result.status == "partial"
    assert result.stop_reason == "step_budget_exhausted"
    assert result.state["step_count"] == 1
    assert result.state["max_steps"] == 1
    assert [step.tool_name for step in result.trajectory] == ["load_csv", "spectral_analysis"]
    assert result.trajectory[-1].error_code == "step_budget_exhausted"
    assert "spectrum" not in result.calculated_result

