"""Per-item classification: the boundary between the LLM and everything else.

Raw model output is never trusted. It is always parsed, schema-validated, retried once on
failure, and finally replaced with a safe fallback record rather than allowed to crash the
pipeline or propagate malformed data downstream.
"""
import json
import logging

from openai import OpenAI

from config.settings import Settings
from prompts.classification_prompt import build_messages
from schemas.models import CleanFeedbackItem, ClassifiedFeedback, Sentiment, SentimentLabel, UrgencyLevel, Category

logger = logging.getLogger(__name__)

_RETRY_REMINDER = (
    "\n\nReminder: respond with ONLY a single valid JSON object matching the required "
    "shape — no markdown fences, no extra text, no missing fields."
)

_REQUIRED_FIELDS = {"category", "sentiment", "urgency", "themes", "reasoning"}


def _parse_and_validate(raw_content: str) -> dict:
    data = json.loads(raw_content)
    if not _REQUIRED_FIELDS.issubset(data.keys()):
        missing = _REQUIRED_FIELDS - data.keys()
        raise ValueError(f"missing required fields: {missing}")
    return data


def _fallback_record(item: CleanFeedbackItem) -> ClassifiedFeedback:
    return ClassifiedFeedback(
        item_id=item.item_id,
        text=item.text,
        category=Category.OTHER,
        sentiment=Sentiment(label=SentimentLabel.NEUTRAL, score=0.0),
        urgency=UrgencyLevel.MEDIUM,
        themes=[],
        reasoning="fallback: model output failed validation after retry",
        is_fallback=True,
    )


def _call_model(client: OpenAI, settings: Settings, messages: list[dict[str, str]]) -> str:
    response = client.chat.completions.create(
        model=settings.classifier_model,
        messages=messages,
        temperature=settings.model_temperature,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


def classify(item: CleanFeedbackItem, client: OpenAI, settings: Settings) -> ClassifiedFeedback:
    messages = build_messages(item.text)

    try:
        raw_content = _call_model(client, settings, messages)
        data = _parse_and_validate(raw_content)
        return ClassifiedFeedback(item_id=item.item_id, text=item.text, is_fallback=False, **data)
    except Exception as first_error:  # noqa: BLE001 — any failure here triggers one retry
        logger.warning("classification attempt 1 failed for %s: %s", item.item_id, first_error)

    try:
        retry_messages = messages + [{"role": "user", "content": _RETRY_REMINDER}]
        raw_content = _call_model(client, settings, retry_messages)
        data = _parse_and_validate(raw_content)
        return ClassifiedFeedback(item_id=item.item_id, text=item.text, is_fallback=False, **data)
    except Exception as second_error:  # noqa: BLE001 — repeated failure falls back, never crashes
        logger.error("classification retry failed for %s: %s", item.item_id, second_error)
        return _fallback_record(item)


def classify_batch(
    items: list[CleanFeedbackItem], client: OpenAI, settings: Settings
) -> list[ClassifiedFeedback]:
    return [classify(item, client, settings) for item in items]
