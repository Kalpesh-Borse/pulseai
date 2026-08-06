# Engineering Design — PulseAI

## Problem

Product and CX teams at Memsy receive hundreds of pieces of customer feedback a week (support
tickets, app reviews, survey responses). Reading all of it manually to spot patterns is slow
and subjective. PulseAI automates the read: classify each item, score its sentiment and
urgency, find the recurring themes across the whole batch, and write a narrative summary a
VP of CX can act on immediately.

## Architecture

```
Batch of feedback (CSV)
        │
        ▼
Input validation & cleanup      preprocessing/cleaner.py
  - reject blank/whitespace-only rows
  - truncate oversized text (flagged, not dropped)
  - flag (not reject) suspected prompt-injection patterns
        │
        ▼
Per-item classification          core/classifier.py + prompts/classification_prompt.py
  - OpenAI call, JSON mode, temperature 0, 9 deliberate few-shot examples
  - category / sentiment / urgency / themes / reasoning
  - Pydantic schema validation → retry once → fallback record (never crashes)
        │
        ▼
Embedding + theme clustering      core/embeddings.py + core/clustering.py
  - each item's theme phrases embedded locally (sentence-transformers, no API key)
  - stored & queried through ChromaDB (cosine similarity) to group near-duplicate themes
    worded differently ("checkout is slow" vs "payment page lags")
        │
        ▼
Aggregation                       core/aggregator.py (pure logic, no AI call)
  - category counts, sentiment distribution, urgency breakdown, top theme clusters
        │
        ▼
Narrative summary                 core/summarizer.py + prompts/summary_prompt.py
  - OpenAI call grounded ONLY in the aggregate numbers + a few representative quotes
    (never the raw batch) — prevents the summary from inventing a trend
  - schema validation → retry once → deterministic template fallback (no AI, ever crashes)
        │
        ▼
Per-week persistence               core/week_utils.py + core/storage.py (SQLite, no AI call)
  - each item bucketed into an ISO calendar week from its date (missing/bad date → today's week)
  - items upserted into that week's stored set; clustering/aggregate/summary above are then
    re-run against the FULL accumulated set for that week and saved — so weeks build up across
    separate uploads instead of one upload overwriting another
        │
        ▼
Orchestration                     core/pipeline.py — the one function every interface calls
        │
        ├──► CLI    cli/run_pipeline.py   — batch process a CSV, write output/*.json + one
        │           weekly_summary_<year>-W<week>.md per week touched
        └──► API    api/main.py           — FastAPI: POST /api/process, GET /api/weeks,
                    │                        GET /api/results/*[?year=&week=]
                    ▼
             Dashboard   dashboard/*.html+js+css — vanilla JS + Chart.js, labeled charts,
             per-item table, and a month/week calendar picker for browsing stored history
```

## Module responsibilities

| Layer | Module | Responsibility |
|---|---|---|
| Schemas | `schemas/models.py` | Every data contract the rest of the app validates against — nothing crosses a module boundary unvalidated |
| Config | `config/settings.py` | All tunables (model names, temperature, thresholds) come from `.env`, nothing hardcoded |
| Preprocessing | `preprocessing/cleaner.py` | First gate every raw row passes through — guarantees non-empty, length-capped text downstream |
| Prompts | `prompts/*.py` | System prompts + few-shot examples, kept separate from the calling code so they can be reviewed/iterated independently |
| Core | `core/classifier.py`, `core/summarizer.py` | The only two places that call an LLM — both parse, validate, retry once, and fall back |
| Core | `core/embeddings.py`, `core/clustering.py` | Cross-item theme discovery via embedding similarity, independent of any LLM call |
| Core | `core/aggregator.py` | Pure business logic (counts/distributions) — no AI, fully deterministic |
| Core | `core/week_utils.py` | Pure date math (which ISO week a date falls in, its label) — no I/O, trivially unit-testable |
| Core | `core/storage.py` | The only module that touches SQLite — item/week persistence and the calendar's month/week listing |
| Core | `core/pipeline.py` | Orchestrates the above; the single reusable entrypoint every interface calls |
| Interfaces | `cli/`, `api/` | Thin adapters — no business logic lives here |

## Why two separate AI calls, not one

Classification and summarization are different tasks with different failure modes.
Classification is a per-item decision with a small, closed answer space (10 categories × 3
sentiment labels × 4 urgency levels) — the risk is malformed JSON or a wrong label.
Summarization is open-ended synthesis over already-aggregated numbers — the risk is a
fluent-sounding paragraph that overstates or invents a trend. Splitting them lets each prompt
be optimized (and independently graded) for its actual risk, and lets the summary call see
only the aggregate, never the raw batch, which is what keeps it grounded.

## Testing strategy

Every AI call (`core/classifier.py`, `core/summarizer.py`) is called through a dependency-
injected client, so tests mock it with `unittest.mock` and assert on the retry/fallback
behavior directly — no API key is needed to run the suite. `preprocessing/cleaner.py`,
`core/aggregator.py`, `core/clustering.py`, and `core/week_utils.py` are pure logic and tested
against fixed inputs (including a fixed fake embedder for clustering, so vector similarity
behavior is fully deterministic in tests). `core/storage.py` and any test touching the database
use `sqlite3.connect(":memory:")` — real SQL, zero disk I/O, no state shared between tests.
`api/main.py` exposes its DB connection as a FastAPI dependency (`get_conn`) specifically so
tests can override it with a shared in-memory connection via `app.dependency_overrides`.
`core/pipeline.py` and `api/main.py` have their own integration tests that wire mocked pieces
together and assert the whole request/response contract, including what happens when every AI
call fails.

## Configuration

All secrets and tunables live in `.env` (see `.env.example`); nothing sensitive is hardcoded.
`config/settings.py` is the single place that reads them and gives the rest of the app typed
defaults.
