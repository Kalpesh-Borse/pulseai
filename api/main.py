"""FastAPI interface — a thin layer over core/pipeline.py. No business logic lives here;
every endpoint just adapts HTTP in/out to the same core functions the CLI calls.
"""
import csv
import io
import logging
import sqlite3

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from config.settings import get_settings
from core.pipeline import run_pipeline
from core.storage import get_items_for_week, get_weekly_report, init_db, list_available_weeks
from schemas.models import AggregateReport, ClassifiedFeedback, PipelineResult, RawFeedbackItem, WeeklySummary

logger = logging.getLogger(__name__)

app = FastAPI(title="PulseAI", description="AI-powered feedback insight engine for Memsy")

# In-process state holding the most recently processed upload — kept as the default view so
# "just uploaded, see results immediately" needs no year/week params. Any *stored* week
# (including this one, once processed) is also reachable via ?year=&week= against SQLite —
# see core/storage.py — which is what the dashboard's calendar/week picker uses.
_latest_result: PipelineResult | None = None

REQUIRED_COLUMNS = {"item_id", "text"}


def get_conn() -> sqlite3.Connection:
    """FastAPI dependency — a fresh connection per request rather than one shared global
    (sync endpoints run in a thread pool, and a single sqlite3.Connection isn't safe to reuse
    across threads). Overridden in tests via app.dependency_overrides to inject a shared
    in-memory connection instead of touching a real file.
    """
    return init_db(get_settings().database_path)


def _parse_csv_bytes(raw_bytes: bytes) -> list[RawFeedbackItem]:
    try:
        text = raw_bytes.decode("utf-8", errors="ignore")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not decode file as UTF-8 text: {e}")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
        raise HTTPException(
            status_code=400,
            detail=f"CSV must contain at least these columns: {sorted(REQUIRED_COLUMNS)}, "
            f"found: {reader.fieldnames}",
        )

    return [
        RawFeedbackItem(
            item_id=row["item_id"],
            text=row.get("text", "") or "",
            source=row.get("source") or None,
            submitted_at=row.get("submitted_at") or None,
        )
        for row in reader
    ]


@app.get("/api/health")
def health():
    settings = get_settings()
    return {"status": "ok", "api_key_configured": bool(settings.openai_api_key)}


@app.post("/api/process")
async def process_batch(file: UploadFile, conn: sqlite3.Connection = Depends(get_conn)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    raw_items = _parse_csv_bytes(raw_bytes)
    if not raw_items:
        raise HTTPException(status_code=400, detail="CSV has no data rows.")

    global _latest_result
    try:
        _latest_result = run_pipeline(raw_items, settings=get_settings(), conn=conn)
    except Exception as e:  # noqa: BLE001 — never let an unexpected error crash the API
        logger.exception("pipeline run failed")
        raise HTTPException(status_code=502, detail=f"Processing failed: {e}")

    return {
        "processed": len(_latest_result.classified_items),
        "rejected": len(_latest_result.rejected_items),
    }


def _require_result() -> PipelineResult:
    if _latest_result is None:
        raise HTTPException(
            status_code=404,
            detail="No batch has been processed yet. POST a CSV to /api/process first.",
        )
    return _latest_result


def _check_year_week_pairing(year: int | None, week: int | None) -> None:
    if (year is None) != (week is None):
        raise HTTPException(
            status_code=400, detail="year and week must be provided together, or not at all."
        )


def _resolve_report_and_summary(
    year: int | None, week: int | None, conn: sqlite3.Connection
) -> tuple[AggregateReport, WeeklySummary]:
    _check_year_week_pairing(year, week)
    if year is None:
        result = _require_result()
        return result.aggregate_report, result.weekly_summary

    stored = get_weekly_report(conn, year, week)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"No data found for {year}-W{week}.")
    return stored


def _resolve_items(
    year: int | None, week: int | None, conn: sqlite3.Connection
) -> list[ClassifiedFeedback]:
    _check_year_week_pairing(year, week)
    if year is None:
        return _require_result().classified_items
    return get_items_for_week(conn, year, week)


@app.get("/api/weeks")
def get_weeks(conn: sqlite3.Connection = Depends(get_conn)):
    return list_available_weeks(conn)


@app.get("/api/results/categories")
def get_categories(
    year: int | None = None, week: int | None = None, conn: sqlite3.Connection = Depends(get_conn)
):
    report, _ = _resolve_report_and_summary(year, week, conn)
    return [c.model_dump() for c in report.category_counts]


@app.get("/api/results/sentiment")
def get_sentiment(
    year: int | None = None, week: int | None = None, conn: sqlite3.Connection = Depends(get_conn)
):
    report, _ = _resolve_report_and_summary(year, week, conn)
    return report.sentiment_distribution.model_dump()


@app.get("/api/results/urgency")
def get_urgency(
    year: int | None = None, week: int | None = None, conn: sqlite3.Connection = Depends(get_conn)
):
    report, _ = _resolve_report_and_summary(year, week, conn)
    return report.urgency_breakdown.model_dump()


@app.get("/api/results/themes")
def get_themes(
    year: int | None = None, week: int | None = None, conn: sqlite3.Connection = Depends(get_conn)
):
    report, _ = _resolve_report_and_summary(year, week, conn)
    return [t.model_dump() for t in report.top_themes]


@app.get("/api/results/items")
def get_items(
    year: int | None = None, week: int | None = None, conn: sqlite3.Connection = Depends(get_conn)
):
    return [item.model_dump() for item in _resolve_items(year, week, conn)]


@app.get("/api/results/summary")
def get_summary(
    year: int | None = None, week: int | None = None, conn: sqlite3.Connection = Depends(get_conn)
):
    _, summary = _resolve_report_and_summary(year, week, conn)
    return summary.model_dump()


@app.get("/api/results/full")
def get_full_result():
    return _require_result().model_dump()


@app.get("/")
def root():
    return RedirectResponse(url="/dashboard/index.html")


app.mount("/dashboard", StaticFiles(directory="dashboard", html=True), name="dashboard")
