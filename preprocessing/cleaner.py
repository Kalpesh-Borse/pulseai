"""Input validation and cleanup — the first gate the pipeline runs every raw row through.

Nothing downstream should ever see blank text, absurdly long text, or malformed encoding.
Suspected prompt-injection attempts are NOT rejected here (a customer can legitimately
mention "ignore my previous ticket" in good faith) — they are flagged so the classifier's
prompt-injection defenses and the audit trail both have visibility into them.
"""
import re
import unicodedata

from schemas.models import CleanFeedbackItem, RawFeedbackItem, RejectedItem

_INJECTION_PATTERNS = [
    re.compile(r"ignore (all )?(previous|prior|above) instructions", re.IGNORECASE),
    re.compile(r"disregard (all )?(previous|prior|above)", re.IGNORECASE),
    re.compile(r"system prompt", re.IGNORECASE),
    re.compile(r"you are now", re.IGNORECASE),
    re.compile(r"act as (a|an) ", re.IGNORECASE),
    re.compile(r"output the (string|word|text)", re.IGNORECASE),
    re.compile(r"override", re.IGNORECASE),
]


def _looks_like_injection(text: str) -> bool:
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)


def _normalize_encoding(text: str) -> str:
    """Strip characters that can't round-trip through UTF-8 and normalize unicode form."""
    text = text.encode("utf-8", errors="ignore").decode("utf-8")
    return unicodedata.normalize("NFC", text)


def validate_and_clean(raw: RawFeedbackItem, max_length: int) -> CleanFeedbackItem | RejectedItem:
    text = _normalize_encoding(raw.text)
    stripped = text.strip()

    if not stripped:
        return RejectedItem(
            item_id=raw.item_id, reason="empty_after_cleaning", submitted_at=raw.submitted_at
        )

    flags: list[str] = []

    if len(stripped) > max_length:
        stripped = stripped[:max_length].rstrip()
        flags.append("truncated")

    if _looks_like_injection(stripped):
        flags.append("possible_prompt_injection")

    return CleanFeedbackItem(
        item_id=raw.item_id,
        text=stripped,
        source=raw.source,
        submitted_at=raw.submitted_at,
        flags=flags,
    )


def clean_batch(
    raw_items: list[RawFeedbackItem], max_length: int
) -> tuple[list[CleanFeedbackItem], list[RejectedItem]]:
    cleaned: list[CleanFeedbackItem] = []
    rejected: list[RejectedItem] = []

    for raw in raw_items:
        result = validate_and_clean(raw, max_length)
        if isinstance(result, RejectedItem):
            rejected.append(result)
        else:
            cleaned.append(result)

    return cleaned, rejected
