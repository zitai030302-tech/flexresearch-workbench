import pytest
from pydantic import ValidationError

from flexresearch.analysis_parameters import is_parameter_only_reply, requests_signal_export
from flexresearch.experiment_tools import ExperimentSessionState, PendingSignalRequest


@pytest.mark.parametrize("text,expected", [("0.5–3 Hz带通，4阶", True), ("采样率100 Hz", True), ("请用3Hz低通", True), ("100", True), ("实验2通道4", False), ("计算平均值100", False), ("你好", False), ("1" * 201, False)])
def test_bounded_parameter_reply(text, expected):
    assert is_parameter_only_reply(text) is expected


@pytest.mark.parametrize("text,expected", [("滤波并保存结果，但不要改原始文件", True), ("滤波这个CSV", False), ("滤波但不要保存CSV", False), ("filter and export csv", True)])
def test_explicit_export_intent(text, expected):
    assert requests_signal_export(text, filtering=True) is expected


def test_pending_scope_must_match_selected_file():
    pending = PendingSignalRequest(query="滤波", source_run_id="a"*32, source_sha256="b"*64, experiment_id=1, file_id=2)
    with pytest.raises(ValidationError, match="selected experiment file"):
        ExperimentSessionState(experiment_id=1, file_id=3, pending_request=pending)

