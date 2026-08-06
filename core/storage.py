"""The only module that touches SQLite. Two tables: one row per feedback item (keyed by
item + the ISO week it was bucketed into), one row per week's recomputed aggregate report
and narrative summary. Everything else in the app goes through the functions here rather
than writing SQL directly.
"""
import json
import sqlite3
from datetime import datetime, timezone

from core.week_utils import month_key_for_week, month_label_for, week_label_for
from schemas.models import AggregateReport, ClassifiedFeedback, Sentiment, WeeklySummary

_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback_items (
    item_id TEXT NOT NULL,
    iso_year INTEGER NOT NULL,
    iso_week INTEGER NOT NULL,
    text TEXT NOT NULL,
    category TEXT NOT NULL,
    sentiment_label TEXT NOT NULL,
    sentiment_score REAL NOT NULL,
    urgency TEXT NOT NULL,
    themes_json TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    is_fallback INTEGER NOT NULL,
    PRIMARY KEY (item_id, iso_year, iso_week)
);

CREATE TABLE IF NOT EXISTS weekly_reports (
    iso_year INTEGER NOT NULL,
    iso_week INTEGER NOT NULL,
    week_label TEXT NOT NULL,
    aggregate_report_json TEXT NOT NULL,
    weekly_summary_json TEXT NOT NULL,
    item_count INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (iso_year, iso_week)
);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    # check_same_thread=False: FastAPI runs sync endpoints in a thread pool, so a connection
    # handed out by the get_conn dependency (or shared across sequential test calls via a
    # dependency override) may be used from a different thread than the one that created it.
    # This is safe here because each connection is only ever accessed sequentially, never
    # concurrently from multiple threads at once.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def upsert_items_for_week(
    conn: sqlite3.Connection, iso_year: int, iso_week: int, items: list[ClassifiedFeedback]
) -> None:
    rows = [
        (
            item.item_id,
            iso_year,
            iso_week,
            item.text,
            item.category.value,
            item.sentiment.label.value,
            item.sentiment.score,
            item.urgency.value,
            json.dumps(item.themes),
            item.reasoning,
            int(item.is_fallback),
        )
        for item in items
    ]
    conn.executemany(
        """
        INSERT OR REPLACE INTO feedback_items
            (item_id, iso_year, iso_week, text, category, sentiment_label, sentiment_score,
             urgency, themes_json, reasoning, is_fallback)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def get_items_for_week(
    conn: sqlite3.Connection, iso_year: int, iso_week: int
) -> list[ClassifiedFeedback]:
    cursor = conn.execute(
        """
        SELECT item_id, text, category, sentiment_label, sentiment_score, urgency,
               themes_json, reasoning, is_fallback
        FROM feedback_items
        WHERE iso_year = ? AND iso_week = ?
        ORDER BY item_id
        """,
        (iso_year, iso_week),
    )
    items = []
    for row in cursor.fetchall():
        (item_id, text, category, sentiment_label, sentiment_score, urgency,
         themes_json, reasoning, is_fallback) = row
        items.append(
            ClassifiedFeedback(
                item_id=item_id,
                text=text,
                category=category,
                sentiment=Sentiment(label=sentiment_label, score=sentiment_score),
                urgency=urgency,
                themes=json.loads(themes_json),
                reasoning=reasoning,
                is_fallback=bool(is_fallback),
                iso_year=iso_year,
                iso_week=iso_week,
            )
        )
    return items


def save_weekly_report(
    conn: sqlite3.Connection,
    iso_year: int,
    iso_week: int,
    aggregate_report: AggregateReport,
    weekly_summary: WeeklySummary,
    item_count: int,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO weekly_reports
            (iso_year, iso_week, week_label, aggregate_report_json, weekly_summary_json,
             item_count, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            iso_year,
            iso_week,
            week_label_for(iso_year, iso_week),
            aggregate_report.model_dump_json(),
            weekly_summary.model_dump_json(),
            item_count,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def get_weekly_report(
    conn: sqlite3.Connection, iso_year: int, iso_week: int
) -> tuple[AggregateReport, WeeklySummary] | None:
    cursor = conn.execute(
        """
        SELECT aggregate_report_json, weekly_summary_json
        FROM weekly_reports
        WHERE iso_year = ? AND iso_week = ?
        """,
        (iso_year, iso_week),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    aggregate_report_json, weekly_summary_json = row
    return (
        AggregateReport.model_validate_json(aggregate_report_json),
        WeeklySummary.model_validate_json(weekly_summary_json),
    )


def list_available_weeks(conn: sqlite3.Connection) -> list[dict]:
    """Returns months in chronological order, each with its weeks in chronological order,
    ready for the calendar UI: [{year, month, month_label, weeks: [{iso_year, iso_week,
    week_number_in_month, week_label, item_count}, ...]}, ...]
    """
    cursor = conn.execute(
        "SELECT iso_year, iso_week, week_label, item_count FROM weekly_reports "
        "ORDER BY iso_year, iso_week"
    )
    rows = cursor.fetchall()

    months: dict[tuple[int, int], dict] = {}
    for iso_year, iso_week, week_label, item_count in rows:
        month_key = month_key_for_week(iso_year, iso_week)
        month_entry = months.setdefault(
            month_key,
            {
                "year": month_key[0],
                "month": month_key[1],
                "month_label": month_label_for(*month_key),
                "weeks": [],
            },
        )
        month_entry["weeks"].append(
            {
                "iso_year": iso_year,
                "iso_week": iso_week,
                "week_number_in_month": len(month_entry["weeks"]) + 1,
                "week_label": week_label,
                "item_count": item_count,
            }
        )

    return [months[key] for key in sorted(months.keys())]
