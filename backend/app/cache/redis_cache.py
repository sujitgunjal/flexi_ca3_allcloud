
"""JSON-only Redis response cache with Upstash REST support."""

import hashlib
import json
import logging
import math
import re
from typing import Any, Iterator

import redis
from redis.exceptions import RedisError
from upstash_redis import Redis as UpstashRedis

from app.context.embeddings import embedding_identity
from app.providers.config import (
    REDIS_DB,
    REDIS_HOST,
    REDIS_PORT,
    REDIS_TTL,
    REDIS_URL,
    UPSTASH_REDIS_REST_URL,
    UPSTASH_REDIS_REST_TOKEN,
    SEMANTIC_CACHE_MAX_CANDIDATES,
    SEMANTIC_CACHE_THRESHOLD,
)

logger = logging.getLogger(__name__)


def _query_fingerprint(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]


def generate_cache_key(query: str) -> str:
    """Build a stable key from a query without changing its semantics."""
    normalized = re.sub(r"\s+", " ", query.strip())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"llm_cache:{embedding_identity()}:{digest}"


def _iter_cache_keys(
    client: Any,
    match: str,
    count: int = 100,
) -> Iterator[str]:
    """Iterate over matching keys for Upstash REST or standard Redis."""
    if isinstance(client, UpstashRedis):
        cursor = 0
        while True:
            result = client.scan(cursor, match=match, count=count)

            # Upstash SDK scan returns (next_cursor, keys).
            cursor, keys = result
            yield from keys

            if int(cursor) == 0:
                break
    else:
        yield from client.scan_iter(match=match, count=count)


class RedisCache:
    """Redis cache storing JSON-compatible response data only."""

    def __init__(
        self,
        client: Any | None = None,
        ttl: int | None = None,
    ):
        if client is not None:
            self.client = client
        elif UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN:
            self.client = UpstashRedis(
                url=UPSTASH_REDIS_REST_URL,
                token=UPSTASH_REDIS_REST_TOKEN,
                allow_telemetry=False,
            )
        elif REDIS_URL:
            self.client = redis.Redis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        else:
            self.client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )

        self.ttl = REDIS_TTL if ttl is None else ttl

    def get(self, key: str) -> Any | None:
        value = self.client.get(key)
        return None if value is None else json.loads(value)

    def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> None:
        encoded = json.dumps(
            value,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        entry_ttl = self.ttl if ttl is None else ttl
        self.client.set(key, encoded, ex=entry_ttl)

        if key.startswith("llm_cache:"):
            source_query = (
                value.get("_cache_query")
                if isinstance(value, dict)
                else None
            )
            logger.debug(
                "Response cache write complete key=%s "
                "source_query_fingerprint=%s ttl_seconds=%d",
                key.rsplit(":", 1)[-1][:12],
                (
                    _query_fingerprint(source_query)
                    if isinstance(source_query, str)
                    else "missing"
                ),
                entry_ttl,
            )

    def delete(self, key: str) -> int:
        return self.client.delete(key)

    def exists(self, key: str) -> bool:
        return bool(self.client.exists(key))

    def find_semantic(
        self,
        query: str,
        embedder: Any,
    ) -> Any | None:
        """Find a safe, similar cached response among live cache keys."""
        candidates = []
        scanned = 0
        filtered = 0

        keys = _iter_cache_keys(
            self.client,
            match=f"llm_cache:{embedding_identity()}:*",
            count=100,
        )

        for key in keys:
            if scanned >= SEMANTIC_CACHE_MAX_CANDIDATES:
                break

            scanned += 1

            if key == generate_cache_key(query):
                filtered += 1
                logger.debug(
                    "Semantic cache candidate skipped key=%s "
                    "reason=exact_key",
                    key.rsplit(":", 1)[-1][:12],
                )
                continue

            value = self.get(key)
            source_query = (
                value.get("_cache_query")
                if isinstance(value, dict)
                else None
            )

            if not isinstance(source_query, str) or not source_query:
                filtered += 1
                logger.debug(
                    "Semantic cache candidate skipped key=%s "
                    "reason=missing_source_query",
                    key.rsplit(":", 1)[-1][:12],
                )
                continue

            if not _compatible_queries(query, source_query):
                filtered += 1
                logger.debug(
                    "Semantic cache candidate skipped key=%s "
                    "source_query_fingerprint=%s "
                    "reason=intent_or_depth_mismatch",
                    key.rsplit(":", 1)[-1][:12],
                    _query_fingerprint(source_query),
                )
                continue

            candidates.append((key, source_query, value))

            if len(candidates) >= SEMANTIC_CACHE_MAX_CANDIDATES:
                break

        logger.debug(
            "Semantic cache scan complete examined=%d eligible=%d "
            "filtered=%d candidate_limit=%d",
            scanned,
            len(candidates),
            filtered,
            SEMANTIC_CACHE_MAX_CANDIDATES,
        )

        if not candidates:
            logger.debug(
                "Semantic cache lookup miss reason=no_eligible_candidates"
            )
            return None

        vectors = embedder.embed(
            [query] + [item[1] for item in candidates]
        )

        if len(vectors) != len(candidates) + 1:
            raise ValueError("Unexpected semantic cache embedding count")

        scored = [
            (_cosine(vectors[0], vectors[index + 1]), item)
            for index, item in enumerate(candidates)
        ]

        for score, (key, source_query, _value) in scored:
            logger.debug(
                "Semantic cache candidate score key=%s "
                "source_query_fingerprint=%s cosine=%.6f "
                "threshold=%.4f",
                key.rsplit(":", 1)[-1][:12],
                _query_fingerprint(source_query),
                score,
                SEMANTIC_CACHE_THRESHOLD,
            )

        best_score, best_candidate = max(
            scored,
            key=lambda pair: pair[0],
        )

        if best_score < SEMANTIC_CACHE_THRESHOLD:
            logger.debug(
                "Semantic cache lookup miss reason=below_threshold "
                "best_score=%.6f threshold=%.4f",
                best_score,
                SEMANTIC_CACHE_THRESHOLD,
            )
            return None

        logger.debug(
            "Semantic cache lookup hit score=%.6f threshold=%.4f",
            best_score,
            SEMANTIC_CACHE_THRESHOLD,
        )
        return best_candidate[2]


def _compatible_queries(
    query: str,
    cached_query: str,
) -> bool:
    """Reject different request intents and explicit answer-depth requests."""

    def features(text: str) -> tuple[str, str]:
        words = set(re.findall(r"[a-z]+", text.lower()))

        detailed = bool(
            words
            & {
                "detail",
                "detailed",
                "elaborate",
                "comprehensive",
                "thorough",
                "in-depth",
                "deep",
            }
        )

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


def _cosine(
    left: list[float],
    right: list[float],
) -> float:
    if not left or len(left) != len(right):
        return 0.0

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))

    return (
        dot / (left_norm * right_norm)
        if left_norm and right_norm
        else 0.0
    )


cache = RedisCache()

__all__ = [
    "RedisCache",
    "RedisError",
    "cache",
    "generate_cache_key",
]
