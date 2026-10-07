"""The opt-in demo must not reuse existing research data or credentials."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.showcase import ROOT, configure


def test_existing_vault_is_not_reused(tmp_path):
    with pytest.raises(ValueError):
        configure(tmp_path)


def test_repository_vault_is_not_used():
    with pytest.raises(ValueError):
        configure(ROOT / "data/showcase")


def test_credentials_are_empty_in_isolated_demo(tmp_path, monkeypatch):
    for name in ("FLEXRESEARCH_DATA_DIR", "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL",
                 "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL", "OPENALEX_API_KEY"):
        monkeypatch.setenv(name, "test-only-placeholder")
    path = configure(tmp_path / "new-vault")
    assert Path(os.environ["FLEXRESEARCH_DATA_DIR"]) == path
    assert os.environ["OPENAI_API_KEY"] == os.environ["DEEPSEEK_API_KEY"] == ""


def test_seed_only_runs_in_an_independent_process(tmp_path):
    vault = tmp_path / "showcase"
    result = subprocess.run([sys.executable, str(ROOT / "scripts/showcase.py"), "--vault", str(vault), "--seed-only"],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert (vault / "flexresearch.db").is_file()
