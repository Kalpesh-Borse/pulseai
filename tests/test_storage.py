from core.storage import (
    get_items_for_week,
    get_weekly_report,
    init_db,
    list_available_weeks,
    save_weekly_report,
    upsert_items_for_week,
)
from schemas.models import (
    AggregateReport,
    Category,
    CategoryCount,
    ClassifiedFeedback,
    Sentiment,
    SentimentDistribution,
    SentimentLabel,
    UrgencyBreakdown,
    UrgencyLevel,
    WeeklySummary,
)


def _item(item_id: str, category=Category.PERFORMANCE, theme="export timeout") -> ClassifiedFeedback:
    return ClassifiedFeedback(
        item_id=item_id,
        text=f"feedback text for {item_id}",
        category=category,
        sentiment=Sentiment(label=SentimentLabel.NEGATIVE, score=-0.6),
        urgency=UrgencyLevel.HIGH,
        themes=[theme],
        reasoning="test reasoning",
    )


def _report(count=2) -> AggregateReport:
    return AggregateReport(
        total_items=count,
        rejected_items=0,
        category_counts=[CategoryCount(category=Category.PERFORMANCE, count=count)],
        sentiment_distribution=SentimentDistribution(positive=0, neutral=0, negative=count, average_score=-0.6),
        urgency_breakdown=UrgencyBreakdown(low=0, medium=0, high=count, critical=0),
        top_themes=[],
    )


def _summary() -> WeeklySummary:
    return WeeklySummary(
        headline="Export timeouts dominate.",
        key_findings=["finding 1"],
        recommended_actions=["action 1"],
        narrative_text="narrative here",
    )


def test_upsert_and_get_items_roundtrip():
    conn = init_db(":memory:")
    items = [_item("A1"), _item("A2", category=Category.BILLING, theme="duplicate charge")]

    upsert_items_for_week(conn, 2026, 31, items)
    result = get_items_for_week(conn, 2026, 31)

    assert len(result) == 2
    a1 = next(i for i in result if i.item_id == "A1")
    assert a1.category == Category.PERFORMANCE
    assert a1.themes == ["export timeout"]
    assert a1.sentiment.label == SentimentLabel.NEGATIVE
    assert a1.urgency == UrgencyLevel.HIGH
    assert a1.iso_year == 2026
    assert a1.iso_week == 31


def test_upsert_same_item_id_replaces_not_duplicates():
    conn = init_db(":memory:")
    upsert_items_for_week(conn, 2026, 31, [_item("A1", category=Category.PERFORMANCE)])
    upsert_items_for_week(conn, 2026, 31, [_item("A1", category=Category.BILLING)])

    result = get_items_for_week(conn, 2026, 31)
    assert len(result) == 1
    assert result[0].category == Category.BILLING


def test_get_items_for_week_with_no_data_returns_empty_list():
    conn = init_db(":memory:")
    assert get_items_for_week(conn, 2026, 31) == []


def test_save_and_get_weekly_report_roundtrip():
    conn = init_db(":memory:")
    report, summary = _report(), _summary()

    save_weekly_report(conn, 2026, 31, report, summary, item_count=2)
    result = get_weekly_report(conn, 2026, 31)

    assert result is not None
    read_report, read_summary = result
    assert read_report.total_items == 2
    assert read_summary.headline == "Export timeouts dominate."


def test_get_weekly_report_returns_none_when_missing():
    conn = init_db(":memory:")
    assert get_weekly_report(conn, 2026, 31) is None


def test_save_weekly_report_upserts_on_repeat_save():
    conn = init_db(":memory:")
    save_weekly_report(conn, 2026, 31, _report(count=2), _summary(), item_count=2)
    save_weekly_report(conn, 2026, 31, _report(count=5), _summary(), item_count=5)

    result = get_weekly_report(conn, 2026, 31)
    assert result[0].total_items == 5


def test_list_available_weeks_groups_by_month_in_order():
    conn = init_db(":memory:")
    # Week 28 (Jul 6-12) and week 31 (Jul 27-Aug 2) both start in July; week 35 starts in Aug.
    save_weekly_report(conn, 2026, 28, _report(), _summary(), item_count=2)
    save_weekly_report(conn, 2026, 31, _report(), _summary(), item_count=3)
    save_weekly_report(conn, 2026, 35, _report(), _summary(), item_count=1)

    months = list_available_weeks(conn)

    assert len(months) == 2
    july = months[0]
    assert july["month_label"] == "Jul 2026"
    assert [w["iso_week"] for w in july["weeks"]] == [28, 31]
    assert [w["week_number_in_month"] for w in july["weeks"]] == [1, 2]

    august = months[1]
    assert august["month_label"] == "Aug 2026"
    assert [w["iso_week"] for w in august["weeks"]] == [35]


def test_list_available_weeks_empty_when_no_reports():
    conn = init_db(":memory:")
    assert list_available_weeks(conn) == []
