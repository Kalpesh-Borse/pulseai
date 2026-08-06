from schemas.models import ClassifiedFeedback, Sentiment, SentimentLabel, UrgencyLevel, Category
from scripts.evaluate_accuracy import compute_summary, score_item
from scripts.test_consistency import compare_passes


def _classified(category=Category.BILLING, sentiment_label=SentimentLabel.NEGATIVE, score=-0.5,
                 urgency=UrgencyLevel.MEDIUM, themes=None) -> ClassifiedFeedback:
    return ClassifiedFeedback(
        item_id="X1",
        text="some feedback",
        category=category,
        sentiment=Sentiment(label=sentiment_label, score=score),
        urgency=urgency,
        themes=themes or ["duplicate charge"],
        reasoning="test",
    )


def test_score_item_all_fields_match():
    predicted = _classified()
    expected_row = {
        "item_id": "X1", "text": "some feedback",
        "expected_category": "billing", "expected_sentiment": "negative", "expected_urgency": "medium",
    }
    result = score_item(predicted, expected_row)
    assert result["category_match"] is True
    assert result["sentiment_match"] is True
    assert result["urgency_match"] is True


def test_score_item_detects_category_mismatch():
    predicted = _classified(category=Category.OTHER)
    expected_row = {
        "item_id": "X1", "text": "some feedback",
        "expected_category": "billing", "expected_sentiment": "negative", "expected_urgency": "medium",
    }
    result = score_item(predicted, expected_row)
    assert result["category_match"] is False
    assert result["sentiment_match"] is True


def test_compute_summary_accuracy_percentages():
    results = [
        {"category_match": True, "sentiment_match": True, "urgency_match": True},
        {"category_match": False, "sentiment_match": True, "urgency_match": True},
        {"category_match": True, "sentiment_match": False, "urgency_match": True},
        {"category_match": True, "sentiment_match": True, "urgency_match": False},
    ]
    summary = compute_summary(results)
    assert summary["n"] == 4
    assert summary["category_accuracy"] == 75.0
    assert summary["sentiment_accuracy"] == 75.0
    assert summary["urgency_accuracy"] == 75.0


def test_compute_summary_handles_empty_results():
    summary = compute_summary([])
    assert summary["n"] == 0
    assert summary["category_accuracy"] == 0.0


def test_compare_passes_identical_results_report_full_match():
    items = [("C01", "text one"), ("C02", "text two")]
    pass1 = {"C01": _classified(), "C02": _classified(category=Category.PERFORMANCE)}
    pass2 = {"C01": _classified(), "C02": _classified(category=Category.PERFORMANCE)}

    rows, summary = compare_passes(pass1, pass2, items)

    assert summary["identical_items"] == 2
    assert summary["matched_fields"] == summary["total_fields"]
    assert all(r["match"] for r in rows)


def test_compare_passes_detects_a_drifted_field():
    items = [("C01", "text one")]
    pass1 = {"C01": _classified(category=Category.BILLING)}
    pass2 = {"C01": _classified(category=Category.OTHER)}

    rows, summary = compare_passes(pass1, pass2, items)

    assert summary["identical_items"] == 0
    category_row = next(r for r in rows if r["field"] == "category")
    assert category_row["match"] is False
    assert category_row["pass1"] == "billing"
    assert category_row["pass2"] == "other"
