"""Recovery copies are immutable, source-bound and independent of SQLite."""

import hashlib
import json
import sqlite3

import pytest

from flexresearch.upload_recovery import is_database_busy, preserve_upload, read_recovery_source, public_recovery, upload_transaction


@pytest.mark.parametrize("message,expected", [("database is locked", True), ("database table is locked", True), ("database schema is locked", True), ("disk full", False), ("unexpected locked secret", False)])
def test_busy_error_is_not_any_database_failure(message, expected):
    assert is_database_busy(sqlite3.OperationalError(message)) is expected


def test_extended_busy_result_code():
    error = sqlite3.OperationalError("redacted")
    error.sqlite_errorcode = sqlite3.SQLITE_BUSY_SNAPSHOT
    assert is_database_busy(error)


def test_recovery_source_is_exact_and_receipt_has_no_absolute_path(tmp_path):
    raw = b"voltage_V,current_A\n-1,-.001\n0,0\n1,.001\n"
    receipt = preserve_upload(tmp_path, raw, "iv.csv", archive_committed=False, events=[])
    assert (tmp_path / receipt.recovery_id / "source.csv").stat().st_mode & 0o777 == 0o600
    restored, source = read_recovery_source(tmp_path, receipt.recovery_id)
    assert source == raw and restored == receipt
    public = public_recovery(receipt)
    assert public["rawPreserved"] and public["sha256"] == hashlib.sha256(raw).hexdigest()
    assert str(tmp_path) not in json.dumps(public)


@pytest.mark.parametrize("mutation", ["source", "receipt_id", "source_symlink", "receipt_symlink", "folder_symlink"])
def test_recovery_download_rejects_tampering_or_symlink(tmp_path, mutation):
    root = tmp_path / "recovery"
    receipt = preserve_upload(root, b"x,y\n1,2\n", "iv.csv", archive_committed=False, events=[])
    folder = root / receipt.recovery_id
    if mutation == "source":
        (folder / "source.csv").write_bytes(b"wrong")
    elif mutation == "receipt_id":
        data = json.loads((folder / "receipt.json").read_text())
        data["recovery_id"] = "0" * 32
        (folder / "receipt.json").write_text(json.dumps(data))
    elif mutation == "folder_symlink":
        outside = tmp_path / "outside"
        folder.rename(outside)
        folder.symlink_to(outside, target_is_directory=True)
    else:
        path = folder / ("source.csv" if mutation == "source_symlink" else "receipt.json")
        outside = tmp_path / "outside"
        path.rename(outside)
        path.symlink_to(outside)
    with pytest.raises(ValueError):
        read_recovery_source(root, receipt.recovery_id)


@pytest.mark.parametrize("identifier", ["../outside", "foo", "A" * 32, "0" * 31])
def test_recovery_identifier_validation(tmp_path, identifier):
    with pytest.raises(ValueError):
        read_recovery_source(tmp_path, identifier)


def test_transaction_body_failure_rolls_back_without_replaying(tmp_path):
    path = tmp_path / "test.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE records (id INTEGER)")
    db.close()
    events, bodies = [], []
    with pytest.raises(ValueError, match="rejected"):
        with upload_transaction(lambda: sqlite3.connect(path), events) as db:
            bodies.append(1)
            db.execute("INSERT INTO records VALUES (1)")
            raise ValueError("rejected")
    check = sqlite3.connect(path)
    try:
        assert check.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 0
    finally:
        check.close()
    assert len(bodies) == 1 and events[-1].phase == "body"
    assert not events[-1].retry_scheduled


def test_nonbusy_connection_failure_is_not_retried():
    events, calls = [], []
    def unavailable():
        calls.append(1)
        raise sqlite3.OperationalError("disk unavailable")
    with pytest.raises(sqlite3.OperationalError):
        with upload_transaction(unavailable, events):
            pytest.fail("must not execute body")
    assert len(calls) == 1 and events[0].error_code == "DATABASE_ERROR"

