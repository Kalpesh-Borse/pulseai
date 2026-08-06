"""Narrative weekly summary generation — the second, distinct AI task in the pipeline.

Same discipline as the classifier: raw model output is parsed, schema-validated, retried once,
and replaced with a deterministic templated fallback (built directly from the aggregate
numbers, no AI involved) if the model still won't produce valid JSON. The pipeline always
ends with a usable summary, even with no API access at all.
"""
import json
import logging

from openai import OpenAI

from config.settings import Settings
from prompts.summary_prompt import build_summary_messages
from schemas.models import AggregateReport, WeeklySummary

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = {"headline", "key_findings", "recommended_actions", "narrative_text"}

_RETRY_REMINDER = (
    "\n\nReminder: respond with ONLY a single valid JSON object matching the required "
    "shape — no markdown fences, no extra text, no missing fields."
)


def _parse_and_validate(raw_content: str) -> dict:
    data = json.loads(raw_content)
    if not _REQUIRED_FIELDS.issubset(data.keys()):
        missing = _REQUIRED_FIELDS - data.keys()
        raise ValueError(f"missing required fields: {missing}")
    return data


def _template_fallback(report: AggregateReport) -> WeeklySummary:
    """A deterministic, non-AI summary so the pipeline never ends without one."""
    top_category = report.category_counts[0] if report.category_counts else None
    top_theme = report.top_themes[0] if report.top_themes else None

    findings = [f"{report.total_items} feedback items processed this week ({report.rejected_items} rejected as unusable)."]
    if top_category:
        findings.append(f"Most common category: {top_category.category.value} ({top_category.count} items).")
    if top_theme:
        findings.append(f"Top recurring theme: '{top_theme.label}' ({top_theme.count} items).")
    findings.append(
        f"Sentiment split — positive: {report.sentiment_distribution.positive}, "
        f"neutral: {report.sentiment_distribution.neutral}, "
        f"negative: {report.sentiment_distribution.negative}."
    )

    return WeeklySummary(
        headline="Automated summary unavailable — showing raw aggregate statistics instead.",
        key_findings=findings,
        recommended_actions=[
            "Review the top theme clusters and category breakdown directly in the dashboard."
        ],
        narrative_text=(
            "The AI narrative summary could not be generated this week, so this is a "
            "template-based fallback built directly from the aggregate statistics: "
            + " ".join(findings)
        ),
    )


def _call_model(client: OpenAI, settings: Settings, messages: list[dict[str, str]]) -> str:
    response = client.chat.completions.create(
        model=settings.summary_model,
        messages=messages,
        temperature=settings.model_temperature,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


def generate_summary(report: AggregateReport, client: OpenAI, settings: Settings) -> WeeklySummary:
    messages = build_summary_messages(report)

    try:
        raw_content = _call_model(client, settings, messages)
        data = _parse_and_validate(raw_content)
        return WeeklySummary(**data)
    except Exception as first_error:  # noqa: BLE001 — any failure triggers one retry
        logger.warning("summary generation attempt 1 failed: %s", first_error)

    try:
        retry_messages = messages + [{"role": "user", "content": _RETRY_REMINDER}]
        raw_content = _call_model(client, settings, retry_messages)
        data = _parse_and_validate(raw_content)
        return WeeklySummary(**data)
    except Exception as second_error:  # noqa: BLE001 — repeated failure falls back, never crashes
        logger.error("summary generation retry failed: %s", second_error)
        return _template_fallback(report)
