# Taxonomy Proposal — for mentor review

This is a working document, not a final spec. The categories below are my draft, built from
reasoning about what a memory-infrastructure product like Memsy would plausibly need — they
haven't been validated against how the actual team thinks about its own feedback. That
validation is the point of this conversation. Bring this doc, walk through it, and fill in the
**Decisions** section at the bottom as you go.

## Current taxonomy (`schemas/models.py`, `Category` enum)

| Category | Definition | Example |
|---|---|---|
| `bug_defect` | Something is broken or behaves incorrectly | "Deleted memories still show up in search for 10 minutes after deletion" |
| `performance` | Works, but too slow / times out / degrades under load | "Export keeps timing out on large datasets" |
| `billing` | Charges, invoices, pricing, refunds | "We were double-charged this month" |
| `feature_request` | A capability that doesn't exist yet | "Please add per-namespace TTL configuration" |
| `ux_usability` | Navigation/discoverability confusion, nothing technically broken | "Usage stats page is buried three menus deep since the redesign" |
| `documentation` | Docs/guides/examples missing, wrong, or outdated | "Quickstart docs reference an SDK method that no longer exists" |
| `integration_api` | Third-party integrations, webhooks, SDKs, API contracts/rate limits | "Webhook integration stopped firing after the last API version bump" |
| `account_access` | Login, authentication, permissions, lockouts | "Got locked out of our workspace after an SSO change" |
| `support_experience` | Feedback about the support interaction itself, not the product | "Support fixed my issue live on a call in under 10 minutes" |
| `other` | Doesn't fit any category above | General praise, gibberish, off-topic |

## Design rationale

- **10 categories, roughly disjoint by "what kind of thing is broken/wanted"** rather than by
  product surface area — chosen so a classifier has a clear rule for most cases (is something
  broken? is it slow but working? is it about money? is it a request for something new?).
- **`support_experience` is separate from the product categories** deliberately — feedback
  about how fast/well the support team responded is actionable by a different team (CX) than
  feedback about the product itself (engineering/product). Worth confirming this split is
  actually useful to the business, not just clean in theory.
- **`other` exists as a safety valve**, not a real answer — a good taxonomy should have as few
  items landing there as possible. In real testing, general praise ("love the CLI tools") and
  genuinely off-topic input (prompt injection with no real content, gibberish) landed here.

## Specific open questions — backed by real testing evidence

These aren't hypothetical — they came from actually running the classifier against real
examples (see `docs/accuracy_report.md`, `docs/decision_log.md`).

1. **`billing` vs `documentation` boundary is genuinely ambiguous.** A real test item — "the
   pricing page doesn't explain what counts as a memory unit" — is defensibly either: it's about
   pricing (`billing`) or about unclear docs (`documentation`). The classifier picked
   `documentation`; a human labeler might reasonably pick either. **Decide**: does this need an
   explicit tie-breaking rule, or is either answer fine for how the team will use this data?

2. **Should `billing` and `account_access` ever merge**, e.g. under a broader "account" bucket?
   Or are they used by different enough teams (finance vs. security/support) that keeping them
   separate is correct?

3. **Is `support_experience` actually useful as its own category**, or would that feedback be
   more useful folded into whatever product category the underlying ticket was about (with a
   separate sentiment-on-support-quality signal instead of a whole category)?

4. **Urgency calibration, not just category.** Real testing found the `critical` vs `high`
   boundary is the least stable part of the system — an item almost identical to our own
   `critical`-urgency few-shot example still came back `high` on a live run. Worth discussing
   whether the taxonomy needs a stricter, more example-heavy urgency rubric independent of the
   category question.

5. **Is 10 categories the right granularity at all?** Too coarse and the "top themes" chart
   duplicates what categories already tell you; too fine and rare categories become noise.
   Worth sanity-checking against however many *actual* Memsy tickets/reviews exist per category
   in a real week, once real data is available.

## Decisions

*(Fill in during/after the mentor conversation — then tell me what changed and I'll update
`schemas/models.py`, the few-shot examples in `prompts/classification_prompt.py`, and this doc
to match.)*

- Category list confirmed / changed:
- Billing vs documentation tie-break rule (if any):
- Support_experience: kept as-is / merged / redefined:
- Urgency rubric changes:
- Other notes:
