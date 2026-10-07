"""Shared isolated-vault fixtures for Flask and integration tests."""

from __future__ import annotations

import pytest

import app as app_module


@pytest.fixture(autouse=True)
def isolated_lab_vault(tmp_path, monkeypatch):
    """Never let tests read or write the user's real local lab vault."""
    monkeypatch.setattr(app_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app_module, "DATABASE", tmp_path / "test.db")
    monkeypatch.setattr(app_module, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(app_module, "MEASUREMENT_DIR", tmp_path / "measurements")
    monkeypatch.setattr(app_module, "ARTIFACT_DIR", tmp_path / "artifacts")
    monkeypatch.setattr(app_module, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(app_module, "PROVIDER_SETTINGS_FILE", tmp_path / "provider-settings.json")
    app_module.init_db()

