import pytest

from app import is_paper_parameter_request
from flexresearch.paper_methods import PaperRetrievalInput, RetrievedPaper, extract_method


@pytest.mark.parametrize("arguments", [{}, {"document_id": 1, "paper_id": 2}, {"paper_id": 0}, {"document_id": -1}, {"paper_id": 1, "unknown": True}, {"paper_id": True}, {"document_id": "1"}])
def test_retrieval_requires_one_explicit_source(arguments):
    with pytest.raises(ValueError):
        PaperRetrievalInput.model_validate(arguments)


@pytest.mark.parametrize("changes", [{"source_sha256": "0" * 64}, {"source_file": "fake.txt"}, {"total_chunks": 1}, {"document_id": 3}, {"paper_id": None}, {"truncated": True}])
def test_metadata_cannot_impersonate_document(changes):
    payload = dict(document_id=None, paper_id=1, title="metadata", source_file=None, source_sha256=None, evidence_level="bibliographic_metadata_only", chunks=[], total_chunks=0)
    with pytest.raises(ValueError):
        RetrievedPaper.model_validate({**payload, **changes})


def test_metadata_cannot_be_summarized_as_methods():
    paper = RetrievedPaper(document_id=None, paper_id=1, title="100 Hz sampling", source_file=None, source_sha256=None, evidence_level="bibliographic_metadata_only", chunks=[], total_chunks=0)
    with pytest.raises(ValueError, match="没有摘要或全文"):
        extract_method(paper)


@pytest.mark.parametrize("query,expected", [
    ("根据这篇只有标题和 DOI 的论文，告诉我它的具体采样率和滤波参数。", True),
    ("论文1的采样率是多少？", True),
    ("文档1具体用了什么滤波？", True),
    ("What is the sampling rate of this paper?", True),
    ("找关于 Bio-Z pulse waveform 滤波的论文", False),
    ("提取文档1的实验方法，包括采样率", False),
    ("实验1的采样率是多少", False),
    ("你好", False),
])
def test_source_specific_parameter_route(query, expected):
    assert is_paper_parameter_request(query) is expected

