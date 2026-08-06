"""Runs a hand-labeled ground-truth set through the REAL classifier and measures accuracy.

This is a manual evaluation utility, not part of the automated pytest suite — it requires a
real OPENAI_API_KEY and makes real (billed) API calls, so it is run deliberately, not on every
test run. Directly answers mission step 4 ("test with real feedback samples and document
accuracy") and de-risks the mentor's own blind-input accuracy check (M5S1).

Usage:
    python -m scripts.evaluate_accuracy [path/to/labeled.csv]
"""
import csv
import sys
from pathlib import Path

from openai import OpenAI

from config.settings import get_settings
from core.classifier import classify
from schemas.models import ClassifiedFeedback, CleanFeedbackItem

DEFAULT_DATASET = Path("data/samples/accuracy_eval_set.csv")
REPORT_PATH = Path("docs/accuracy_report.md")


def load_labeled_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def score_item(predicted: ClassifiedFeedback, expected_row: dict) -> dict:
    """Pure comparison logic — no I/O, no API calls — so it's directly unit-testable."""
    category_match = predicted.category.value == expected_row["expected_category"]
    sentiment_match = predicted.sentiment.label.value == expected_row["expected_sentiment"]
    urgency_match = predicted.urgency.value == expected_row["expected_urgency"]

    return {
        "item_id": expected_row["item_id"],
        "text": expected_row["text"],
        "expected_category": expected_row["expected_category"],
        "predicted_category": predicted.category.value,
        "category_match": category_match,
        "expected_sentiment": expected_row["expected_sentiment"],
        "predicted_sentiment": predicted.sentiment.label.value,
        "sentiment_match": sentiment_match,
        "expected_urgency": expected_row["expected_urgency"],
        "predicted_urgency": predicted.urgency.value,
        "urgency_match": urgency_match,
        "is_fallback": predicted.is_fallback,
    }


def compute_summary(results: list[dict]) -> dict:
    """Pure aggregation — no I/O — so it's directly unit-testable."""
    n = len(results)
    if n == 0:
        return {"n": 0, "category_accuracy": 0.0, "sentiment_accuracy": 0.0, "urgency_accuracy": 0.0}

    category_correct = sum(r["category_match"] for r in results)
    sentiment_correct = sum(r["sentiment_match"] for r in results)
    urgency_correct = sum(r["urgency_match"] for r in results)

    return {
        "n": n,
        "category_correct": category_correct,
        "sentiment_correct": sentiment_correct,
        "urgency_correct": urgency_correct,
        "category_accuracy": category_correct / n * 100,
        "sentiment_accuracy": sentiment_correct / n * 100,
        "urgency_accuracy": urgency_correct / n * 100,
    }


def render_report_markdown(results: list[dict], summary: dict, dataset_path: Path) -> str:
    """Pure string-building — no I/O — so it's directly unit-testable."""
    lines = [
        "# Classification Accuracy Report",
        "",
        f"Evaluated against `{dataset_path}` — {summary['n']} hand-labeled feedback items, each "
        "with an unambiguous expected category/sentiment/urgency, run through the real "
        "classifier (`core/classifier.py`, real OpenAI API call per item, no mocking).",
        "",
        "This set intentionally covers only clear-cut cases (2 per taxonomy category) so the "
        "accuracy number reflects baseline reliability. Known harder cases (sarcasm, prompt "
        "injection with no real content) are already documented separately in "
        "`docs/decision_log.md` and `docs/mentor_qa.md` rather than mixed into this metric.",
        "",
        "## Summary",
        "",
        f"- **Category accuracy**: {summary['category_accuracy']:.1f}% "
        f"({summary['category_correct']}/{summary['n']})",
        f"- **Sentiment accuracy**: {summary['sentiment_accuracy']:.1f}% "
        f"({summary['sentiment_correct']}/{summary['n']})",
        f"- **Urgency accuracy**: {summary['urgency_accuracy']:.1f}% "
        f"({summary['urgency_correct']}/{summary['n']})",
        "",
        "## Per-item results",
        "",
        "| ID | Text | Category (expected -> predicted) | Sentiment (expected -> predicted) | Urgency (expected -> predicted) |",
        "|---|---|---|---|---|",
    ]

    for r in results:
        cat = f"{r['expected_category']} -> {r['predicted_category']}" + ("" if r["category_match"] else " [MISS]")
        sent = f"{r['expected_sentiment']} -> {r['predicted_sentiment']}" + ("" if r["sentiment_match"] else " [MISS]")
        urg = f"{r['expected_urgency']} -> {r['predicted_urgency']}" + ("" if r["urgency_match"] else " [MISS]")
        text_preview = r["text"][:70] + ("..." if len(r["text"]) > 70 else "")
        lines.append(f"| {r['item_id']} | {text_preview} | {cat} | {sent} | {urg} |")

    misses = [r for r in results if not (r["category_match"] and r["sentiment_match"] and r["urgency_match"])]
    lines.append("")
    lines.append("## Misclassifications")
    lines.append("")
    if not misses:
        lines.append("None — every item matched its expected label on every field.")
    else:
        for r in misses:
            lines.append(f"- **{r['item_id']}**: \"{r['text']}\"")
            if not r["category_match"]:
                lines.append(f"  - category: expected `{r['expected_category']}`, got `{r['predicted_category']}`")
            if not r["sentiment_match"]:
                lines.append(f"  - sentiment: expected `{r['expected_sentiment']}`, got `{r['predicted_sentiment']}`")
            if not r["urgency_match"]:
                lines.append(f"  - urgency: expected `{r['expected_urgency']}`, got `{r['predicted_urgency']}`")

    return "\n".join(lines) + "\n"


def main() -> int:
    dataset_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATASET
    rows = load_labeled_rows(dataset_path)

    settings = get_settings()
    if not settings.openai_api_key:
        print("Error: OPENAI_API_KEY not set — this evaluation requires real classification.", file=sys.stderr)
        return 1

    client = OpenAI(api_key=settings.openai_api_key)

    results = []
    for row in rows:
        item = CleanFeedbackItem(
            item_id=row["item_id"], text=row["text"], submitted_at=row.get("submitted_at") or None
        )
        predicted = classify(item, client, settings)
        result = score_item(predicted, row)
        results.append(result)
        status = "OK" if (result["category_match"] and result["sentiment_match"] and result["urgency_match"]) else "MISS"
        print(f"{row['item_id']}: {status} (category={result['predicted_category']}, "
              f"sentiment={result['predicted_sentiment']}, urgency={result['predicted_urgency']})")

    summary = compute_summary(results)
    print(f"\nCategory accuracy: {summary['category_accuracy']:.1f}%")
    print(f"Sentiment accuracy: {summary['sentiment_accuracy']:.1f}%")
    print(f"Urgency accuracy: {summary['urgency_accuracy']:.1f}%")

    REPORT_PATH.write_text(render_report_markdown(results, summary, dataset_path))
    print(f"\nFull report written to {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
