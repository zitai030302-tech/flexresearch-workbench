from datetime import date

import pytest
from pydantic import ValidationError

import flexresearch.publication_dates as dates
from flexresearch.paper_tools import SearchPapersInput


@pytest.mark.parametrize("today,start", [(date(2026, 9, 3), date(2023, 9, 3)), (date(2027, 1, 1), date(2024, 1, 1)), (date(2028, 2, 29), date(2025, 2, 28))])
def test_rolling_window_uses_calendar_years_and_handles_leap_day(monkeypatch, today, start):
    monkeypatch.setattr(dates, "publication_today", lambda: today)
    window = dates.publication_window(recent_only=True)
    assert (window.from_date, window.to_date) == (start, today)
    parsed = SearchPapersInput(query="flexible Bio-Z", recent_only=True)
    assert parsed.from_year == start.year and parsed.to_date == today
    assert parsed.model_dump(mode="json")["to_date"] == today.isoformat()


def test_explicit_historical_window_and_unbounded_search(monkeypatch):
    monkeypatch.setattr(dates, "publication_today", lambda: date(2026, 9, 3))
    assert dates.publication_window() is None
    window = dates.publication_window(from_year=2020, to_date=date(2021, 6, 30))
    assert window.from_date == date(2020, 1, 1)
    assert window.to_date == date(2021, 6, 30)


@pytest.mark.parametrize("kwargs", [{"recent_only": True, "from_year": 2020}, {"to_date": "2027-01-01"}, {"from_year": 2026, "to_date": "2025-01-01"}, {"from_year": 1800}, {"to_date": "2026-02-30"}])
def test_invalid_window_is_rejected_before_network(monkeypatch, kwargs):
    monkeypatch.setattr(dates, "publication_today", lambda: date(2026, 9, 3))
    with pytest.raises(ValidationError):
        SearchPapersInput(query="Bio-Z", **kwargs)


@pytest.mark.parametrize("value,expected", [("2023-09-03", True), ("2023-09-02", False), ("2026-09-03", True), ("2026-09-04", False), ("2024", True), ("2023", False), ("2026", False), ("2023-09", False), ("2023-10", True), ("2026-08", True), ("2026-09", False), ("2026-02-30", False), (None, False)])
def test_date_precision_must_prove_entire_interval_within_window(monkeypatch, value, expected):
    monkeypatch.setattr(dates, "publication_today", lambda: date(2026, 9, 3))
    window = dates.publication_window(recent_only=True)
    assert dates.publication_in_window({"publication_date": value}, window) is expected


@pytest.mark.parametrize("parts,expected", [([2024], "2024"), ([2024, 2], "2024-02"), ([2024, 2, 29], "2024-02-29"), ([2023, 2, 29], None), ([None], None), ([True], None), ([], None), ("2025", None)])
def test_crossref_date_parts_do_not_invent_missing_month_or_day(parts, expected):
    assert dates.publication_date_from_parts(parts) == expected


def test_legacy_year_is_conservative_and_invalid_date_does_not_fall_back(monkeypatch):
    monkeypatch.setattr(dates, "publication_today", lambda: date(2026, 9, 3))
    window = dates.publication_window(recent_only=True)
    assert dates.publication_in_window({"year": 2024}, window)
    assert not dates.publication_in_window({"year": 2026}, window)
    assert not dates.publication_in_window({"year": 2024, "publication_date": "invalid"}, window)


@pytest.mark.parametrize("year,expected", [("2024", True), ("2026", False), ("2023", False), ("n.d.", False), (True, False), (2024.0, False)])
def test_provider_string_year_preserves_annual_precision(monkeypatch, year, expected):
    monkeypatch.setattr(dates, "publication_today", lambda: date(2026, 9, 3))
    window = dates.publication_window(recent_only=True)
    assert dates.publication_in_window({"year": year}, window) is expected

