import hashlib
import json
import logging
import os
import re
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

from app.providers.config import (
    EMBEDDING_MODEL,
    EMBEDDING_PROVIDER,
    EMBEDDING_TIMEOUT_SECONDS,
    OLLAMA_API_BASE,
    VOYAGE_API_BASE,
    VOYAGE_API_KEY,
    VOYAGE_EMBEDDING_MODEL,
)

# voyage-4-lite defaults to 1024 dimensions and accepts 32,000 tokens.
# nomic-embed-text is 768 dimensions. Those vectors must not be compared.
VOYAGE_BATCH_LIMIT = 1000


def embedding_identity() -> str:
    """Provider and model tag used to keep embedding spaces separate."""

    provider = os.getenv("EMBEDDING_PROVIDER", EMBEDDING_PROVIDER).strip().lower() or "voyage"
    if provider == "ollama":
        model = os.getenv("EMBEDDING_MODEL", EMBEDDING_MODEL)
    else:
        model = os.getenv("VOYAGE_EMBEDDING_MODEL", VOYAGE_EMBEDDING_MODEL)
    safe_model = re.sub(r"[^A-Za-z0-9._-]+", "-", model)
    return f"{provider}:{safe_model}"


class VoyageEmbedder:
    """Embed text with Voyage AI's hosted embeddings API."""

    provider = "voyage"

    def __init__(
        self,
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ):
        self.model = model or os.getenv("VOYAGE_EMBEDDING_MODEL", VOYAGE_EMBEDDING_MODEL)
        self.api_base = (api_base or os.getenv("VOYAGE_API_BASE", VOYAGE_API_BASE)).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("VOYAGE_API_KEY", VOYAGE_API_KEY)
        self.timeout = EMBEDDING_TIMEOUT_SECONDS if timeout is None else timeout

    def embed(self, texts: list[str], input_type: str | None = None) -> list[list[float]]:
        if not texts:
            return []
        if not self.api_key:
            raise RuntimeError("VOYAGE_API_KEY is not configured")
        # Query-to-query cache comparisons and query-to-document context ranking
        # both use Voyage's retrieval prompt. Callers pass document for history.
        selected_type = input_type or "query"
        # Voyage rejects "" with HTTP 400: input cannot contain empty strings.
        pending = [(index, text) for index, text in enumerate(texts) if text != ""]
        if not pending:
            return HashEmbedder().embed(texts)
        vectors: list[list[float] | None] = [None] * len(texts)
        width: int | None = None
        for start in range(0, len(pending), VOYAGE_BATCH_LIMIT):
            batch = pending[start:start + VOYAGE_BATCH_LIMIT]
            embedded = self._embed_batch([text for _index, text in batch], selected_type)
            if width is None:
                width = len(embedded[0])
            elif any(len(vector) != width for vector in embedded):
                raise RuntimeError("Voyage returned embeddings with different dimensions")
            for (index, _text), vector in zip(batch, embedded):
                vectors[index] = vector
        if width is None:
            raise RuntimeError("Voyage returned no embeddings")
        blank = [0.0] * width
        return [vector if vector is not None else list(blank) for vector in vectors]

    def _embed_batch(self, texts: list[str], input_type: str) -> list[list[float]]:
        request = urllib.request.Request(
            f"{self.api_base}/embeddings",
            data=json.dumps({
                "model": self.model,
                "input": texts,
                "input_type": input_type,
            }).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # 400 is a permanent request error. Do not send it again.
            detail = _voyage_error_detail(exc, self.api_key)
            logger.error(
                "Voyage embeddings failed stage=embed status=%s detail=%s",
                exc.code,
                detail,
            )
            raise RuntimeError(f"Voyage embeddings returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.error(
                "Voyage embeddings failed stage=embed category=%s",
                type(exc).__name__,
            )
            raise RuntimeError("Voyage embeddings request failed") from exc
        return _vectors_from_voyage_payload(payload, len(texts))


class OllamaEmbedder:
    """Optional local Ollama embedding model."""

    provider = "ollama"

    def __init__(self, model: str | None = None, api_base: str | None = None, timeout: float | None = None):
        self.model = model or EMBEDDING_MODEL
        self.api_base = (api_base or OLLAMA_API_BASE).rstrip("/")
        self.timeout = EMBEDDING_TIMEOUT_SECONDS if timeout is None else timeout

    def embed(self, texts: list[str], input_type: str | None = None) -> list[list[float]]:
        del input_type
        if not texts:
            return []
        request = urllib.request.Request(
            f"{self.api_base}/api/embed",
            data=json.dumps({"model": self.model, "input": texts}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Ollama embedding model '{self.model}' is unavailable"
            ) from exc

        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise RuntimeError("Ollama returned an unexpected embedding response")
        return embeddings


class HashEmbedder:
    """Deterministic word-hash vectors used when the embedding API is unavailable."""

    provider = "local_hash"

    def __init__(self, dimensions: int = 64):
        self.model = "local-hash"
        self.dimensions = dimensions
        self.timeout = None

    def embed(self, texts: list[str], input_type: str | None = None) -> list[list[float]]:
        del input_type
        return [_hash_vector(text, self.dimensions) for text in texts]


def get_embedder():
    """Return the configured embedder. Voyage is the deployment default."""

    provider = os.getenv("EMBEDDING_PROVIDER", EMBEDDING_PROVIDER).strip().lower() or "voyage"
    if provider == "ollama":
        return OllamaEmbedder()
    if provider == "voyage":
        return VoyageEmbedder()
    raise RuntimeError(f"Unknown embedding provider '{provider}'. Use 'voyage' or 'ollama'.")


def _voyage_error_detail(exc: urllib.error.HTTPError, api_key: str) -> str:
    """Return Voyage's error detail without the credential or request body."""

    try:
        raw = exc.read().decode("utf-8", errors="replace")
    except Exception:
        return "unreadable error response"
    detail = raw
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
        detail = payload["detail"]
    if api_key:
        detail = detail.replace(api_key, "[redacted]")
    detail = re.sub(r"Bearer\s+\S+", "Bearer [redacted]", detail, flags=re.IGNORECASE)
    return detail[:300]


def _vectors_from_voyage_payload(payload: object, expected: int) -> list[list[float]]:
    if not isinstance(payload, dict):
        raise RuntimeError("Voyage returned a malformed embedding response")
    data = payload.get("data")
    if not isinstance(data, list) or len(data) != expected:
        raise RuntimeError("Voyage returned an unexpected embedding count")
    ordered = sorted(
        data,
        key=lambda item: item.get("index", 0) if isinstance(item, dict) else 0,
    )
    vectors = []
    for item in ordered:
        if not isinstance(item, dict):
            raise RuntimeError("Voyage returned a malformed embedding response")
        vector = item.get("embedding")
        if (
            not isinstance(vector, list)
            or not vector
            or any(not isinstance(value, (int, float)) for value in vector)
        ):
            raise RuntimeError("Voyage returned a malformed embedding vector")
        vectors.append([float(value) for value in vector])
    return vectors


def _hash_vector(text: str, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0
    return vector
