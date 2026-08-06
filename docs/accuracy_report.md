# Classification Accuracy Report

Evaluated against `data/samples/accuracy_eval_set.csv` — 20 hand-labeled feedback items, each with an unambiguous expected category/sentiment/urgency, run through the real classifier (`core/classifier.py`, real OpenAI API call per item, no mocking).

This set intentionally covers only clear-cut cases (2 per taxonomy category) so the accuracy number reflects baseline reliability. Known harder cases (sarcasm, prompt injection with no real content) are already documented separately in `docs/decision_log.md` and `docs/mentor_qa.md` rather than mixed into this metric.

## Summary

- **Category accuracy**: 95.0% (19/20)
- **Sentiment accuracy**: 100.0% (20/20)
- **Urgency accuracy**: 85.0% (17/20)

## Per-item results

| ID | Text | Category (expected -> predicted) | Sentiment (expected -> predicted) | Urgency (expected -> predicted) |
|---|---|---|---|---|
| A01 | Deleted memories still show up in search results for about 10 minutes ... | bug_defect -> bug_defect | negative -> negative | medium -> medium |
| A02 | The delete API returns a success response but the record is still retr... | bug_defect -> bug_defect | negative -> negative | medium -> medium |
| A03 | Export of our memory store keeps hanging at 90% and eventually times o... | performance -> performance | negative -> negative | high -> high |
| A04 | Search queries that used to return instantly now take several seconds ... | performance -> performance | negative -> negative | medium -> medium |
| A05 | We were double-charged this month, both the annual and monthly plan fe... | billing -> billing | negative -> negative | medium -> medium |
| A06 | The pricing page doesn't explain what counts as a memory unit, had to ... | billing -> documentation [MISS] | negative -> negative | low -> medium [MISS] |
| A07 | Would love a way to set custom TTLs per memory namespace instead of on... | feature_request -> feature_request | neutral -> neutral | low -> low |
| A08 | Please add a bulk-delete API so we don't have to loop single deletes f... | feature_request -> feature_request | neutral -> neutral | medium -> medium |
| A09 | Since the redesign, the usage stats page is buried three menus deep. P... | ux_usability -> ux_usability | negative -> negative | low -> low |
| A10 | Navigation got worse after the update, takes forever to find the API k... | ux_usability -> ux_usability | negative -> negative | medium -> medium |
| A11 | The quickstart docs reference an SDK method that no longer exists in t... | documentation -> documentation | negative -> negative | medium -> medium |
| A12 | Docs for the Python SDK are out of date, the retrieve() example throws... | documentation -> documentation | negative -> negative | medium -> medium |
| A13 | Our webhook integration stopped firing after the last API version bump... | integration_api -> integration_api | negative -> negative | high -> high |
| A14 | The REST API rate limit dropped without any changelog notice, now we g... | integration_api -> integration_api | negative -> negative | high -> high |
| A15 | Got locked out of our workspace after an SSO provider change, support ... | account_access -> account_access | negative -> negative | critical -> high [MISS] |
| A16 | Two of my teammates lost admin access after we rotated our SSO certifi... | account_access -> account_access | negative -> negative | high -> high |
| A17 | Support responded to my critical outage ticket in under 10 minutes and... | support_experience -> support_experience | positive -> positive | low -> low |
| A18 | Support closed my ticket as resolved without actually fixing the under... | support_experience -> support_experience | negative -> negative | medium -> high [MISS] |
| A19 | Really solid experience overall, the CLI tools especially make local d... | other -> other | positive -> positive | low -> low |
| A20 | Just a neutral note, usage has been stable this week, no complaints an... | other -> other | neutral -> neutral | low -> low |

## Misclassifications

- **A06**: "The pricing page doesn't explain what counts as a memory unit, had to email sales to understand our bill."
  - category: expected `billing`, got `documentation`
  - urgency: expected `low`, got `medium`
- **A15**: "Got locked out of our workspace after an SSO provider change, support couldn't restore access for 6 hours."
  - urgency: expected `critical`, got `high`
- **A18**: "Support closed my ticket as resolved without actually fixing the underlying issue, had to reopen it twice."
  - urgency: expected `medium`, got `high`

## Analysis

All 3 misses are on **urgency**, and only 1 is on category (with sentiment perfect at 20/20).
That's not noise — it's a real, useful signal: urgency judgment is the weakest link, not
category or sentiment.

The most interesting single case is **A15**. Its wording ("locked out of our workspace after
an SSO provider change, support couldn't restore access for 6 hours") is a near-verbatim
rephrasing of the `account_access` few-shot example in
`prompts/classification_prompt.py`, which explicitly teaches `urgency=critical` for this exact
scenario. Yet the real classifier returned `high`, not `critical`, on this run. That's evidence
of real output drift even against a case the model was directly shown an answer for — not just
a hypothetical concern from `docs/decision_log.md` entry 9, but the same class of instability
showing up on a completely different, non-adversarial input. Combined with A18 (a real ticket
that also got bumped up a level to `high`), the model appears to lean toward *overestimating*
urgency on tickets that mention repeated failures or extended downtime, even when the actual
business impact described is moderate. A06 illustrates a genuinely ambiguous case rather than
an error: "the pricing page doesn't explain X" is defensibly either a `billing` complaint (it's
about pricing) or a `documentation` complaint (it's about unclear docs) — a human labeler could
reasonably pick either.

**Takeaway for the taxonomy conversation with your mentor**: consider whether the urgency
rubric needs tighter, more example-heavy calibration (more few-shot coverage of "high vs
critical" boundaries specifically), and whether categories like billing/documentation need an
explicit tie-breaking rule for cases like A06.
