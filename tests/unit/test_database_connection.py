"""Connection-lifecycle contracts for the local SQLite database."""

from __future__ import annotations

import sqlite3

import pytest

import app as app_module


def assert_connection_is_closed(connection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_get_db_closes_connection_after_successful_context() -> None:
    with app_module.get_db() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1

    assert_connection_is_closed(connection)


def test_get_db_rolls_back_and_closes_connection_after_exception() -> None:
    with pytest.raises(RuntimeError, match="injected transaction failure"):
        with app_module.get_db() as connection:
            connection.execute(
                "INSERT INTO audit_events "
                "(entity_type, entity_id, action, actor, detail_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("test", 0, "rollback-check", "pytest", "{}", app_module.now()),
            )
            raise RuntimeError("injected transaction failure")

    assert_connection_is_closed(connection)
    with app_module.get_db() as verification:
        count = verification.execute(
            "SELECT COUNT(*) FROM audit_events WHERE action = ?",
            ("rollback-check",),
        ).fetchone()[0]
    assert count == 0

