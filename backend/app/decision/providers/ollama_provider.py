import json
import os
import urllib.error
import urllib.request

from app.decision.base import DecisionProviderError
from app.decision.prompts.candidate import CANDIDATE_SYSTEM_PROMPT
from app.providers.config import OLLAMA_API_BASE, OLLAMA_MODEL


# Live classifier prompt. Selected on the validation split for llama3:8b.
SYSTEM_PROMPT = CANDIDATE_SYSTEM_PROMPT


class OllamaDecisionProvider:
    """Permanent local decision provider. This is the default Jev-inspired engine."""

    name = "ollama"

    def __init__(self, model: str | None = None, api_base: str | None = None):
        self.model_name = model or os.getenv("DECISION_OLLAMA_MODEL", OLLAMA_MODEL)
        self.api_base = (api_base or OLLAMA_API_BASE).rstrip("/")

    def classify_raw(
        self,
        query: str,
        *,
        correction: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        user_content = f"Classify this query:\n{query.strip()}"
        if correction:
            user_content = f"{correction}\n\n{user_content}"

        body = {
            "model": self.model_name,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "options": {
                "temperature": 0,
                "num_predict": 400,
            },
        }
        request = urllib.request.Request(
            f"{self.api_base}/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise DecisionProviderError(
                f"Local Ollama decision model is unavailable at {self.api_base}"
            ) from exc
        except TimeoutError as exc:
            raise DecisionProviderError(
                "Local Ollama decision model timed out"
            ) from exc
        except json.JSONDecodeError as exc:
            raise DecisionProviderError(
                "Local Ollama decision model returned invalid JSON"
            ) from exc

        message = payload.get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise DecisionProviderError(
                "Local Ollama decision model returned an empty classification"
            )

        return content
