"""Contracts for public bibliographic discovery and evidence selection."""

from typing import Any
import re
from html import unescape
from datetime import date

from pydantic import Field, HttpUrl, model_validator

from .schemas import StrictModel
from .publication_dates import PublicationWindow, publication_window


class SearchPapersInput(StrictModel):
    query: str = Field(min_length=2, max_length=400)
    recent_only: bool = False
    limit: int = Field(default=8, ge=1, le=16)
    from_year: int | None = Field(default=None, ge=1900, le=2100)
    to_date: date | None = None

    @model_validator(mode="after")
    def normalize_date_window(self) -> "SearchPapersInput":
        window = publication_window(recent_only=self.recent_only, from_year=self.from_year, to_date=self.to_date)
        if window:
            self.from_year = window.from_date.year
            self.to_date = window.to_date
        return self


class PaperCandidate(StrictModel):
    source: str
    title: str = Field(min_length=1)
    url: HttpUrl
    doi: str | None = None
    journal: str = ""
    year: int | None = None
    publication_date: str | None = None
    authors: str = ""
    citedBy: int = 0
    type: str = ""
    abstract: str = ""
    quality: dict[str, Any] = Field(default_factory=dict)
    relevance: dict[str, Any] = Field(default_factory=dict)


class SearchPapersOutput(StrictModel):
    query: str
    items: list[PaperCandidate]
    provider_errors: list[str] = Field(default_factory=list)
    evidence_level: str = "bibliographic_metadata_only"
    rejected_records: int = 0
    date_window: PublicationWindow | None = None
    date_excluded_records: int = 0


class PaperSelection(StrictModel):
    """Model selects observed records; factual text comes from those records."""

    selected_urls: list[HttpUrl] = Field(max_length=16)


def is_publication_notice(title: str) -> bool:
    """Conservative title filter; Crossref's journal-article type includes notices."""
    return bool(re.search(r"call\s+for\s+papers|publication\s+information|table\s+of\s+contents|editorial\s+board|masthead|stronger\s+venue\s+for|^editorial\b|^front\s+matter\b", unescape(title), re.IGNORECASE))


def paper_exclusion_reason(record: dict[str, Any], query: str) -> str | None:
    """Conservative discovery filters, not a scientific-validity certificate.

    Crossref can label trial-registration summaries as journal articles and
    gives supplement datasets their own DOI. They are not research-paper
    results. An explicit Bio-Z query must also match that measurement modality,
    rather than matching only generic words such as pulse or waveform.
    """
    if is_publication_notice(record.get("title", "")):
        return "publication_notice"
    doi = (record.get("doi") or "").lower()
    journal = (record.get("journal") or "").lower()
    if re.search(r"(?:^|/)ct1-nct\d+|/isrctn\d+", doi) or "isrctn.com" in journal:
        return "trial_registration"
    if record.get("type", "").lower() in {"dataset", "component", "reference-entry", "book-chapter"} or re.search(r"\.s\d{3}$|/mm\d+$", doi):
        return "non_paper_record"
    modality = r"\bbio[\s-]?(?:impedance|z)\b|生物阻抗|\bimpedance\s+(?:plethysmograph\w*|cardiograph\w*)\b|\belectrical\s+impedance\b"
    if re.search(modality, query, re.I) and not re.search(modality, " ".join(str(record.get(key) or "") for key in ("title", "abstract")), re.I):
        return "requested_modality_not_in_metadata"
    return None

