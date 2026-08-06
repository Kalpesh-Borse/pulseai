from datetime import date

from core.week_utils import (
    month_key_for_week,
    month_label_for,
    week_key_for,
    week_label_for,
)


def test_week_key_for_valid_iso_date():
    # 2026-07-27 is a Monday, ISO week 31 of 2026.
    assert week_key_for("2026-07-27", fallback_date=date(2020, 1, 1)) == (2026, 31)


def test_week_key_for_missing_date_falls_back():
    fallback = date(2026, 7, 28)
    assert week_key_for(None, fallback_date=fallback) == fallback.isocalendar()[:2]


def test_week_key_for_empty_string_falls_back():
    fallback = date(2026, 7, 28)
    assert week_key_for("", fallback_date=fallback) == fallback.isocalendar()[:2]


def test_week_key_for_malformed_date_falls_back_without_crashing():
    fallback = date(2026, 7, 28)
    assert week_key_for("not-a-date", fallback_date=fallback) == fallback.isocalendar()[:2]
    assert week_key_for("30/07/2026", fallback_date=fallback) == fallback.isocalendar()[:2]


def test_week_key_for_same_week_different_days():
    # 2026-07-27 (Mon) through 2026-08-02 (Sun) are all ISO week 31 of 2026.
    assert week_key_for("2026-07-27", date(2020, 1, 1)) == (2026, 31)
    assert week_key_for("2026-08-02", date(2020, 1, 1)) == (2026, 31)


def test_week_label_for_within_single_month():
    # ISO week 28 of 2026: Mon Jul 6 - Sun Jul 12.
    assert week_label_for(2026, 28) == "Jul 6 - Jul 12, 2026"


def test_week_label_for_crossing_month_boundary():
    assert week_label_for(2026, 31) == "Jul 27 - Aug 2, 2026"


def test_week_label_for_crossing_year_boundary():
    # ISO week 1 of 2026 starts Mon Dec 29, 2025.
    assert week_label_for(2026, 1) == "Dec 29, 2025 - Jan 4, 2026"


def test_month_key_for_week_buckets_by_monday():
    # Week 31 of 2026 starts Jul 27, so it belongs to July even though it ends in August.
    assert month_key_for_week(2026, 31) == (2026, 7)


def test_month_label_for():
    assert month_label_for(2026, 7) == "Jul 2026"
