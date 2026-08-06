"""Cross-item aggregation — pure business logic, no AI call involved.

Takes the already-classified items plus their theme clusters and produces the counts,
distributions, and top themes that both the dashboard and the narrative summary are built on.
"""
from collections import Counter

from config.settings import Settings
from schemas.models import (
    AggregateReport,
    ClassifiedFeedback,
    CategoryCount,
    RejectedItem,
    SentimentDistribution,
    ThemeCluster,
    UrgencyBreakdown,
)


def _category_counts(items: list[ClassifiedFeedback]) -> list[CategoryCount]:
    counts = Counter(item.category for item in items)
    ordered = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)
    return [CategoryCount(category=category, count=count) for category, count in ordered]


def _sentiment_distribution(items: list[ClassifiedFeedback]) -> SentimentDistribution:
    if not items:
        return SentimentDistribution(positive=0, neutral=0, negative=0, average_score=0.0)

    counts = Counter(item.sentiment.label for item in items)
    average = sum(item.sentiment.score for item in items) / len(items)
    return SentimentDistribution(
        positive=counts.get("positive", 0),
        neutral=counts.get("neutral", 0),
        negative=counts.get("negative", 0),
        average_score=round(average, 3),
    )


def _urgency_breakdown(items: list[ClassifiedFeedback]) -> UrgencyBreakdown:
    counts = Counter(item.urgency for item in items)
    return UrgencyBreakdown(
        low=counts.get("low", 0),
        medium=counts.get("medium", 0),
        high=counts.get("high", 0),
        critical=counts.get("critical", 0),
    )


def aggregate(
    classified_items: list[ClassifiedFeedback],
    clusters: list[ThemeCluster],
    rejected_items: list[RejectedItem],
    settings: Settings,
) -> AggregateReport:
    return AggregateReport(
        total_items=len(classified_items) + len(rejected_items),
        rejected_items=len(rejected_items),
        category_counts=_category_counts(classified_items),
        sentiment_distribution=_sentiment_distribution(classified_items),
        urgency_breakdown=_urgency_breakdown(classified_items),
        top_themes=clusters[: settings.top_theme_count],
    )
