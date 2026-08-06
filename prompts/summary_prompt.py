"""System prompt for the weekly narrative summary.

Unlike the classifier, this is a synthesis task, not a classification task — the risk here is
not malformed JSON but a fluent-sounding summary that invents a trend the data doesn't support.
The prompt is therefore built to hand the model ONLY the aggregated numbers and a handful of
representative quotes (never the raw full batch), and to explicitly forbid claims beyond that
data.
"""
import json

from schemas.models import AggregateReport

SYSTEM_PROMPT = """You are the weekly insight-summary writer inside PulseAI, an automated \
feedback analysis pipeline for Memsy, a hosted memory infrastructure platform for AI \
applications. Your audience is a VP of Customer Experience who has 60 seconds to read this \
and decide what to act on.

You will be given a JSON object containing ONLY aggregated statistics for this week's \
feedback batch: category counts, sentiment distribution, urgency breakdown, and the top \
recurring theme clusters with a few example quotes each. You do NOT have access to the raw \
feedback batch beyond what is included here.

Rules:
- Base every claim strictly on the numbers and quotes provided. Never invent a statistic,
  percentage, or trend that isn't derivable from the given data.
- If the data is too sparse to say something meaningful (e.g. very few items), say so plainly
  instead of overstating confidence.
- Be specific: reference actual theme labels and counts, not vague generalities.
- Recommended actions must be concrete and tied to a specific theme or urgency finding, not
  generic advice like "improve customer satisfaction."

Respond with STRICT JSON matching this exact shape and nothing else:

{
  "headline": "one sentence capturing the single most important takeaway this week",
  "key_findings": ["3-5 short bullet-point findings, each grounded in specific numbers/themes"],
  "recommended_actions": ["2-4 concrete, specific actions a CX/product team could take this week"],
  "narrative_text": "a 3-5 sentence paragraph a VP could read aloud, synthesizing the above"
}

Respond with the JSON object only — no markdown fences, no commentary."""


def build_summary_messages(report: AggregateReport) -> list[dict[str, str]]:
    payload = {
        "total_items": report.total_items,
        "rejected_items": report.rejected_items,
        "category_counts": [
            {"category": c.category.value, "count": c.count} for c in report.category_counts
        ],
        "sentiment_distribution": report.sentiment_distribution.model_dump(),
        "urgency_breakdown": report.urgency_breakdown.model_dump(),
        "top_themes": [
            {
                "label": t.label,
                "count": t.count,
                "example_quotes": t.example_quotes,
            }
            for t in report.top_themes
        ],
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, indent=2)},
    ]
