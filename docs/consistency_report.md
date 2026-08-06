# Consistency Report

Same 6 feedback items classified twice by the real classifier, 5 minutes apart, temperature=0. Direct test of the rubric check: "Run identical input twice, 5 minutes apart. Compare outputs."

**5/6 items were fully identical across both passes (every field matched). 29/30 individual fields matched overall.**

| ID | Field | Pass 1 | Pass 2 | Match? |
|---|---|---|---|---|
| C01 | category | `performance` | `performance` | yes |
| C01 | sentiment_label | `negative` | `negative` | yes |
| C01 | sentiment_score | `-0.7` | `-0.7` | yes |
| C01 | urgency | `high` | `high` | yes |
| C01 | themes | `['export timeout', 'large dataset export']` | `['export timeout', 'large dataset export']` | yes |
| C02 | category | `billing` | `billing` | yes |
| C02 | sentiment_label | `negative` | `negative` | yes |
| C02 | sentiment_score | `-0.6` | `-0.6` | yes |
| C02 | urgency | `medium` | `medium` | yes |
| C02 | themes | `['duplicate billing charge']` | `['duplicate billing charge']` | yes |
| C03 | category | `performance` | `performance` | yes |
| C03 | sentiment_label | `negative` | `negative` | yes |
| C03 | sentiment_score | `-0.6` | `-0.6` | yes |
| C03 | urgency | `medium` | `medium` | yes |
| C03 | themes | `['export timeout', 'recurring reliability complaint']` | `['export timeout', 'recurring reliability complaint']` | yes |
| C04 | category | `account_access` | `account_access` | yes |
| C04 | sentiment_label | `negative` | `negative` | yes |
| C04 | sentiment_score | `-0.7` | `-0.7` | yes |
| C04 | urgency | `high` | `high` | yes |
| C04 | themes | `['SSO lockout', 'prolonged access issue']` | `['SSO lockout', 'prolonged access issue']` | yes |
| C05 | category | `support_experience` | `support_experience` | yes |
| C05 | sentiment_label | `positive` | `positive` | yes |
| C05 | sentiment_score | `0.9` | `0.9` | yes |
| C05 | urgency | `low` | `low` | yes |
| C05 | themes | `['fast support response', 'live issue resolution']` | `['fast support response', 'live issue resolution']` | yes |
| C06 | category | `other` | `other` | yes |
| C06 | sentiment_label | `neutral` | `neutral` | yes |
| C06 | sentiment_score | `0.0` | `0.0` | yes |
| C06 | urgency | `low` | `low` | yes |
| C06 | themes | `['ignored instructions']` | `['instruction override']` | NO |

## Interpretation

Every enum-constrained field — category, sentiment label, sentiment score, and urgency — was
**100% stable** across all 6 items (24/24 matched). The only drift was on C06's free-text
`themes` field: `"ignored instructions"` became `"instruction override"` on the second pass —
two different phrasings of the same concept, not a different answer. C06 is also the pure
prompt-injection item with no real content (the same one documented in `docs/decision_log.md`
entry 9), so it's notable that even its drift was cosmetic wording, not a change in category,
sentiment, or urgency.

**Takeaway**: at temperature=0, the structured, closed-answer-space fields this system is
actually graded and acted on (category/sentiment/urgency — see `docs/mentor_qa.md` M5S2) are
consistent in practice, at least at this sample size. The one thing that isn't perfectly
stable is open-ended free-text generation (theme phrasing), which is expected — it's a
generative task, not a classification into a fixed set — and doesn't change any of the numbers
the dashboard's charts or aggregate report are built from, since theme *clustering* groups
synonymous phrasings together anyway (see `core/clustering.py`).
