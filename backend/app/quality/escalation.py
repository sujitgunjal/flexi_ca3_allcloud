import os

TIER_ORDER = ("local", "cheap", "strong")


def max_quality_escalations() -> int:
    """How many times a failed quality check may request a stronger model."""

    raw = os.getenv("QUALITY_MAX_ESCALATIONS", "1")
    try:
        return max(0, int(raw))
    except ValueError:
        return 1


def next_stronger_tier(tier: str | None) -> str | None:
    if tier not in TIER_ORDER:
        return "cheap"
    index = TIER_ORDER.index(tier)
    if index + 1 >= len(TIER_ORDER):
        return None
    return TIER_ORDER[index + 1]
