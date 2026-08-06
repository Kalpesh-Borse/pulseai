from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from core.storage import init_db, save_weekly_report, upsert_items_for_week
from schemas.models import (
    AggregateReport,
    Category,
    CategoryCount,
    ClassifiedFeedback,
    PipelineResult,
    Sentiment,
    SentimentDistribution,
    SentimentLabel,
    ThemeCluster,
    UrgencyBreakdown,
    UrgencyLevel,
    WeeklySummary,
)

client = TestClient(api_main.app)


@pytest.fixture(autouse=True)
def in_memory_db():
    """Every test gets its own fresh in-memory SQLite connection, overriding the real
    file-backed one `get_conn` would otherwise open — no test ever touches disk.
    """
    conn = init_db(":memory:")
    api_main.app.dependency_overrides[api_main.get_conn] = lambda: conn
    yield conn
    api_main.app.dependency_overrides.clear()


def _fake_result() -> PipelineResult:
    return PipelineResult(
        classified_items=[
            ClassifiedFeedback(
                item_id="1",
                text="Export keeps timing out.",
                category=Category.PERFORMANCE,
                sentiment=Sentiment(label=SentimentLabel.NEGATIVE, score=-0.7),
                urgency=UrgencyLevel.HIGH,
                themes=["export timeout"],
                reasoning="test",
            )
        ],
        rejected_items=[],
        aggregate_report=AggregateReport(
            total_items=1,
            rejected_items=0,
            category_counts=[CategoryCount(category=Category.PERFORMANCE, count=1)],
            sentiment_distribution=SentimentDistribution(positive=0, neutral=0, negative=1, average_score=-0.7),
            urgency_breakdown=UrgencyBreakdown(low=0, medium=0, high=1, critical=0),
            top_themes=[
                ThemeCluster(cluster_id="c0", label="export timeout", item_ids=["1"], count=1)
            ],
        ),
        weekly_summary=WeeklySummary(
            headline="Export timeouts are the top issue.",
            key_findings=["1 item about export timeout."],
            recommended_actions=["Investigate export pipeline."],
            narrative_text="Export timeouts dominated this week.",
        ),
    )


@pytest.fixture(autouse=True)
def reset_state():
    api_main._latest_result = None
    yield
    api_main._latest_result = None


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_results_endpoints_return_404_before_any_batch_processed():
    response = client.get("/api/results/summary")
    assert response.status_code == 404
    assert "process" in response.json()["detail"].lower()


def test_process_batch_success_populates_results():
    csv_content = "item_id,text\n1,Export keeps timing out.\n"
    with patch("api.main.run_pipeline", return_value=_fake_result()):
        response = client.post(
            "/api/process", files={"file": ("feedback.csv", csv_content, "text/csv")}
        )
    assert response.status_code == 200
    assert response.json()["processed"] == 1

    categories = client.get("/api/results/categories")
    assert categories.status_code == 200
    assert categories.json()[0]["category"] == "performance"

    summary = client.get("/api/results/summary")
    assert summary.status_code == 200
    assert summary.json()["headline"] == "Export timeouts are the top issue."

    items = client.get("/api/results/items")
    assert items.status_code == 200
    assert items.json()[0]["item_id"] == "1"
    assert items.json()[0]["category"] == "performance"
    assert items.json()[0]["sentiment"]["label"] == "negative"


def test_process_batch_rejects_empty_file():
    response = client.post("/api/process", files={"file": ("feedback.csv", b"", "text/csv")})
    assert response.status_code == 400


def test_process_batch_rejects_non_csv_filename():
    response = client.post(
        "/api/process", files={"file": ("feedback.txt", "item_id,text\n1,hi\n", "text/plain")}
    )
    assert response.status_code == 400


def test_process_batch_rejects_missing_required_columns():
    csv_content = "id,message\n1,hello\n"
    response = client.post("/api/process", files={"file": ("feedback.csv", csv_content, "text/csv")})
    assert response.status_code == 400


def test_process_batch_handles_pipeline_failure_gracefully():
    csv_content = "item_id,text\n1,Export keeps timing out.\n"
    with patch("api.main.run_pipeline", side_effect=RuntimeError("simulated invalid API key")):
        response = client.post(
            "/api/process", files={"file": ("feedback.csv", csv_content, "text/csv")}
        )
    assert response.status_code == 502
    assert "process" in response.json()["detail"].lower() or "failed" in response.json()["detail"].lower()


def _seed_week(conn, iso_year, iso_week, item_id="A1"):
    item = ClassifiedFeedback(
        item_id=item_id,
        text="Stored week feedback.",
        category=Category.BILLING,
        sentiment=Sentiment(label=SentimentLabel.NEGATIVE, score=-0.5),
        urgency=UrgencyLevel.MEDIUM,
        themes=["duplicate charge"],
        reasoning="test",
    )
    upsert_items_for_week(conn, iso_year, iso_week, [item])
    report = AggregateReport(
        total_items=1,
        rejected_items=0,
        category_counts=[CategoryCount(category=Category.BILLING, count=1)],
        sentiment_distribution=SentimentDistribution(positive=0, neutral=0, negative=1, average_score=-0.5),
        urgency_breakdown=UrgencyBreakdown(low=0, medium=1, high=0, critical=0),
        top_themes=[ThemeCluster(cluster_id="c0", label="duplicate charge", item_ids=[item_id], count=1)],
    )
    summary = WeeklySummary(
        headline="Billing issues this week.",
        key_findings=["finding"],
        recommended_actions=["action"],
        narrative_text="narrative",
    )
    save_weekly_report(conn, iso_year, iso_week, report, summary, item_count=1)


def test_weeks_endpoint_returns_calendar_data(in_memory_db):
    _seed_week(in_memory_db, 2026, 31)

    response = client.get("/api/weeks")
    assert response.status_code == 200
    months = response.json()
    assert months[0]["month_label"] == "Jul 2026"
    assert months[0]["weeks"][0]["iso_week"] == 31


def test_weeks_endpoint_empty_when_nothing_stored():
    response = client.get("/api/weeks")
    assert response.status_code == 200
    assert response.json() == []


def test_results_endpoints_read_specific_week_from_storage(in_memory_db):
    _seed_week(in_memory_db, 2026, 31)

    categories = client.get("/api/results/categories", params={"year": 2026, "week": 31})
    assert categories.status_code == 200
    assert categories.json()[0]["category"] == "billing"

    summary = client.get("/api/results/summary", params={"year": 2026, "week": 31})
    assert summary.status_code == 200
    assert summary.json()["headline"] == "Billing issues this week."

    items = client.get("/api/results/items", params={"year": 2026, "week": 31})
    assert items.status_code == 200
    assert items.json()[0]["item_id"] == "A1"


def test_results_endpoint_404_for_unstored_week(in_memory_db):
    response = client.get("/api/results/summary", params={"year": 2099, "week": 1})
    assert response.status_code == 404


def test_results_endpoint_400_when_only_one_of_year_week_given(in_memory_db):
    response = client.get("/api/results/summary", params={"year": 2026})
    assert response.status_code == 400


def test_process_batch_persists_to_a_queryable_week(in_memory_db):
    csv_content = "item_id,text\n1,Export keeps timing out.\n"
    with patch("api.main.run_pipeline") as mock_run:
        result = _fake_result()
        mock_run.return_value = result
        client.post("/api/process", files={"file": ("feedback.csv", csv_content, "text/csv")})

    # run_pipeline itself is mocked (no real classification/persistence happens here), but the
    # /api/process endpoint must pass the request-scoped conn through to it so a real run would
    # persist through the same connection the dependency override controls.
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs["conn"] is in_memory_db
