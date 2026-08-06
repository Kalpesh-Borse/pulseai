import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import chromadb
import numpy as np
import pytest

from config.settings import Settings
from core.pipeline import run_pipeline
from core.storage import init_db
from schemas.models import RawFeedbackItem

CLASSIFY_RESPONSE = json.dumps(
    {
        "category": "performance",
        "sentiment": {"label": "negative", "score": -0.7},
        "urgency": "high",
        "themes": ["export timeout"],
        "reasoning": "Recurring export timeout.",
    }
)

SUMMARY_RESPONSE = json.dumps(
    {
        "headline": "Export timeouts dominate this week.",
        "key_findings": ["Export timeout theme appeared repeatedly."],
        "recommended_actions": ["Investigate export pipeline."],
        "narrative_text": "Export timeouts were the main story this week.",
    }
)


def _resp(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class FakeEmbedder:
    def embed(self, texts):
        return np.array([[1.0, 0.0, 0.0] for _ in texts])


def _smart_client():
    """Distinguishes classifier vs summarizer calls by system prompt content, so any number
    of calls (1 classify + 1 global summary + N per-week summaries) all succeed validly —
    unlike a fixed-length side_effect list, which is exhausted by the extra per-week calls
    this feature introduces.
    """
    client = MagicMock()

    def _create(model, messages, temperature, response_format):
        system_content = messages[0]["content"]
        if "weekly insight-summary writer" in system_content:
            return _resp(SUMMARY_RESPONSE)
        return _resp(CLASSIFY_RESPONSE)

    client.chat.completions.create.side_effect = _create
    return client


@pytest.fixture
def memory_conn():
    return init_db(":memory:")


@pytest.fixture
def chroma_client():
    # Ephemeral (in-memory) rather than the pipeline's real default of a PersistentClient —
    # no test should ever write to ./chroma_db on disk.
    return chromadb.EphemeralClient()


def test_pipeline_end_to_end_with_mocked_ai_calls(memory_conn, chroma_client):
    client = _smart_client()
    raw_items = [
        RawFeedbackItem(item_id="1", text="Export keeps timing out on large jobs.", submitted_at="2026-07-27"),
        RawFeedbackItem(item_id="2", text="   "),  # rejected during cleaning
    ]

    result = run_pipeline(
        raw_items,
        settings=Settings(),
        client=client,
        embedder=FakeEmbedder(),
        conn=memory_conn,
        chroma_client=chroma_client,
    )

    assert len(result.classified_items) == 1
    assert len(result.rejected_items) == 1
    assert result.aggregate_report.total_items == 2
    assert result.aggregate_report.rejected_items == 1
    assert result.weekly_summary.headline == "Export timeouts dominate this week."


def test_pipeline_never_crashes_when_every_ai_call_fails(memory_conn, chroma_client):
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("simulated API outage")

    raw_items = [RawFeedbackItem(item_id="1", text="Something broke badly.")]

    result = run_pipeline(
        raw_items,
        settings=Settings(),
        client=client,
        embedder=FakeEmbedder(),
        conn=memory_conn,
        chroma_client=chroma_client,
    )

    assert len(result.classified_items) == 1
    assert result.classified_items[0].is_fallback is True
    assert result.weekly_summary.headline  # template fallback still produced a summary


def test_pipeline_handles_fully_empty_batch(memory_conn, chroma_client):
    result = run_pipeline(
        [],
        settings=Settings(),
        client=MagicMock(),
        embedder=FakeEmbedder(),
        conn=memory_conn,
        chroma_client=chroma_client,
    )

    assert result.classified_items == []
    assert result.aggregate_report.total_items == 0
    assert result.weekly_summary.headline
    assert result.weeks == []


def test_weeks_field_populated_for_single_week_batch(memory_conn, chroma_client):
    client = _smart_client()
    raw_items = [
        RawFeedbackItem(item_id="1", text="Export timeout again.", submitted_at="2026-07-27"),
        RawFeedbackItem(item_id="2", text="Another export timeout.", submitted_at="2026-07-29"),
    ]

    result = run_pipeline(
        raw_items,
        settings=Settings(),
        client=client,
        embedder=FakeEmbedder(),
        conn=memory_conn,
        chroma_client=chroma_client,
    )

    assert len(result.weeks) == 1
    week = result.weeks[0]
    assert (week.iso_year, week.iso_week) == (2026, 31)
    assert week.item_count == 2
    assert week.week_label == "Jul 27 - Aug 2, 2026"


def test_items_with_dates_in_different_weeks_split_into_separate_weeks(memory_conn, chroma_client):
    client = _smart_client()
    raw_items = [
        RawFeedbackItem(item_id="1", text="Export timeout.", submitted_at="2026-07-06"),  # week 28
        RawFeedbackItem(item_id="2", text="Export timeout again.", submitted_at="2026-07-27"),  # week 31
        RawFeedbackItem(item_id="3", text="Yet another timeout.", submitted_at="2026-07-28"),  # week 31
    ]

    result = run_pipeline(
        raw_items,
        settings=Settings(),
        client=client,
        embedder=FakeEmbedder(),
        conn=memory_conn,
        chroma_client=chroma_client,
    )

    assert len(result.weeks) == 2
    by_week = {(w.iso_year, w.iso_week): w for w in result.weeks}
    assert by_week[(2026, 28)].item_count == 1
    assert by_week[(2026, 31)].item_count == 2


def test_missing_submitted_at_falls_back_to_current_week(memory_conn, chroma_client):
    from datetime import date

    client = _smart_client()
    raw_items = [RawFeedbackItem(item_id="1", text="No date on this one.")]

    result = run_pipeline(
        raw_items,
        settings=Settings(),
        client=client,
        embedder=FakeEmbedder(),
        conn=memory_conn,
        chroma_client=chroma_client,
    )

    expected_year, expected_week, _ = date.today().isocalendar()
    assert len(result.weeks) == 1
    assert (result.weeks[0].iso_year, result.weeks[0].iso_week) == (expected_year, expected_week)


def test_weeks_accumulate_across_multiple_uploads_sharing_the_same_week(memory_conn, chroma_client):
    client = _smart_client()

    first_upload = [RawFeedbackItem(item_id="1", text="Export timeout.", submitted_at="2026-07-27")]
    result_1 = run_pipeline(
        first_upload,
        settings=Settings(),
        client=client,
        embedder=FakeEmbedder(),
        conn=memory_conn,
        chroma_client=chroma_client,
    )
    assert result_1.weeks[0].item_count == 1

    second_upload = [RawFeedbackItem(item_id="2", text="Another export timeout.", submitted_at="2026-07-29")]
    result_2 = run_pipeline(
        second_upload,
        settings=Settings(),
        client=client,
        embedder=FakeEmbedder(),
        conn=memory_conn,
        chroma_client=chroma_client,
    )

    # The second upload's week result reflects BOTH items (1 from the first upload, 1 from this
    # one) — accumulation, not overwrite.
    assert result_2.weeks[0].item_count == 2
