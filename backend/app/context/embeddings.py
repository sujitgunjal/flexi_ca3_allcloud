import hashlib
import json
import re
import urllib.error
import urllib.request

from app.providers.config import EMBEDDING_MODEL, OLLAMA_API_BASE


class OllamaEmbedder:
    """Embed text with the local Ollama embedding model."""

    def __init__(self, model: str | None = None, api_base: str | None = None, timeout: float = 30):
        self.model = model or EMBEDDING_MODEL
        self.api_base = (api_base or OLLAMA_API_BASE).rstrip("/")
        self.timeout = timeout

    def embed(self, texts: list[str]) -> list[list[float]]:
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
    """Deterministic word-hash vectors used when Ollama embeddings are unavailable."""

    def __init__(self, dimensions: int = 64):
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_hash_vector(text, self.dimensions) for text in texts]


def _hash_vector(text: str, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0
    return vector
