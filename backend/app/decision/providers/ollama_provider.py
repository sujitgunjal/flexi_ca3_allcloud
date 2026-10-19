import json
import logging
import os
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request

from app.decision.base import DecisionProviderError
from app.decision.prompts.candidate import CANDIDATE_SYSTEM_PROMPT
from app.providers.config import OLLAMA_API_BASE, OLLAMA_MODEL


# Live classifier prompt. Selected on the validation split for llama3:8b.
SYSTEM_PROMPT = CANDIDATE_SYSTEM_PROMPT
HOSTED_OLLAMA_API_BASE = "https://ollama.com"
_LOCAL_OLLAMA_HOSTS = {"localhost", "127.0.0.1", "::1"}
logger = logging.getLogger(__name__)


def _hostname(api_base: str) -> str:
    return (urllib.parse.urlparse(api_base).hostname or "").lower()


class OllamaDecisionProvider:
    """Decision classifier. Local Ollama by default; hosted Ollama for cloud models."""

    name = "ollama"

    def __init__(self, model: str | None = None, api_base: str | None = None):
        self.model_name = model or os.getenv("DECISION_OLLAMA_MODEL", OLLAMA_MODEL)
        self.api_key = os.getenv("OLLAMA_API_KEY", "").strip()
        configured_base = (api_base if api_base is not None else OLLAMA_API_BASE).rstrip("/")
        host = _hostname(configured_base)
        # An explicit api_base keeps the caller's server and model id.
        # Cloud tags served by the local daemon use the "-cloud" suffix.
        # Ollama's hosted API serves the same model without that suffix.
        self._use_hosted_cloud = api_base is None and self.model_name.endswith("-cloud") and (
            host == "ollama.com" or (host in _LOCAL_OLLAMA_HOSTS and bool(self.api_key))
        )
        if self._use_hosted_cloud:
            self.api_base = HOSTED_OLLAMA_API_BASE
            self._request_model = self.model_name[: -len("-cloud")]
        else:
            self.api_base = configured_base
            self._request_model = self.model_name
        self.timeout_seconds = float(os.getenv("DECISION_TIMEOUT_SECONDS", "180"))
        self.last_call: dict = {}

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
            "model": self._request_model,
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
        headers = {"Content-Type": "application/json"}
        if self._use_hosted_cloud and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.api_base}/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            _log_decision_failure("decision_classify", exc, f"status={exc.code}")
            raise DecisionProviderError(
                f"Ollama decision model returned HTTP {exc.code}"
            ) from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            reason_name = type(reason).__name__ if reason is not None else "none"
            _log_decision_failure("decision_classify", exc, f"reason={reason_name}")
            target = "Ollama cloud" if self._use_hosted_cloud else "Local Ollama"
            if isinstance(reason, TimeoutError):
                raise DecisionProviderError(
                    f"{target} decision model timed out"
                ) from exc
            raise DecisionProviderError(
                f"{target} decision model is unavailable"
            ) from exc
        except TimeoutError as exc:
            _log_decision_failure("decision_classify", exc, "reason=TimeoutError")
            raise DecisionProviderError(
                "Local Ollama decision model timed out"
            ) from exc
        except json.JSONDecodeError as exc:
            _log_decision_failure("decision_classify", exc, "reason=invalid_json")
            raise DecisionProviderError(
                "Local Ollama decision model returned invalid JSON"
            ) from exc

        message = payload.get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        self.last_call = {
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "prompt_tokens": payload.get("prompt_eval_count"),
            "output_tokens": payload.get("eval_count"),
        }
        if not isinstance(content, str) or not content.strip():
            raise DecisionProviderError(
                "Local Ollama decision model returned an empty classification"
            )

        return content


def _log_decision_failure(stage: str, exc: Exception, detail: str) -> None:
    """Log the failure stage and traceback without the query or credentials."""

    logger.error(
        "Decision provider failed stage=%s category=%s %s\n%s",
        stage,
        type(exc).__name__,
        detail,
        "".join(traceback.format_tb(exc.__traceback__)),
    )
