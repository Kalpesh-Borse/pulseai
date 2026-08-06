from config.settings import Settings
from core.aggregator import aggregate
from schemas.models import (
    Category,
    ClassifiedFeedback,
    RejectedItem,
    Sentiment,
    SentimentLabel,
    ThemeCluster,
    UrgencyLevel,
)


def _item(item_id, category, label, score, urgency) -> ClassifiedFeedback:
    return ClassifiedFeedback(
        item_id=item_id,
        text="some feedback",
        category=category,
        sentiment=Sentiment(label=label, score=score),
        urgency=urgency,
        themes=["some theme"],
        reasoning="test",
    )


def test_category_counts_and_ordering():
    items = [
        _item("1", Category.PERFORMANCE, SentimentLabel.NEGATIVE, -0.5, UrgencyLevel.HIGH),
        _item("2", Category.PERFORMANCE, SentimentLabel.NEGATIVE, -0.6, UrgencyLevel.MEDIUM),
        _item("3", Category.BILLING, SentimentLabel.NEGATIVE, -0.3, UrgencyLevel.LOW),
    ]
    report = aggregate(items, clusters=[], rejected_items=[], settings=Settings())

    assert report.category_counts[0].category == Category.PERFORMANCE
    assert report.category_counts[0].count == 2
    assert report.category_counts[1].category == Category.BILLING
    assert report.category_counts[1].count == 1


def test_sentiment_distribution_counts_and_average():
    items = [
        _item("1", Category.OTHER, SentimentLabel.POSITIVE, 0.8, UrgencyLevel.LOW),
        _item("2", Category.OTHER, SentimentLabel.NEGATIVE, -0.4, UrgencyLevel.LOW),
        _item("3", Category.OTHER, SentimentLabel.NEUTRAL, 0.0, UrgencyLevel.LOW),
    ]
    report = aggregate(items, clusters=[], rejected_items=[], settings=Settings())

    dist = report.sentiment_distribution
    assert dist.positive == 1
    assert dist.neutral == 1
    assert dist.negative == 1
    assert dist.average_score == round((0.8 - 0.4 + 0.0) / 3, 3)


def test_urgency_breakdown():
    items = [
        _item("1", Category.OTHER, SentimentLabel.NEGATIVE, -0.5, UrgencyLevel.CRITICAL),
        _item("2", Category.OTHER, SentimentLabel.NEGATIVE, -0.5, UrgencyLevel.CRITICAL),
        _item("3", Category.OTHER, SentimentLabel.NEGATIVE, -0.5, UrgencyLevel.LOW),
    ]
    report = aggregate(items, clusters=[], rejected_items=[], settings=Settings())

    assert report.urgency_breakdown.critical == 2
    assert report.urgency_breakdown.low == 1
    assert report.urgency_breakdown.high == 0


def test_total_and_rejected_counts_include_rejected_items():
    items = [_item("1", Category.OTHER, SentimentLabel.NEUTRAL, 0.0, UrgencyLevel.LOW)]
    rejected = [RejectedItem(item_id="2", reason="empty_after_cleaning")]
    report = aggregate(items, clusters=[], rejected_items=rejected, settings=Settings())

    assert report.total_items == 2
    assert report.rejected_items == 1


def test_top_themes_capped_by_settings_top_theme_count():
    clusters = [
        ThemeCluster(cluster_id=f"c{i}", label=f"theme {i}", item_ids=[str(i)], count=10 - i)
        for i in range(5)
    ]
    settings = Settings()
    object.__setattr__(settings, "top_theme_count", 2)

    report = aggregate([], clusters=clusters, rejected_items=[], settings=settings)

    assert len(report.top_themes) == 2
    assert report.top_themes[0].label == "theme 0"


def test_empty_batch_produces_zeroed_report_without_crashing():
    report = aggregate([], clusters=[], rejected_items=[], settings=Settings())

    assert report.total_items == 0
    assert report.sentiment_distribution.average_score == 0.0
    assert report.category_counts == []
