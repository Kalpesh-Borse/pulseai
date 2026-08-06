"""CLI entrypoint: process one CSV batch of feedback end-to-end.

Usage:
    python -m cli.run_pipeline data/samples/week1_feedback.csv
"""
import argparse
import csv
import json
import sys
from pathlib import Path

from config.settings import get_settings
from core.pipeline import run_pipeline
from schemas.models import RawFeedbackItem

REQUIRED_COLUMNS = {"item_id", "text"}


def _load_raw_items(csv_path: Path) -> list[RawFeedbackItem]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
            raise ValueError(
                f"CSV must contain at least these columns: {REQUIRED_COLUMNS}, "
                f"found: {reader.fieldnames}"
            )
        return [
            RawFeedbackItem(
                item_id=row["item_id"],
                text=row.get("text", "") or "",
                source=row.get("source") or None,
                submitted_at=row.get("submitted_at") or None,
            )
            for row in reader
        ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the PulseAI feedback pipeline on a CSV batch.")
    parser.add_argument("csv_path", type=Path, help="Path to a feedback CSV file")
    parser.add_argument("--output-dir", type=Path, default=Path("output"), help="Where to write results")
    args = parser.parse_args()

    if not args.csv_path.exists():
        print(f"Error: file not found: {args.csv_path}", file=sys.stderr)
        return 1

    try:
        raw_items = _load_raw_items(args.csv_path)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not raw_items:
        print("Error: input CSV has no data rows.", file=sys.stderr)
        return 1

    settings = get_settings()
    if not settings.openai_api_key:
        print(
            "Warning: OPENAI_API_KEY is not set. Classification and summary generation "
            "will fail and fall back to safe defaults for every item.",
            file=sys.stderr,
        )

    result = run_pipeline(raw_items, settings=settings)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "classified_items.json").write_text(
        json.dumps([item.model_dump() for item in result.classified_items], indent=2)
    )
    (args.output_dir / "aggregate_report.json").write_text(
        result.aggregate_report.model_dump_json(indent=2)
    )
    (args.output_dir / "weekly_summary.md").write_text(
        _render_summary_markdown("Weekly Feedback Insight Summary (this upload)", result.weekly_summary)
    )

    for week in result.weeks:
        filename = f"weekly_summary_{week.iso_year}-W{week.iso_week:02d}.md"
        title = f"Weekly Feedback Insight Summary — {week.week_label}"
        (args.output_dir / filename).write_text(_render_summary_markdown(title, week.weekly_summary))

    print(f"Processed {len(raw_items)} items ({len(result.rejected_items)} rejected).")
    print(f"Results written to {args.output_dir}/")

    if result.weeks:
        print("\nPer-week breakdown:")
        for week in result.weeks:
            print(f"  {week.week_label} (ISO {week.iso_year}-W{week.iso_week:02d}): {week.item_count} item(s) accumulated")

    print(f"\n{result.weekly_summary.headline}")
    return 0


def _render_summary_markdown(title: str, summary) -> str:
    lines = [f"# {title}\n", f"## {summary.headline}\n", "### Key Findings"]
    lines += [f"- {f}" for f in summary.key_findings]
    lines.append("\n### Recommended Actions")
    lines += [f"- {a}" for a in summary.recommended_actions]
    lines.append(f"\n### Narrative\n{summary.narrative_text}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
