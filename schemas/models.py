"""Strict, shared data contracts. The LLM's raw output is never trusted directly —
everything that leaves the classifier or summarizer must validate against one of these models.
"""
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Category(str, Enum):
    BUG_DEFECT = "bug_defect"
    PERFORMANCE = "performance"
    BILLING = "billing"
    FEATURE_REQUEST = "feature_request"
    UX_USABILITY = "ux_usability"
    DOCUMENTATION = "documentation"
    INTEGRATION_API = "integration_api"
    ACCOUNT_ACCESS = "account_access"
    SUPPORT_EXPERIENCE = "support_experience"
    OTHER = "other"


class SentimentLabel(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class UrgencyLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Sentiment(BaseModel):
    label: SentimentLabel
    score: float = Field(..., description="Continuous polarity from -1.0 (very negative) to 1.0 (very positive)")

    @field_validator("score")
    @classmethod
    def clamp_score(cls, v: float) -> float:
        return max(-1.0, min(1.0, v))


class RawFeedbackItem(BaseModel):
    """A single feedback row as it arrives from the input file, before cleaning."""

    item_id: str
    text: str
    source: str | None = None
    submitted_at: str | None = None


class CleanFeedbackItem(BaseModel):
    """Output of the preprocessing layer — guaranteed non-empty, length-capped text."""

    item_id: str
    text: str
    source: str | None = None
    submitted_at: str | None = None
    flags: list[str] = Field(default_factory=list)


class RejectedItem(BaseModel):
    """A raw item that could not be cleaned into something classifiable."""

    item_id: str
    reason: str
    submitted_at: str | None = None
    iso_year: int = 0
    iso_week: int = 0


class ClassifiedFeedback(BaseModel):
    item_id: str
    text: str
    category: Category
    sentiment: Sentiment
    urgency: UrgencyLevel
    themes: list[str] = Field(default_factory=list, max_length=3)
    reasoning: str
    is_fallback: bool = False
    iso_year: int = 0
    iso_week: int = 0


class ThemeCluster(BaseModel):
    cluster_id: str
    label: str
    item_ids: list[str]
    count: int
    example_quotes: list[str] = Field(default_factory=list, max_length=3)


class CategoryCount(BaseModel):
    category: Category
    count: int


class SentimentDistribution(BaseModel):
    positive: int
    neutral: int
    negative: int
    average_score: float


class UrgencyBreakdown(BaseModel):
    low: int
    medium: int
    high: int
    critical: int


class AggregateReport(BaseModel):
    total_items: int
    rejected_items: int
    category_counts: list[CategoryCount]
    sentiment_distribution: SentimentDistribution
    urgency_breakdown: UrgencyBreakdown
    top_themes: list[ThemeCluster]


class WeeklySummary(BaseModel):
    headline: str
    key_findings: list[str]
    recommended_actions: list[str]
    narrative_text: str


class WeekResult(BaseModel):
    """One ISO calendar week's recomputed-from-full-accumulated-data results."""

    iso_year: int
    iso_week: int
    week_label: str
    item_count: int
    aggregate_report: AggregateReport
    weekly_summary: WeeklySummary


class PipelineResult(BaseModel):
    classified_items: list[ClassifiedFeedback]
    rejected_items: list[RejectedItem]
    aggregate_report: AggregateReport
    weekly_summary: WeeklySummary
    weeks: list[WeekResult] = Field(default_factory=list)
