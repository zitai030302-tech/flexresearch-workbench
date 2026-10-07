import hashlib
import threading

import pytest
from pydantic import BaseModel

import app as module
from flexresearch.document_indexing import DocumentUpload, IndexDocumentInput, IndexDocumentOutput, prepare_document
from flexresearch.tooling import ToolRegistry, ToolSpec
from scripts.document_fixtures import document_pdf


@pytest.mark.parametrize("args", [{"upload_id": "../../private"}, {"upload_id": "a"*32, "file_path": "/etc/passwd"}, {"upload_id": "a"*32, "experiment_id": 0}, {"upload_id": "a"*32, "metadata": {"unsupported": 1}}])
def test_index_schema_refuses_arbitrary_paths_and_bad_scope(args):
    result = module.build_application_tool_registry().execute("index_document", args)
    assert result.status == "error" and result.error_code == "invalid_arguments"


def test_index_requires_upload_owned_by_this_request():
    result = module.build_application_tool_registry().execute("index_document", {"upload_id": "a"*32})
    assert result.status == "error" and "上传授权" in result.error


@pytest.mark.parametrize("kind,pages", [("two_page", [1, 2]), ("blank_first", [2])])
def test_prepare_preserves_physical_pages_and_has_no_side_effects(kind, pages):
    raw = document_pdf(kind)
    result = prepare_document(IndexDocumentInput(upload_id="a"*32), DocumentUpload("a"*32, "sop.pdf", raw), module.extract_text, module.split_document_chunks)
    assert not result.error_code
    assert [chunk.page for chunk in result.chunks] == pages
    assert result.content.count("\f") + 1 == 2
    assert result.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert "raw" not in result.model_dump() and "content" not in result.model_dump() and "chunks" not in result.model_dump()
    assert not module.UPLOAD_DIR.exists()
    with module.get_db() as db:
        assert db.execute("SELECT count(*) FROM documents").fetchone()[0] == 0


@pytest.mark.parametrize("raw,filename,code", [(b"", "empty.txt", "DOCUMENT_INPUT_INVALID"), (b"x", "bad.exe", "DOCUMENT_INPUT_INVALID"), (b"  ", "empty.txt", "DOCUMENT_TEXT_EMPTY"), (b"%PDF-invalid", "corrupt.pdf", "DOCUMENT_PARSE_FAILED")])
def test_prepare_reports_no_document_for_invalid_input(raw, filename, code):
    result = prepare_document(IndexDocumentInput(upload_id="a"*32), DocumentUpload("a"*32, filename, raw), module.extract_text, module.split_document_chunks)
    assert result.error_code == code and not result.chunks


def test_index_output_cannot_claim_success_without_document():
    with pytest.raises(ValueError):
        IndexDocumentOutput(response_state="completed", source_sha256="a"*64)


class Stage(BaseModel):
    value: int


def test_two_phase_timeout_never_commits_even_when_worker_finishes():
    released, finished = threading.Event(), threading.Event()
    commits = []
    def prepare(_):
        released.wait(2)
        finished.set()
        return Stage(value=1)
    registry = ToolRegistry()
    registry.register(ToolSpec("staged", "test", Stage, Stage, prepare, .01, prepared_model=Stage, commit_handler=lambda value: commits.append(value) or value))
    try:
        result = registry.execute("staged", {"value": 1})
        assert result.status == "timeout" and commits == []
    finally:
        released.set()
    assert finished.wait(1) and commits == []


def test_invalid_prepared_schema_cannot_commit():
    commits = []
    registry = ToolRegistry()
    registry.register(ToolSpec("staged", "test", Stage, Stage, lambda _: {"value": "invalid"}, 1, prepared_model=Stage, commit_handler=lambda value: commits.append(value) or value))
    assert registry.execute("staged", {"value": 1}).status == "error"
    assert commits == []


def test_two_phase_registration_requires_both_contract_and_commit():
    with pytest.raises(ValueError):
        ToolRegistry().register(ToolSpec("bad", "test", Stage, Stage, lambda x: x, prepared_model=Stage))

