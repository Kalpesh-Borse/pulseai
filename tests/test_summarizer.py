import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from config.settings import Settings
from core.summarizer import generate_summary
from schemas.models import (
    AggregateReport,
    Category,
    CategoryCount,
    SentimentDistribution,
    ThemeCluster,
    UrgencyBreakdown,
)

VALID_SUMMARY = json.dumps(
    {
        "headline": "Export timeouts are this week's top issue.",
        "key_findings": ["Export timeout theme appeared in 3 items."],
        "recommended_actions": ["Investigate export pipeline performance."],
        "narrative_text": "Export timeouts dominated this week's feedback.",
    }
)


def _mock_client_with_responses(*contents: str) -> MagicMock:
    client = MagicMock()
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=c))]) for c in contents
    ]
    client.chat.completions.create.side_effect = responses
    return client


def _report() -> AggregateReport:
    return AggregateReport(
        total_items=3,
        rejected_items=0,
        category_counts=[CategoryCount(category=Category.PERFORMANCE, count=3)],
        sentiment_distribution=SentimentDistribution(positive=0, neutral=0, negative=3, average_score=-0.6),
        urgency_breakdown=UrgencyBreakdown(low=0, medium=1, high=2, critical=0),
        top_themes=[
            ThemeCluster(
                cluster_id="cluster_0",
                label="export timeout",
                item_ids=["1", "2", "3"],
                count=3,
                example_quotes=["Export keeps timing out."],
            )
        ],
    )


def test_generate_summary_succeeds_on_first_valid_response():
    client = _mock_client_with_responses(VALID_SUMMARY)
    result = generate_summary(_report(), client, Settings())

    assert "Export" in result.headline
    assert client.chat.completions.create.call_count == 1


def test_generate_summary_retries_once_then_succeeds():
    client = _mock_client_with_responses("not json", VALID_SUMMARY)
    result = generate_summary(_report(), client, Settings())

    assert result.headline
    assert client.chat.completions.create.call_count == 2


def test_generate_summary_falls_back_to_template_after_repeated_failure():
    client = _mock_client_with_responses("bad", "still bad")
    result = generate_summary(_report(), client, Settings())

    assert "fallback" in result.narrative_text.lower()
    assert "export timeout" in result.key_findings[1].lower() or any(
        "export timeout" in f.lower() for f in result.key_findings
    )


def test_fallback_never_crashes_on_empty_report():
    empty_report = AggregateReport(
        total_items=0,
        rejected_items=0,
        category_counts=[],
        sentiment_distribution=SentimentDistribution(positive=0, neutral=0, negative=0, average_score=0.0),
        urgency_breakdown=UrgencyBreakdown(low=0, medium=0, high=0, critical=0),
        top_themes=[],
    )
    client = _mock_client_with_responses("bad", "still bad")
    result = generate_summary(empty_report, client, Settings())

    assert result.headline
