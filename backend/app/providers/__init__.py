
from app.providers.litellm_client import generate_with_cloud
from app.providers.local_nim import generate_with_local_nim
from app.providers.config import OLLAMA_TIMEOUT_SECONDS, PROVIDER_TIMEOUT_SECONDS
from app.providers.registry import get_tier


def generate_response(
    model: str,
    prompt: str,
    history: list[dict] | None = None,
    timeout: float | None = None,
) -> dict:
    """Generate a reply and return available token usage metadata."""

    tier = get_tier(model)
    # A caller may choose a shorter/longer finite deadline (for example a
    # provider probe); normal chat generation uses the configured default.
    if tier.tier == "local":
        return generate_with_local_nim(
            prompt,
            history,
            timeout=(OLLAMA_TIMEOUT_SECONDS if timeout is None else timeout),
        )

    return generate_with_cloud(
        model,
        prompt,
        history,
        timeout=(PROVIDER_TIMEOUT_SECONDS if timeout is None else timeout),
    )
