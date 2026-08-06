import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from config.settings import Settings
from core.classifier import classify
from schemas.models import CleanFeedbackItem

VALID_RESPONSE = json.dumps(
    {
        "category": "performance",
        "sentiment": {"label": "negative", "score": -0.7},
        "urgency": "high",
        "themes": ["export timeout"],
        "reasoning": "Recurring export timeout described.",
    }
)


def _mock_client_with_responses(*contents: str) -> MagicMock:
    client = MagicMock()
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=c))]) for c in contents
    ]
    client.chat.completions.create.side_effect = responses
    return client


def _item() -> CleanFeedbackItem:
    return CleanFeedbackItem(item_id="X1", text="Export keeps timing out on large jobs.")


def test_classify_succeeds_on_first_valid_response():
    client = _mock_client_with_responses(VALID_RESPONSE)
    result = classify(_item(), client, Settings())

    assert result.is_fallback is False
    assert result.category == "performance"
    assert client.chat.completions.create.call_count == 1


def test_classify_retries_once_on_invalid_json_then_succeeds():
    client = _mock_client_with_responses("not valid json{{{", VALID_RESPONSE)
    result = classify(_item(), client, Settings())

    assert result.is_fallback is False
    assert result.category == "performance"
    assert client.chat.completions.create.call_count == 2


def test_classify_falls_back_after_two_failures_without_crashing():
    client = _mock_client_with_responses("still not json", "also not json")
    result = classify(_item(), client, Settings())

    assert result.is_fallback is True
    assert result.category == "other"
    assert client.chat.completions.create.call_count == 2


def test_classify_falls_back_when_required_field_missing():
    incomplete = json.dumps({"category": "performance", "urgency": "high"})
    client = _mock_client_with_responses(incomplete, incomplete)
    result = classify(_item(), client, Settings())

    assert result.is_fallback is True
