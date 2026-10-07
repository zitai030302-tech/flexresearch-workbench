"""Bounded SQLite upload transactions and independent immutable recovery copies.

Retry only BEGIN IMMEDIATE, before application writes. Never replay a body after
it ran: a failed COMMIT is rolled back, and a post-archive failure is disclosed
as already archived. This is not a distributed transaction or crash checkpoint.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

from pydantic import Field

from .schemas import StrictModel


ARCHIVE_ATTEMPTS = 3
ARCHIVE_BUSY_TIMEOUT_MS = 250


class TransactionAttempt(StrictModel):
    phase: Literal["begin", "commit", "body"]
    attempt: int = Field(ge=1)
    status: Literal["complete", "error"]
    latency_ms: int = Field(ge=0)
    error_code: str | None = None
    retry_scheduled: bool = False
    retry_delay_ms: int = Field(default=0, ge=0)


class RecoveryReceipt(StrictModel):
    schema_version: Literal[1] = 1
    recovery_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    created_at: str
    filename: str
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(gt=0, le=8 * 1024 * 1024)
    intent: Literal["data_analysis"] = "data_analysis"
    error_code: Literal["DATABASE_BUSY"] = "DATABASE_BUSY"
    archive_committed: bool
    measurement_id: int | None = Field(default=None, gt=0)
    experiment_id: int | None = Field(default=None, gt=0)
    attempts: list[TransactionAttempt]


def is_database_busy(error: sqlite3.Error) -> bool:
    code = getattr(error, "sqlite_errorcode", None)
    if isinstance(code, int):
        return code & 0xFF in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
    # Test adapters and older Python versions may not expose sqlite_errorcode.
    return str(error).lower() in {"database is locked", "database table is locked", "database schema is locked"}


@contextmanager
def upload_transaction(connect: Callable[[], sqlite3.Connection], events: list[TransactionAttempt]) -> Iterator[sqlite3.Connection]:
    db = None
    for attempt in range(1, ARCHIVE_ATTEMPTS + 1):
        started = time.monotonic()
        try:
            db = connect()
            db.execute(f"PRAGMA busy_timeout = {ARCHIVE_BUSY_TIMEOUT_MS}")
            db.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:
            if db is not None:
                db.close()
                db = None
            busy = is_database_busy(error)
            retry = busy and attempt < ARCHIVE_ATTEMPTS
            delay_ms = 50 * attempt if retry else 0
            events.append(TransactionAttempt(phase="begin", attempt=attempt, status="error", latency_ms=round((time.monotonic() - started) * 1000), error_code="DATABASE_BUSY" if busy else "DATABASE_ERROR", retry_scheduled=retry, retry_delay_ms=delay_ms))
            if not retry:
                raise
            time.sleep(delay_ms / 1000)
        else:
            events.append(TransactionAttempt(phase="begin", attempt=attempt, status="complete", latency_ms=round((time.monotonic() - started) * 1000)))
            break
    assert db is not None
    phase: Literal["body", "commit"] = "body"
    started = time.monotonic()
    try:
        yield db
        phase = "commit"
        started = time.monotonic()
        db.commit()
        events.append(TransactionAttempt(phase="commit", attempt=attempt, status="complete", latency_ms=round((time.monotonic() - started) * 1000)))
    except BaseException as error:
        # No automatic body replay; close also abandons any unfinished txn.
        events.append(TransactionAttempt(phase=phase, attempt=attempt, status="error", latency_ms=round((time.monotonic() - started) * 1000), error_code="DATABASE_BUSY" if isinstance(error, sqlite3.Error) and is_database_busy(error) else "TRANSACTION_FAILED"))
        db.rollback()
        raise
    finally:
        db.close()


def _write_exclusive(path: Path, content: bytes) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def preserve_upload(root: Path, raw: bytes, filename: str, *, archive_committed: bool, events: list[TransactionAttempt], measurement_id: int | None = None, experiment_id: int | None = None) -> RecoveryReceipt:
    receipt = RecoveryReceipt(recovery_id=uuid.uuid4().hex, created_at=datetime.now(UTC).isoformat(), filename=Path(filename).name, source_sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw), archive_committed=archive_committed, measurement_id=measurement_id if archive_committed else None, experiment_id=experiment_id if archive_committed else None, attempts=events)
    folder = root / receipt.recovery_id
    folder.mkdir(mode=0o700, parents=True, exist_ok=False)
    _write_exclusive(folder / "source.csv", raw)
    # A receipt is published only after the durable raw copy is complete.
    _write_exclusive(folder / "receipt.json", receipt.model_dump_json(indent=2).encode())
    return receipt


def read_recovery_source(root: Path, recovery_id: str) -> tuple[RecoveryReceipt, bytes]:
    if not re.fullmatch(r"[a-f0-9]{32}", recovery_id):
        raise ValueError("invalid recovery identifier")
    folder = root / recovery_id
    if folder.is_symlink() or not folder.resolve().is_relative_to(root.resolve()):
        raise ValueError("invalid recovery path")
    for name in ("source.csv", "receipt.json"):
        if (folder / name).is_symlink():
            raise ValueError("invalid recovery path")
    receipt = RecoveryReceipt.model_validate_json((folder / "receipt.json").read_bytes())
    if receipt.recovery_id != recovery_id:
        raise ValueError("receipt identity mismatch")
    raw = (folder / "source.csv").read_bytes()
    if len(raw) != receipt.size_bytes or hashlib.sha256(raw).hexdigest() != receipt.source_sha256:
        raise ValueError("recovery source integrity mismatch")
    return receipt, raw


def public_recovery(receipt: RecoveryReceipt) -> dict[str, Any]:
    return {
        "id": receipt.recovery_id, "filename": receipt.filename,
        "sha256": receipt.source_sha256, "sizeBytes": receipt.size_bytes,
        "rawPreserved": True, "archiveCommitted": receipt.archive_committed,
        "measurementId": receipt.measurement_id, "experimentId": receipt.experiment_id,
        "sourceUrl": f"/api/upload-recovery/{receipt.recovery_id}/source",
        "transactionAttempts": [item.model_dump() for item in receipt.attempts],
        "maxBeginAttempts": ARCHIVE_ATTEMPTS,
    }

