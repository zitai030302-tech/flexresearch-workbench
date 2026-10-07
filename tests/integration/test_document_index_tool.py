import hashlib
import io
import json
import sqlite3
import threading
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor

import pytest
from pypdf import PdfReader

import app as module
from scripts.document_fixtures import document_pdf


def upload(client, raw, **fields):
    return client.post("/api/documents", data={"file": (io.BytesIO(raw), "SYNTHETIC-sop.pdf"), "question": "把这份两页 SOP PDF 加入知识库。", **fields}, content_type="multipart/form-data")


def assert_empty_index():
    with module.get_db() as db:
        for table in ("documents", "document_chunks", "document_chunks_fts", "document_chunk_embeddings", "experiment_files"):
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert not list(module.UPLOAD_DIR.glob("*.pdf"))


def test_document_tool_persists_pages_hash_citations_run_and_chat():
    client, raw = module.app.test_client(), document_pdf()
    response = upload(client, raw)
    assert response.status_code == 201
    body = response.get_json()
    index = body["documentIndex"]
    assert body["intent"] == "knowledge_ingest" and body["responseState"] == "completed"
    assert index["document"] == body["item"] and index["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert [c["locator"] for c in index["citations"]] == ["p. 1", "p. 2"]
    assert [step["tool_name"] for step in body["toolCalls"]] == ["index_document"]
    for citation in index["citations"]:
        evidence = client.get(citation["url"]).get_json()
        assert evidence["page"] == citation["page"] and evidence["sourceSha256"] == index["source_sha256"]
    run = client.get(f"/api/agent-runs/{body['agentRun']['runId']}").get_json()
    assert run["toolCalls"][0]["tool_name"] == "index_document"
    assert run["final_result"]["source_refs"][0]["tool_run_id"] == body["toolCalls"][0]["tool_run_id"]
    messages = client.get(f"/api/sessions/{body['sessionId']}").get_json()["messages"]
    assert messages[-1]["result"]["documentIndex"] == index
    assert messages[-2]["content"] == "把这份两页 SOP PDF 加入知识库。"
    assert (module.UPLOAD_DIR / body["item"]["filename"]).read_bytes() == raw


def test_duplicate_keeps_document_id_original_bytes_and_single_experiment_link():
    client, raw = module.app.test_client(), document_pdf()
    experiment = client.post("/api/experiments", json={"name": "SYNTHETIC document scope"}).get_json()["item"]
    first = upload(client, raw, experimentId=str(experiment["id"])).get_json()
    second_response = upload(client, raw, experimentId=str(experiment["id"]), question="再次导入同一份 SOP。", sessionId=str(first["sessionId"]))
    second = second_response.get_json()
    assert second_response.status_code == 200 and second["duplicate"] is True
    assert first["item"]["id"] == second["item"]["id"] and first["item"]["filename"] == second["item"]["filename"]
    with module.get_db() as db:
        assert db.execute("SELECT count(*) FROM documents").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM experiment_files").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM document_chunks").fetchone()[0] == 2
    assert len(list(module.UPLOAD_DIR.glob("*.pdf"))) == 1


def test_image_only_pdf_requests_ocr_with_no_method_claims_or_archive():
    client, raw = module.app.test_client(), document_pdf("scan")
    page = PdfReader(io.BytesIO(raw)).pages[0]
    assert not page.extract_text() and page.images
    response = upload(client, raw, question="导入这份扫描版论文并提取方法。")
    body = response.get_json()
    assert response.status_code == 400 and body["responseState"] == "needs_clarification" and body["errorCode"] == "OCR_REQUIRED"
    assert body["methodClaims"] == [] and body["documentIndex"]["method_claims"] == [] and body["item"] is None
    assert "100" not in body["answer"]
    assert body["toolCalls"][0]["tool_name"] == "index_document"
    history = client.get(f"/api/sessions/{body['sessionId']}").get_json()["messages"]
    assert history[-1]["result"]["errorCode"] == "OCR_REQUIRED"
    assert_empty_index()


def test_blank_first_pdf_page_still_cites_physical_page_two():
    client = module.app.test_client()
    body = upload(client, document_pdf("blank_first")).get_json()
    assert body["item"]["pages"] == 2
    assert [c["page"] for c in body["documentIndex"]["citations"]] == [2]
    evidence = client.get(body["documentIndex"]["citations"][0]["url"]).get_json()
    assert evidence["page"] == 2 and "1250" in evidence["text"]


@pytest.mark.parametrize("failure", ["before_index", "after_first_chunk"])
def test_index_failure_rolls_back_document_all_indexes_and_owned_file(monkeypatch, failure):
    original = module.write_prepared_document_chunks
    def broken(db, identifier, title, chunks):
        if failure == "after_first_chunk":
            original(db, identifier, title, chunks[:1])
        raise sqlite3.OperationalError("synthetic index commit failure")
    monkeypatch.setattr(module, "write_prepared_document_chunks", broken)
    response = upload(module.app.test_client(), document_pdf())
    assert response.status_code == 503 and response.get_json()["responseState"] == "partial"
    assert response.get_json()["item"] is None
    assert_empty_index()


def test_duplicate_with_tampered_archive_never_overwrites_it():
    client, raw = module.app.test_client(), document_pdf()
    first = upload(client, raw).get_json()
    path = module.UPLOAD_DIR / first["item"]["filename"]
    path.write_bytes(b"SYNTHETIC damaged archive")
    response = upload(client, raw)
    assert response.status_code == 400 and response.get_json()["item"] is None
    assert path.read_bytes() == b"SYNTHETIC damaged archive"
    assert len(client.get("/api/documents").get_json()["items"]) == 1


def test_parse_timeout_cannot_create_archive_after_response(monkeypatch):
    released, finished = threading.Event(), threading.Event()
    original_registry, original_extract = module.build_application_tool_registry, module.extract_text
    def delayed(*args):
        released.wait(2)
        try:
            return original_extract(*args)
        finally:
            finished.set()
    def registry(**kwargs):
        value = original_registry(**kwargs)
        value._tools["index_document"] = replace(value._tools["index_document"], timeout_seconds=.01)
        return value
    monkeypatch.setattr(module, "extract_text", delayed)
    monkeypatch.setattr(module, "build_application_tool_registry", registry)
    try:
        response = upload(module.app.test_client(), document_pdf())
        assert response.status_code == 503 and response.get_json()["errorCode"] == "DOCUMENT_INDEX_TIMEOUT"
        assert_empty_index()
    finally:
        released.set()
    assert finished.wait(1)
    assert_empty_index()


def test_invalid_experiment_does_not_archive_document():
    response = upload(module.app.test_client(), document_pdf(), experimentId="9999")
    assert response.status_code == 400 and response.get_json()["item"] is None
    assert_empty_index()


def test_concurrent_duplicate_uploads_commit_one_document():
    raw = document_pdf()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: upload(module.app.test_client(), raw), range(2)))
    assert sorted(result.status_code for result in results) == [200, 201]
    assert len({result.get_json()["item"]["id"] for result in results}) == 1
    assert len(list(module.UPLOAD_DIR.glob("*.pdf"))) == 1


def test_reindex_failure_rolls_back_old_chunks_without_removing_original(monkeypatch):
    client, raw = module.app.test_client(), document_pdf()
    first = upload(client, raw).get_json()
    original = module.write_prepared_document_chunks
    def fail(db, identifier, title, chunks):
        original(db, identifier, title, chunks[:1])
        raise sqlite3.OperationalError("synthetic repair failure")
    monkeypatch.setattr(module, "write_prepared_document_chunks", fail)
    assert upload(client, raw).status_code == 503
    with module.get_db() as db:
        assert db.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0] == 2
    assert (module.UPLOAD_DIR / first["item"]["filename"]).read_bytes() == raw


def test_logging_failure_discloses_committed_index_and_keeps_document_id(monkeypatch):
    monkeypatch.setattr(module, "persist_agent_result", lambda *_a, **_k: (_ for _ in ()).throw(sqlite3.OperationalError("synthetic log failure")))
    response = upload(module.app.test_client(), document_pdf())
    body = response.get_json()
    assert response.status_code == 503 and body["responseState"] == "partial"
    assert body["errorCode"] == "DOCUMENT_LOG_FAILED" and body["item"]["id"] > 0
    assert "勿重复上传" in body["error"]
    assert len(module.app.test_client().get("/api/documents").get_json()["items"]) == 1

