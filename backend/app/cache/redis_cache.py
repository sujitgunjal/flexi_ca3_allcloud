"""Small JSON-only Redis response cache."""

import hashlib
import json
import math
import re
from typing import Any

import redis
from redis.exceptions import RedisError

from app.providers.config import (
    REDIS_DB, REDIS_HOST, REDIS_PORT, REDIS_TTL,
    SEMANTIC_CACHE_MAX_CANDIDATES, SEMANTIC_CACHE_THRESHOLD,
)


def generate_cache_key(query: str) -> str:
    """Build a stable key from a query without changing its semantics."""
    normalized = re.sub(r"\s+", " ", query.strip())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"llm_cache:{digest}"


class RedisCache:
    """Redis cache storing JSON-compatible response data only."""

    def __init__(self, client: Any | None = None, ttl: int | None = None):
        self.client = client or redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
            decode_responses=True, socket_connect_timeout=1, socket_timeout=1,
        )
        self.ttl = REDIS_TTL if ttl is None else ttl

    def get(self, key: str) -> Any | None:
        value = self.client.get(key)
        return None if value is None else json.loads(value)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        # Validate before writing so arbitrary Python objects never reach Redis.
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        self.client.set(key, encoded, ex=self.ttl if ttl is None else ttl)

    def delete(self, key: str) -> int:
        return self.client.delete(key)

    def exists(self, key: str) -> bool:
        return bool(self.client.exists(key))

    def find_semantic(self, query: str, embedder: Any) -> Any | None:
        """Find a safe, similar cached response among recent live cache keys."""
        candidates = []
        scanned = 0
        for key in self.client.scan_iter(match="llm_cache:*", count=100):
            if scanned >= SEMANTIC_CACHE_MAX_CANDIDATES:
                break
            scanned += 1
            if key == generate_cache_key(query):
                continue
            value = self.get(key)
            source_query = value.get("_cache_query") if isinstance(value, dict) else None
            if source_query and _compatible_queries(query, source_query):
                candidates.append((key, source_query, value))
            if len(candidates) >= SEMANTIC_CACHE_MAX_CANDIDATES:
                break
        if not candidates:
            return None
        vectors = embedder.embed([query] + [item[1] for item in candidates])
        if len(vectors) != len(candidates) + 1:
            raise ValueError("Unexpected semantic cache embedding count")
        best = max(
            ((_cosine(vectors[0], vectors[index + 1]), item)
             for index, item in enumerate(candidates)),
            key=lambda pair: pair[0],
        )
        return best[1][2] if best[0] >= SEMANTIC_CACHE_THRESHOLD else None


def _compatible_queries(query: str, cached_query: str) -> bool:
    """Reject different request intents and explicit answer-depth requests."""
    def features(text: str) -> tuple[str, str]:
        words = set(re.findall(r"[a-z]+", text.lower()))
        detailed = bool(words & {"detail", "detailed", "elaborate", "comprehensive", "thorough", "in-depth", "deep"})
        if words & {"compare", "comparison", "difference", "versus", "vs"}:
            intent = "compare"
        elif words & {"how", "steps", "procedure", "implement", "make", "build"}:
            intent = "how"
        elif words & {"why", "reason", "cause"}:
            intent = "why"
        elif words & {"list", "examples", "example", "types", "kinds"}:
            intent = "list"
        else:
            intent = "explain"
        return intent, "detailed" if detailed else "standard"

    return features(query) == features(cached_query)


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


cache = RedisCache()

__all__ = ["RedisCache", "RedisError", "cache", "generate_cache_key"]
