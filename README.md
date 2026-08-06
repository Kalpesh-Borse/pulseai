# PulseAI — Port 05: The Final Tempest

AI-powered feedback insight engine for Memsy, a hosted memory infrastructure platform for AI
applications. Ingests a batch of customer feedback (support tickets, app reviews, survey
responses) and produces:

- Per-item classification: category, sentiment, urgency, and specific theme tags
- Cross-item recurring themes via embedding-based clustering (ChromaDB)
- A narrative weekly insight summary grounded in the aggregate data
- A dashboard visualizing all of the above with labeled, self-explanatory charts
- Persistent, calendar-browsable history: feedback is bucketed into ISO calendar weeks by its
  date and stored in SQLite, so past weeks stay reachable (and keep accumulating as more data
  for them arrives) long after the upload that created them

This is the successor to Port 04's Smart Ticket Router — see `docs/decision_log.md` and
`docs/engineering_design.md` for how the architecture evolved and why.

## Setup

Requires Python 3.11+.

```bash
cd pulseai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `OPENAI_API_KEY` to a real key. Everything else has a sensible default.

## Running the tests

The full test suite runs with **no API key required** — every OpenAI call is mocked.

```bash
pytest
```

## Running the pipeline — CLI

Process a CSV batch (see `data/samples/week1_feedback.csv` for the expected format:
`item_id,text` required, `source` and `submitted_at` optional):

```bash
python -m cli.run_pipeline data/samples/week1_feedback.csv
```

Writes `output/classified_items.json` and `output/aggregate_report.json` (the whole upload,
regardless of date), `output/weekly_summary.md` (same scope), plus one
`output/weekly_summary_<year>-W<week>.md` per ISO week the batch's dates actually touched.

`data/samples/` has a few purpose-built datasets: `week1_feedback.csv` (39 rows, deliberate
edge cases — blank/whitespace, prompt injection, non-English, sarcasm, an extremely long rant),
`sample_10.csv` (a clean 10-row set spanning most categories), `multi_week_feedback.csv` (24
rows across 3 different ISO weeks/2 months, for exercising the calendar picker), and
`accuracy_eval_set.csv` (20 hand-labeled items with ground-truth answers, used by
`scripts/evaluate_accuracy.py`).

## Running the pipeline — API + dashboard

```bash
uvicorn api.main:app --reload
```

Open `http://127.0.0.1:8000/` — it redirects to the dashboard. Upload a CSV and click
"Process Batch" to see the charts and narrative summary populate. The same result is also
available as JSON at `/api/results/{categories,sentiment,urgency,themes,summary,items}`.

Every upload is also bucketed by date into ISO calendar weeks and persisted to a local SQLite
database (`DATABASE_PATH` in `.env`, defaults to `./pulseai.db`). Use the "Browse by week"
picker at the top of the dashboard (or `GET /api/weeks`, and `?year=&week=` on any
`/api/results/*` endpoint) to revisit any past week — including weeks from earlier uploads,
even after a restart. Re-uploading data for a week that already has stored items adds to it
rather than replacing it, and that week's themes/aggregate/summary are recomputed from the full
accumulated set every time.

## Evaluating accuracy and consistency

Two manual evaluation utilities (real API calls, not mocked, not part of `pytest`):

```bash
python -m scripts.evaluate_accuracy      # 20 hand-labeled items -> docs/accuracy_report.md
python -m scripts.test_consistency       # same items classified twice, 5 min apart -> docs/consistency_report.md (takes ~6 minutes)
```

Latest real results: **95% category / 100% sentiment / 85% urgency accuracy**, and **100% of
enum-constrained fields (category/sentiment/urgency) stable** across a 5-minute-apart rerun —
see the generated reports for the full breakdown and analysis of every miss.

## Project structure

```
pulseai/
├── config/        # .env-driven settings, nothing hardcoded
├── schemas/        # pydantic data contracts every module validates against
├── prompts/        # system prompts + few-shot examples, kept separate from calling code
├── preprocessing/  # input validation/cleanup — the first gate every raw row passes through
├── core/           # reusable business logic: classifier, embeddings, clustering,
│                   # aggregator, summarizer, week bucketing, SQLite storage, and the
│                   # pipeline that orchestrates all of them
├── api/            # FastAPI — thin adapter, no business logic
├── cli/            # CLI entrypoint — thin adapter, no business logic
├── dashboard/      # static HTML/JS/Chart.js frontend (charts, per-item table, week picker)
├── data/samples/   # synthetic Memsy feedback dataset used for testing/demo
├── scripts/        # manual evaluation utilities (accuracy, consistency) — real API calls,
│                   # not part of the automated test suite
├── tests/          # full suite, all AI calls mocked, all storage tests use an in-memory DB
└── docs/           # engineering design, decision log, mentor Q&A prep, accuracy/consistency reports
```

## Documentation

- [`docs/engineering_design.md`](docs/engineering_design.md) — architecture and module
  responsibilities
- [`docs/decision_log.md`](docs/decision_log.md) — key decisions and trade-offs, including a
  real clustering bug found and fixed during development
- [`docs/mentor_qa.md`](docs/mentor_qa.md) — prepared answers to anticipated demo questions
- [`docs/accuracy_report.md`](docs/accuracy_report.md) — real classification accuracy against a
  hand-labeled ground-truth set
- [`docs/consistency_report.md`](docs/consistency_report.md) — real same-input-twice consistency
  test, 5 minutes apart
