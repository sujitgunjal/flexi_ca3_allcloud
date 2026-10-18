from dataclasses import dataclass

from app.providers.config import (
    CHEAP_MODEL,
    LOCAL_RESPONSE_MODEL,
    NVIDIA_API_BASE,
    STRONG_MODEL,
)


@dataclass(frozen=True)
class ModelTier:
    tier: str
    provider: str
    model: str
    api_base: str


def list_tiers() -> list[ModelTier]:
    return [
        ModelTier(
            tier="local",
            provider="nvidia",
            model=LOCAL_RESPONSE_MODEL,
            api_base=NVIDIA_API_BASE,
        ),
        ModelTier(
            tier="cheap",
            provider="nvidia",
            model=CHEAP_MODEL,
            api_base=NVIDIA_API_BASE,
        ),
        ModelTier(
            tier="strong",
            provider="nvidia",
            model=STRONG_MODEL,
            api_base=NVIDIA_API_BASE,
        ),
    ]


def get_tier(tier: str) -> ModelTier:
    for item in list_tiers():
        if item.tier == tier:
            return item

    raise ValueError(f"Unknown model tier: {tier}")
