"""Pipeline orchestration — the single place that wires preprocessing, classification,
clustering, aggregation, summarization, and persistence together. CLI, API, and any future
interface all call this same function so business logic never lives twice.

Two views are produced on every run:
- A "this upload" view (`aggregate_report`/`weekly_summary` at the top level) — the whole
  batch just submitted, regardless of date. Unchanged behavior from before weekly storage
  existed.
- A per-ISO-week view (`weeks`) — each week touched by this upload gets its classified items
  upserted into SQLite, then its cluster/aggregate/summary are RECOMPUTED FROM THE FULL
  ACCUMULATED SET stored for that week (not just this upload), so repeated uploads that land
  in the same week build up one evolving picture rather than overwriting each other.
"""
import sqlite3
from datetime import date

import chromadb
from openai import OpenAI

from config.settings import Settings, get_settings
from core.aggregator import aggregate
from core.classifier import classify_batch
from core.clustering import cluster_themes
from core.embeddings import Embedder, get_default_embedder
from core.storage import get_items_for_week, init_db, save_weekly_report, upsert_items_for_week
from core.summarizer import generate_summary
from core.week_utils import week_key_for, week_label_for
from preprocessing.cleaner import clean_batch
from schemas.models import PipelineResult, RawFeedbackItem, WeekResult


def run_pipeline(
    raw_items: list[RawFeedbackItem],
    settings: Settings | None = None,
    client: OpenAI | None = None,
    embedder: Embedder | None = None,
    conn: sqlite3.Connection | None = None,
    chroma_client: chromadb.ClientAPI | None = None,
) -> PipelineResult:
    settings = settings or get_settings()
    client = client or OpenAI(api_key=settings.openai_api_key)
    embedder = embedder or get_default_embedder()
    conn = conn or init_db(settings.database_path)
    # Persistent by default (not core/clustering.py's own ephemeral default) so the embeddings
    # behind the last clustering pass of a run are actually inspectable on disk afterwards —
    # tests inject an EphemeralClient here to stay disk-free, same pattern as conn/client/embedder.
    chroma_client = chroma_client or chromadb.PersistentClient(path=settings.chroma_persist_dir)

    cleaned, rejected = clean_batch(raw_items, settings.max_feedback_length)
    classified = classify_batch(cleaned, client, settings)

    today = date.today()
    submitted_at_by_id = {item.item_id: item.submitted_at for item in cleaned}
    for item in classified:
        item.iso_year, item.iso_week = week_key_for(submitted_at_by_id.get(item.item_id), today)
    for item in rejected:
        item.iso_year, item.iso_week = week_key_for(item.submitted_at, today)

    global_clusters = cluster_themes(classified, embedder, settings, chroma_client)
    global_report = aggregate(classified, global_clusters, rejected, settings)
    global_summary = generate_summary(global_report, client, settings)

    weeks_touched = sorted({(item.iso_year, item.iso_week) for item in classified})
    week_results: list[WeekResult] = []

    for iso_year, iso_week in weeks_touched:
        week_items = [
            item for item in classified if (item.iso_year, item.iso_week) == (iso_year, iso_week)
        ]
        upsert_items_for_week(conn, iso_year, iso_week, week_items)

        # Recompute from the FULL accumulated set for this week, not just this upload's items —
        # rejected/unusable rows are intentionally not persisted or accumulated (they carry no
        # content to accumulate), so the per-week rejected count only ever reflects this upload.
        accumulated_items = get_items_for_week(conn, iso_year, iso_week)
        week_clusters = cluster_themes(accumulated_items, embedder, settings, chroma_client)
        week_report = aggregate(accumulated_items, week_clusters, [], settings)
        week_summary = generate_summary(week_report, client, settings)

        save_weekly_report(
            conn, iso_year, iso_week, week_report, week_summary, item_count=len(accumulated_items)
        )

        week_results.append(
            WeekResult(
                iso_year=iso_year,
                iso_week=iso_week,
                week_label=week_label_for(iso_year, iso_week),
                item_count=len(accumulated_items),
                aggregate_report=week_report,
                weekly_summary=week_summary,
            )
        )

    return PipelineResult(
        classified_items=classified,
        rejected_items=rejected,
        aggregate_report=global_report,
        weekly_summary=global_summary,
        weeks=week_results,
    )
