"""User-facing replies for the local tier, served by NVIDIA NIM."""

from openai import OpenAI

from app.providers.config import LOCAL_RESPONSE_MODEL, NVIDIA_API_BASE, NVIDIA_API_KEY


def generate_with_local_nim(
    prompt: str,
    history: list[dict] | None = None,
    timeout: float | None = None,
) -> dict:
    if not NVIDIA_API_KEY:
        raise RuntimeError("NVIDIA API key is not configured")

    messages = []
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    client = OpenAI(
        base_url=NVIDIA_API_BASE,
        api_key=NVIDIA_API_KEY,
        timeout=timeout,
        max_retries=0,
    )
    response = client.chat.completions.create(
        model=LOCAL_RESPONSE_MODEL,
        messages=messages,
        stream=False,
    )
    usage = response.usage
    choice = response.choices[0]
    return {
        "response": choice.message.content or "",
        "input_tokens": getattr(usage, "prompt_tokens", None),
        "output_tokens": getattr(usage, "completion_tokens", None),
    }
