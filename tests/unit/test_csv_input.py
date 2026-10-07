"""Shared byte parsing must not invent delimiters or time metadata."""

import hashlib
import csv

import pytest
import pandas as pd

from flexresearch.csv_input import read_csv_bytes
from flexresearch.lab_tools import build_lab_tool_registry


@pytest.mark.parametrize("separator", [",", ";", "\t"])
def test_supported_delimiters_preserve_values(separator):
    frame = read_csv_bytes(f"time_s{separator}signal\n0{separator}2\n1{separator}4\n".encode())
    assert list(frame) == ["time_s", "signal"]
    assert frame["signal"].tolist() == [2, 4]


def test_one_column_header_is_not_used_as_a_delimiter():
    frame = read_csv_bytes(b"signal\n1\n2\n3\n")
    assert list(frame) == ["signal"] and frame["signal"].tolist() == [1, 2, 3]


def test_tool_parses_the_same_bytes_as_its_hash(tmp_path, monkeypatch):
    from pathlib import Path
    path = tmp_path / "source.csv"
    raw = b"signal\n1\n2\n3\n"
    path.write_bytes(raw)
    original = Path.read_bytes
    def change_after_read(self):
        contents = original(self)
        if self == path:
            path.write_bytes(b"signal\n99\n99\n")
        return contents
    monkeypatch.setattr(Path, "read_bytes", change_after_read)
    result = build_lab_tool_registry().execute("load_csv", {"file_path": str(path)})
    assert result.status == "complete"
    assert result.result["data"]["signal"] == [1, 2, 3]
    assert result.result["source_sha256"] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("raw", [b'a,b\n"1,2\n', b"a,b\n1,2,3,4\n5,6\n7,8,9,10,11\n", b"\xff"])
def test_invalid_csv_is_not_silently_repaired(raw):
    with pytest.raises((csv.Error, UnicodeDecodeError, pd.errors.ParserError)):
        read_csv_bytes(raw)

