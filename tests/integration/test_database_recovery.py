"""Real SQLite locks, upload rollback, recovery download and bounded retry."""

import hashlib
import io
import json
import sqlite3
import threading
import time
from contextlib import contextmanager

import pytest

import app as application


IV_CSV = ("voltage_V,current_A\n" + "\n".join(f"{i/20:.8f},{i/20000:.8f}" for i in range(-20, 21)) + "\n").encode()


@contextmanager
def hold_write_lock(path, duration=None):
    ready, release = threading.Event(), threading.Event()
    errors = []
    def lock():
        db = sqlite3.connect(path)
        try:
            db.execute("BEGIN IMMEDIATE")
            ready.set()
            release.wait(duration)
            db.rollback()
        except BaseException as error:
            errors.append(error)
            ready.set()
        finally:
            db.close()
    thread = threading.Thread(target=lock)
    thread.start()
    assert ready.wait(2) and not errors
    try:
        yield thread
    finally:
        if duration is not None:
            thread.join(timeout=duration + 1)
        release.set()
        thread.join(timeout=3)
        assert not thread.is_alive() and not errors


def upload(client):
    return client.post("/api/analyze", data={"question": "分析上传的 I-V CSV 并归档。", "bindContext": "true", "file": (io.BytesIO(IV_CSV), "iv_1kohm.csv")}, content_type="multipart/form-data")


def counts():
    with application.get_db() as db:
        return {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("measurements", "experiments", "experiment_files", "agent_runs")}


def test_real_1500ms_lock_returns_partial_and_recoverable_raw_then_retry_once():
    client = application.app.test_client()
    before = counts()
    with hold_write_lock(application.DATABASE, 1.5) as owner:
        started = time.monotonic()
        response = upload(client)
        elapsed = time.monotonic() - started
        assert owner.is_alive(), "request must stop before the 1.5s lock is released"
        assert response.status_code == 503
        result = response.json
        assert result["responseState"] == "partial" and result["errorCode"] == "DATABASE_BUSY"
        assert result["intent"] == "data_analysis"
        assert .7 < elapsed < 1.5
        recovery = result["recovery"]
        assert recovery["rawPreserved"] is True and recovery["archiveCommitted"] is False
        assert recovery["measurementId"] is None and recovery["experimentId"] is None
        attempts = recovery["transactionAttempts"]
        assert len(attempts) == 3 and all(item["phase"] == "begin" for item in attempts)
        assert [item["retry_scheduled"] for item in attempts] == [True, True, False]
        assert all(item["error_code"] == "DATABASE_BUSY" for item in attempts)
        assert not any(key in result for key in ("agent", "metrics", "measurement", "calculated_result"))
        downloaded = client.get(recovery["sourceUrl"])
        assert downloaded.status_code == 200 and downloaded.data == IV_CSV
        assert hashlib.sha256(downloaded.data).hexdigest() == recovery["sha256"]
        downloaded.close()
        assert counts() == before
    retry = upload(client)
    assert retry.status_code == 200
    after = counts()
    assert after["measurements"] == before["measurements"] + 1
    assert after["experiments"] == before["experiments"] + 1
    assert after["experiment_files"] == before["experiment_files"] + 1
    assert len(list(application.MEASUREMENT_DIR.glob("*.csv"))) == 1
    assert client.get(recovery["sourceUrl"]).data == IV_CSV


def test_transient_lock_recovers_inside_bounded_begin_retry():
    client = application.app.test_client()
    with hold_write_lock(application.DATABASE, .35):
        response = upload(client)
    assert response.status_code == 200
    events = response.json["storage"]["transactionAttempts"]
    assert [event["phase"] for event in events] == ["begin", "begin", "commit"]
    assert [event["status"] for event in events] == ["error", "complete", "complete"]
    assert counts()["measurements"] == 1


def test_post_archive_failure_does_not_replay_or_claim_nothing_was_saved(monkeypatch):
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(application, "persist_agent_result", fail)
    client = application.app.test_client()
    response = upload(client)
    assert response.status_code == 503
    recovery = response.json["recovery"]
    assert recovery["archiveCommitted"] is True and recovery["measurementId"] == 1
    assert counts()["measurements"] == 1 and counts()["agent_runs"] == 0
    assert "请勿重复上传" in response.json["error"]
    assert len(recovery["transactionAttempts"]) == 2
    assert client.get(recovery["sourceUrl"]).data == IV_CSV


def test_db_busy_and_recovery_disk_failure_is_not_claimed_safe(monkeypatch):
    monkeypatch.setattr(application, "preserve_upload", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("injected disk full")))
    with hold_write_lock(application.DATABASE):
        response = upload(application.app.test_client())
    assert response.status_code == 503
    assert response.json["recoverable"] is False
    assert response.json["recovery"]["rawPreserved"] is False
    assert "sourceUrl" not in response.json["recovery"]
    assert counts()["measurements"] == 0


def test_recovery_route_fails_closed_on_modified_raw_or_missing_receipt():
    client = application.app.test_client()
    with hold_write_lock(application.DATABASE):
        result = upload(client).json
    recovery = result["recovery"]
    (application.DATA_DIR / "upload-recovery" / recovery["id"] / "source.csv").write_bytes(b"wrong")
    assert client.get(recovery["sourceUrl"]).status_code == 409
    assert client.get("/api/upload-recovery/" + "0" * 32 + "/source").status_code == 404


def test_commit_blocked_by_reader_rolls_back_all_rows_without_body_retry():
    reader = sqlite3.connect(application.DATABASE)
    reader.execute("BEGIN")
    reader.execute("SELECT COUNT(*) FROM measurements").fetchone()
    try:
        response = upload(application.app.test_client())
        assert response.status_code == 503 and response.json["errorCode"] == "DATABASE_BUSY"
        recovery = response.json["recovery"]
        assert recovery["archiveCommitted"] is False
        assert [(event["phase"], event["status"]) for event in recovery["transactionAttempts"]] == [("begin", "complete"), ("commit", "error")]
    finally:
        reader.rollback()
        reader.close()
    assert counts()["measurements"] == counts()["experiments"] == counts()["experiment_files"] == 0
    assert application.app.test_client().get(recovery["sourceUrl"]).data == IV_CSV

