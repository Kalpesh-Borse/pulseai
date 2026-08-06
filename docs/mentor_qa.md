# Mentor Q&A Prep

Plain-English answers to the questions the evaluation rubric signals will be asked.

## "Explain prompt engineering / JSON schema / few-shot to me like I'm a Product Manager"

Instead of asking the AI a free-form question and hoping it answers usefully, we tell it
*exactly* what shape the answer must be — like a form with fixed fields (a category picked
from a fixed list, a sentiment score, up to three theme tags) — and we show it 9 worked
examples first so it learns the pattern by example rather than by instruction alone. That
combination (a fixed answer shape + example-based teaching) is what lets us trust the output
enough to feed it straight into charts and a report without a human checking every row.

## "Why ChromaDB and not a simple keyword search?"

Two customers rarely describe the same problem with the same words — one says "checkout is
slow," another says "payment page lags." A keyword search would see zero overlap and treat
those as two different issues. We convert each theme phrase into a vector (a list of numbers
capturing its meaning) and group phrases that are close together in that space, regardless of
wording. ChromaDB is the tool that stores those vectors and answers "what's near this one?"
quickly. We actually ran into a real bug because of this — see the "what did you figure out"
answer below — which is good evidence we understand it rather than just using it.

## "Why SQLite for the weekly history, and why ISO calendar weeks instead of just '4 weeks per month'?"

SQLite for the same reason as ChromaDB/local embeddings elsewhere in this project: this is a
single-user local tool, so a file-based embedded database gives real persistence across
restarts without running a second service or adding an ORM dependency — Postgres would be
unjustified operational weight here. ISO calendar weeks (Monday-Sunday, via Python's
`date.isocalendar()`) instead of naively splitting each month into four 7-day chunks: months
don't divide evenly into weeks, so "week 1/2/3/4 of a month" is ambiguous right at every month
boundary. ISO weeks are the standard, unambiguous definition — the dashboard still shows
friendly "Week 1, Week 2" labels, but the underlying key is always the exact date range.

## "Why few-shot vs zero-shot?"

Zero-shot means giving the model instructions only; few-shot means also showing it worked
examples. We use few-shot because several of our category boundaries are genuinely subtle —
a documentation complaint vs a bug complaint, a UX complaint vs a bug complaint, sarcasm that
reads as positive on the surface but is actually negative, and a ticket that tries to tell the
model what to output (prompt injection). Instructions alone leave room for the model to guess
wrong on these; a worked example of each removes the ambiguity. See `prompts/classification_
prompt.py` — every one of the 9 examples was picked to teach a distinct distinction, not just
to cover a category label.

## "Walk me through what happens after I submit a batch until the report appears"

1. Each row is validated — blank/whitespace rows are rejected, oversized text is truncated,
   suspected prompt-injection attempts are flagged (not rejected — a legitimate customer might
   say "ignore my last ticket").
2. Each remaining item goes to the classifier: one LLM call, temperature 0, asking for
   category/sentiment/urgency/themes as strict JSON. The response is parsed and checked
   against our schema; if it's invalid we retry once with a stricter reminder, and if it's
   still invalid we substitute a safe fallback record rather than crash.
3. Each item's theme phrases are embedded and clustered by similarity (see the ChromaDB
   answer above) so near-duplicate themes worded differently merge into one.
4. We compute counts and distributions across the whole batch — no AI involved here, just
   arithmetic.
5. Those aggregate numbers (never the raw feedback text) are handed to a second LLM call that
   writes the narrative summary, so it can't invent a trend that isn't actually in the data.
6. The CLI writes this to files; the API serves it as JSON; the dashboard fetches that JSON
   and draws the charts.

## "Where is your system most likely to give a wrong answer?"

Three places, honestly:
1. **Ambiguous category boundaries** — a ticket that's genuinely both a bug and a UX
   complaint will get whichever label the model leans toward; we've picked deliberate few-shot
   examples to reduce this but it won't be zero.
2. **Sentiment on sarcasm/mixed tone** — we specifically trained an example for this, but
   subtler cases than our example could still be missed.
3. **Determinism isn't perfect, but it's better than it sounds** — even at temperature 0, the
   OpenAI API is not guaranteed to return bit-for-bit identical output for identical input every
   time. We measured this directly rather than just asserting it: `docs/consistency_report.md`
   classified the same 6 items twice, 5 minutes apart, and found every enum-constrained field
   (category, sentiment, urgency — 24/24) was perfectly stable; the only drift was the exact
   wording of one free-text theme phrase on one item, which is expected for open-ended
   generation and doesn't affect any number the dashboard shows (theme clustering already
   merges synonymous phrasings). The schema validation and retry/fallback path exist so any
   drift that does happen can never produce a *crash*, only, at worst, a borderline item's exact
   label flipping.
4. **Injection input with no real content underneath can get misclassified via few-shot echo**
   — we found this for real, not hypothetically. See below.

## "What's your classification accuracy, and how do you know?"

We built a 20-item hand-labeled ground-truth set (2 per category, unambiguous expected
category/sentiment/urgency) and ran it through the real classifier —
`docs/accuracy_report.md`. Results: **95% category accuracy, 100% sentiment accuracy, 85%
urgency accuracy**. All 3 misses were urgency-related (or urgency + category for one
genuinely ambiguous item). The most interesting single miss: an item nearly identical in
wording to one of our own few-shot examples (which explicitly teaches `urgency=critical` for
SSO-lockout scenarios) still came back as `high` on this run — real evidence that urgency
calibration is the weakest link, not category or sentiment, and a concrete thing worth
tightening with more few-shot coverage of the high/critical boundary before this goes further.
We deliberately kept this ground-truth set to clear-cut cases only, so the number reflects
baseline reliability — harder cases (sarcasm, injection-with-no-content) are tracked separately
in `docs/decision_log.md` rather than folded into this metric.

## "Who would use this and what problem does it solve for them?"

A CX or product lead who currently has to read (or delegate reading) hundreds of tickets and
reviews a week to spot patterns like "exports keep timing out" or "onboarding docs are stale."
PulseAI turns that into a five-minute read: what categories dominate, how sentiment is
trending, what the top 5-8 recurring themes actually are (with real quotes), and 2-4 concrete
actions to take this week.

## "Why did you choose these specific few-shot examples?"

Each of the 9 examples in `prompts/classification_prompt.py` earns its place by teaching a
distinct failure mode, not just a distinct category:
- A recurring performance defect (clear-cut case, sets the baseline)
- A billing double-charge (distinguishes billing from bug_defect)
- A pure feature request with no frustration (teaches neutral tone ≠ negative)
- A UX complaint where nothing is technically broken (bug_defect vs ux_usability)
- A documentation complaint where the underlying feature works fine (documentation vs bug)
- A critical account lockout (teaches the urgency ceiling)
- Positive praise about support specifically (teaches that support_experience exists and that
  not everything is negative)
- Sarcasm ("Oh great, ANOTHER timeout") — surface-positive wording, actually negative intent
- An explicit prompt-injection attempt embedded in real critical content — teaches the model
  to classify the substance, not obey embedded instructions

## "What was hardest / what surprised you?"

Two things, both found by actually running the pipeline live rather than trusting unit tests
alone:

1. **Theme clustering at scale.** See `docs/decision_log.md` entry 7 — capping the ChromaDB
   nearest-neighbor query at a fixed top-10 seemed reasonable but silently fragmented a single
   68-item cluster into a bigger one and a chunk of smaller ones, because tie-broken
   approximate search doesn't guarantee finding an already-clustered neighbor once a true
   cluster exceeds that cap. Catching it required running the pipeline end-to-end against a
   deliberately invalid API key (to force every item through the fallback path with identical
   fallback themes) — the small-scale unit tests never had enough identical items to expose it.
2. **A pure prompt-injection item got misclassified via few-shot echo.** See
   `docs/decision_log.md` entry 9 — item F033 has zero real complaint content (just an
   injection attempt), and instead of recognizing that, the model echoed the reasoning from our
   injection few-shot example almost verbatim and invented a "production database outage" that
   isn't in the text at all. The injection *attempt itself* was correctly refused (it didn't
   comply and output "APPROVED"); what failed was noticing there was no substance left once the
   injection was stripped away. Only found by running the real classifier against real
   deliberately-adversarial input — the fallback-path tests couldn't have caught this since
   they never call the real model at all.

## "What would you do differently if you started today?"

Two things:
1. Design the clustering test suite to include a group larger than any hardcoded top-K cutoff
   from the start, rather than discovering the cap via a live run. More generally: for any
   ANN/approximate-search component, write at least one test that deliberately exceeds whatever
   internal limit exists, since approximate algorithms tend to degrade exactly at scale
   boundaries rather than uniformly.
2. Add a *contrastive* pair to the injection few-shot example — one injection attempt wrapped
   around real critical content (which we have) and one injection attempt with nothing else in
   it (which we don't), so the model has to distinguish "ignore the instruction, classify the
   real content" from "ignore the instruction, and notice there's no real content left." Right
   now it only has the first case to learn from, and over-generalized to a case that looks
   similar but isn't.

## "What are you least confident about?"

The clustering distance threshold (`THEME_CLUSTER_DISTANCE_THRESHOLD`, default 0.35) was
chosen by reasoning about cosine-distance geometry and validated only against a small,
hand-built set of themes — it hasn't been tuned against a large volume of real production
feedback, so on a live dataset it may need adjustment (too tight and near-duplicate themes
won't merge; too loose and unrelated themes will).
