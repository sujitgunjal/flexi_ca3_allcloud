import logging
from time import perf_counter

from redis.exceptions import RedisError

from app.cache.redis_cache import cache, generate_cache_key
from app.context.embeddings import OllamaEmbedder
from app.orchestration.state import RequestState
from app.services.metrics_service import record_cache_event

logger = logging.getLogger(__name__)


class CacheAgent:
    def __init__(self, cache_service=cache, embedder=None):
        self.cache = cache_service
        self.embedder = embedder or OllamaEmbedder()

    def run(self, state: RequestState) -> RequestState:
        key = generate_cache_key(state.get("query", ""))
        state["cache_key"] = key
        started = perf_counter()
        hit = False
        try:
            value = self.cache.get(key)
            logger.debug(
                "Response cache exact lookup result=%s key=%s",
                "hit" if value is not None else "miss",
                key.rsplit(":", 1)[-1][:12],
            )
            if value is None:
                try:
                    logger.debug(
                        "Response cache semantic lookup started query_fingerprint=%s",
                        key.rsplit(":", 1)[-1][:12],
                    )
                    value = self.cache.find_semantic(state.get("query", ""), self.embedder)
                except RedisError:
                    raise
                except Exception:
                    logger.warning(
                        "Semantic cache lookup failed category=embedding_or_lookup_error; continuing to model flow"
                    )
            hit = value is not None
            if value is None:
                logger.debug("Response cache final result=miss")
            else:
                logger.debug("Response cache final result=hit")
            if hit:
                value = {name: item for name, item in value.items() if name != "_cache_query"}
                state.update(value)
                state["cached_response"] = True
            state["cache_unavailable"] = False
        except RedisError:
            state["cache_unavailable"] = True
            logger.exception("Redis cache unavailable; continuing without cache")
        latency_ms = (perf_counter() - started) * 1000
        state["cache_hit"] = hit

        request_id = state.get("metrics_request_id")
        if request_id is not None:
            record_cache_event(request_id, hit, key, latency_ms,
                               fallback_used=state["cache_unavailable"])

        return state
