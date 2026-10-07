"""Calendar publication windows, retaining source precision rather than inventing dates."""

from __future__ import annotations

import calendar
import re
from datetime import UTC, date, datetime
from typing import Any

from .schemas import StrictModel


def publication_today() -> date:
    return datetime.now(UTC).date()


class PublicationWindow(StrictModel):
    from_date: date
    to_date: date


def publication_window(*, recent_only: bool = False, from_year: int | None = None, to_date: date | None = None) -> PublicationWindow | None:
    if not recent_only and from_year is None and to_date is None:
        return None
    end = to_date or publication_today()
    if end > publication_today():
        raise ValueError("publication window cannot end in the future")
    if recent_only:
        year = end.year - 3
        if from_year is not None and from_year != year:
            raise ValueError("recent_only requires from_year = to_date.year - 3")
        start = date(year, end.month, min(end.day, calendar.monthrange(year, end.month)[1]))
    else:
        start = date(from_year or 1900, 1, 1)
    if start > end:
        raise ValueError("publication window is reversed")
    return PublicationWindow(from_date=start, to_date=end)


def publication_date_from_parts(parts: Any) -> str | None:
    if not isinstance(parts, list) or not 1 <= len(parts) <= 3 or any(isinstance(value, bool) or not isinstance(value, int) for value in parts):
        return None
    text = "-".join(f"{value:04d}" if index == 0 else f"{value:02d}" for index, value in enumerate(parts))
    return text if publication_interval(text) is not None else None


def publication_interval(value: Any) -> tuple[date, date] | None:
    """Return the uncertainty interval for YYYY, YYYY-MM or YYYY-MM-DD."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}(?:-\d{2}){0,2}", value):
        return None
    try:
        parts = [int(part) for part in value.split("-")]
        year = parts[0]
        if len(parts) == 1:
            return date(year, 1, 1), date(year, 12, 31)
        month = parts[1]
        if len(parts) == 2:
            return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
        day = date(*parts)
        return day, day
    except (ValueError, calendar.IllegalMonthError):
        return None


def publication_in_window(record: dict[str, Any], window: PublicationWindow | None) -> bool:
    if window is None:
        return True
    value = record.get("publication_date")
    # Older metadata may contain only a year. That precision remains explicit;
    # accept only when the whole uncertainty interval is within the window.
    year = record.get("year")
    if value is None and not isinstance(year, bool):
        if isinstance(year, int) or (isinstance(year, str) and re.fullmatch(r"\d{4}", year)):
            value = str(year)
    interval = publication_interval(value)
    return bool(interval and window.from_date <= interval[0] <= interval[1] <= window.to_date)

