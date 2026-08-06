"""Pure date/week math — no I/O, no database. Kept separate from storage.py so the
bucketing logic (which date maps to which ISO calendar week) is trivially unit-testable.

ISO calendar weeks (Monday-Sunday) are used instead of naively chunking a month into four
7-day blocks, since months don't divide evenly into weeks and that produces ambiguous,
inconsistent boundaries. The calendar UI still labels weeks "Week 1, Week 2, ..." for
readability, but the underlying key is always the unambiguous (iso_year, iso_week) pair.
"""
from datetime import date, timedelta

_MONTH_ABBR = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def week_key_for(submitted_at: str | None, fallback_date: date) -> tuple[int, int]:
    """Returns (iso_year, iso_week) for the given date string, or for fallback_date if
    submitted_at is missing or unparseable — so a bad/missing date never drops an item, it
    just lands in the current week instead of crashing or being silently discarded.
    """
    parsed = _parse_date(submitted_at)
    target = parsed or fallback_date
    iso_year, iso_week, _ = target.isocalendar()
    return iso_year, iso_week


def _format_day(d: date) -> str:
    return f"{_MONTH_ABBR[d.month - 1]} {d.day}"


def week_label_for(iso_year: int, iso_week: int) -> str:
    """e.g. 'Jul 27 - Aug 2, 2026', or 'Dec 29, 2025 - Jan 4, 2026' across a year boundary."""
    monday = date.fromisocalendar(iso_year, iso_week, 1)
    sunday = monday + timedelta(days=6)

    if monday.year != sunday.year:
        return f"{_format_day(monday)}, {monday.year} - {_format_day(sunday)}, {sunday.year}"
    return f"{_format_day(monday)} - {_format_day(sunday)}, {sunday.year}"


def month_key_for_week(iso_year: int, iso_week: int) -> tuple[int, int]:
    """Buckets a week under the month its Monday (start date) falls in."""
    monday = date.fromisocalendar(iso_year, iso_week, 1)
    return monday.year, monday.month


def month_label_for(year: int, month: int) -> str:
    return f"{_MONTH_ABBR[month - 1]} {year}"
