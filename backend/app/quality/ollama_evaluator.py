import json
import logging
import os
import urllib.error
import urllib.request

from app.providers.config import OLLAMA_API_BASE
from app.quality.base import QualityEvaluatorError
from app.quality.prompt import QUALITY_SYSTEM_PROMPT

DEFAULT_QUALITY_OLLAMA_MODEL = "gemma4:31b-cloud"
QUALITY_TIMEOUT_SECONDS = float(os.getenv("QUALITY_TIMEOUT_SECONDS", "20"))
logger = logging.getLogger(__name__)


class OllamaQualityEvaluator:
    """Quality evaluator. Its model is set only by QUALITY_OLLAMA_MODEL."""

    name = "ollama"

    def __init__(self, model: str | None = None, api_base: str | None = None):
        self.model_name = model or os.getenv(
            "QUALITY_OLLAMA_MODEL",
            DEFAULT_QUALITY_OLLAMA_MODEL,
        )
        self.api_base = (api_base or OLLAMA_API_BASE).rstrip("/")

    def evaluate_raw(
        self,
        query: str,
        response: str,
        *,
        correction: str | None = None,
    ) -> str:
        user_content = (
            f"User query:\n{query.strip()}\n\n"
            f"Assistant response:\n{response.strip()}"
        )
        if correction:
            user_content = f"{correction}\n\n{user_content}"

        body = {
            "model": self.model_name,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": QUALITY_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "options": {
                "temperature": 0,
                "num_predict": 300,
            },
        }
        request = urllib.request.Request(
            f"{self.api_base}/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=QUALITY_TIMEOUT_SECONDS,
            ) as http_response:
                payload = json.loads(http_response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", None)
            category = (
                "timeout"
                if isinstance(reason, TimeoutError)
                else "connection_error"
            )
            logger.warning(
                "Ollama quality request failed category=%s",
                category,
            )
            raise QualityEvaluatorError(
                f"Local Ollama quality model is unavailable at {self.api_base}"
            ) from exc
        except TimeoutError as exc:
            logger.warning("Ollama quality request failed category=timeout")
            raise QualityEvaluatorError("Local Ollama quality model timed out") from exc
        except json.JSONDecodeError as exc:
            raise QualityEvaluatorError(
                "Local Ollama quality model returned invalid JSON"
            ) from exc

        message = payload.get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise QualityEvaluatorError(
                "Local Ollama quality model returned an empty evaluation"
            )
        return content
