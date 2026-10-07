"""Parse exactly the bytes whose SHA-256 is recorded, including one-column CSV."""

import csv
import io

import pandas as pd


def read_csv_bytes(raw: bytes, *, nrows: int | None = None) -> pd.DataFrame:
    text = raw.decode("utf-8-sig")
    try:
        delimiter = csv.Sniffer().sniff(text[:2048], delimiters=",;\t").delimiter
    except csv.Error:
        first_line = next((line for line in text.splitlines() if line.strip()), "")
        if any(delimiter in first_line for delimiter in (",", ";", "\t")):
            raise
        # A single column has no delimiter. Never let Sniffer choose a letter
        # from its header as a separator, or invent a sampling-time axis.
        delimiter = ","
    return pd.read_csv(io.StringIO(text), sep=delimiter, nrows=nrows)

