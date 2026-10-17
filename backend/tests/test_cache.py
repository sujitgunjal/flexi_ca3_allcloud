import json
import math
import time

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.cache.redis_cache import RedisCache, generate_cache_key


class MemoryRedis:
    def __init__(self):
        self.values = {}
        self.expirations = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex):
        self.values[key] = value
        self.expirations[key] = ex

    def delete(self, key):
        return int(self.values.pop(key, None) is not None)

    def exists(self, key):
        return key in self.values

    def scan_iter(self, match=None, count=None):
        return iter(key for key in self.values if key.startswith("llm_cache:"))


def test_json_set_get_ttl_delete_exists_and_default_ttl():
    client = MemoryRedis()
    cache = RedisCache(client, ttl=3600)
    cache.set("key", {"message": "hello"})
    assert client.expirations["key"] == 3600
    assert json.loads(client.values["key"]) == {"message": "hello"}
    assert cache.get("key") == {"message": "hello"}
    assert cache.exists("key") is True
    assert cache.delete("key") == 1
    assert cache.exists("key") is False


def test_set_allows_per_entry_ttl_and_rejects_python_objects():
    cache = RedisCache(MemoryRedis(), ttl=9)
    cache.set("key", [1, 2], ttl=3)
    assert cache.client.expirations["key"] == 3
    with pytest.raises(TypeError):
        cache.set("bad", object())


def test_key_normalizes_whitespace_but_preserves_query_meaning():
    assert generate_cache_key("  What   is Docker?\n") == generate_cache_key("What is Docker?")
    assert generate_cache_key("What is Docker?") != generate_cache_key("What is docker?")
    assert generate_cache_key("one two") != generate_cache_key("onetwo")
    assert generate_cache_key("q").startswith("llm_cache:")


def test_cache_agent_records_event_and_falls_back_on_redis_error(monkeypatch):
    from app.agents.cache_agent import CacheAgent
    from app.services import metrics_service

    class BrokenCache:
        def get(self, _key):
            raise RedisConnectionError("unavailable")

    events = []
    monkeypatch.setattr(metrics_service, "record_cache_event", lambda *args, **kwargs: events.append((args, kwargs)))
    # CacheAgent imports the callable directly, so patch its local reference too.
    import app.agents.cache_agent as agent_module
    monkeypatch.setattr(agent_module, "record_cache_event", lambda *args, **kwargs: events.append((args, kwargs)))
    state = CacheAgent(BrokenCache()).run({"query": "test", "metrics_request_id": 42})
    assert state["cache_hit"] is False
    assert state["cache_unavailable"] is True
    assert events[0][0][:2] == (42, False)
    assert events[0][1]["fallback_used"] is True


def test_exact_cache_hit_skips_semantic_lookup():
    from app.agents.cache_agent import CacheAgent

    cache = RedisCache(MemoryRedis())
    key = generate_cache_key("What is cloud computing?")
    cache.set(key, {"response": "exact answer"})
    cache.find_semantic = lambda *_args: pytest.fail("semantic lookup should not run")
    result = CacheAgent(cache).run({"query": "What is cloud computing?"})
    assert result["cache_hit"] is True
    assert result["response"] == "exact answer"


def test_equivalent_wording_reuses_semantic_response():
    from app.agents.cache_agent import CacheAgent

    cache = RedisCache(MemoryRedis())
    cache.set(generate_cache_key("What is HTTP?"), {
        "response": "A cached answer", "_cache_query": "What is HTTP?",
    })

    class Embedder:
        def embed(self, texts):
            assert texts == ["Define HTTP", "What is HTTP?"]
            return [[0.9332545, 0.359216], [1.0, 0.0]]

    result = CacheAgent(cache, embedder=Embedder()).run({"query": "Define HTTP"})
    assert result["cache_hit"] is True
    assert result["response"] == "A cached answer"


def test_simple_terms_prompt_reuses_http_definition_at_measured_similarity():
    from app.agents.cache_agent import CacheAgent
    from app.providers.config import SEMANTIC_CACHE_THRESHOLD

    source_query = "What is HTTP?"
    incoming_query = "Explain HTTP in simple terms"
    cache = RedisCache(MemoryRedis())
    key = generate_cache_key(source_query)
    cache.set(key, {
        "response": "A cached answer", "_cache_query": source_query,
    })
    assert cache.get(key)["_cache_query"] == source_query

    measured_similarity = 0.8677494373576463

    class Embedder:
        def embed(self, texts):
            assert texts == [incoming_query, source_query]
            return [
                [measured_similarity, math.sqrt(1 - measured_similarity**2)],
                [1.0, 0.0],
            ]

    result = CacheAgent(cache, embedder=Embedder()).run({"query": incoming_query})

    assert measured_similarity >= SEMANTIC_CACHE_THRESHOLD
    assert result["cache_hit"] is True
    assert result["response"] == "A cached answer"


def test_unrelated_query_does_not_reuse_response():
    from app.cache.redis_cache import RedisCache

    cache = RedisCache(MemoryRedis())
    cached_query = "Explain SMTP in simple terms"
    incoming_query = "Explain HTTP in simple terms"
    cache.set(generate_cache_key(cached_query), {
        "response": "SMTP", "_cache_query": cached_query,
    })

    class Embedder:
        def embed(self, texts):
            assert texts == [incoming_query, cached_query]
            measured_similarity = 0.704534
            return [
                [measured_similarity, math.sqrt(1 - measured_similarity**2)],
                [1.0, 0.0],
            ]

    assert cache.find_semantic(incoming_query, Embedder()) is None


def test_default_cache_agent_uses_embedder_default_timeout():
    from app.agents.cache_agent import CacheAgent
    from app.context.embeddings import OllamaEmbedder

    default_embedder = OllamaEmbedder()
    agent_embedder = CacheAgent(RedisCache(MemoryRedis())).embedder

    assert agent_embedder.model == default_embedder.model
    assert agent_embedder.timeout == default_embedder.timeout


def test_detailed_request_does_not_reuse_short_definition():
    from app.cache.redis_cache import _compatible_queries

    assert not _compatible_queries("Elaborate cloud computing", "What is cloud computing?")
    assert _compatible_queries("Explain cloud computing", "What is cloud computing?")


def test_semantic_embedding_failure_falls_back_to_normal_flow(monkeypatch):
    from app.agents.cache_agent import CacheAgent

    class FailingCache:
        def get(self, _key):
            return None

        def find_semantic(self, *_args):
            raise RuntimeError("embedding unavailable")

    result = CacheAgent(FailingCache()).run({"query": "Explain cloud computing"})
    assert result["cache_hit"] is False
    assert result.get("cached_response") is None
    assert result["cache_unavailable"] is False


def test_cache_miss_retains_cache_key_for_normal_generation():
    from app.agents.cache_agent import CacheAgent

    result = CacheAgent(RedisCache(MemoryRedis())).run({"query": "new question"})
    assert result["cache_hit"] is False
    assert result["cache_key"] == generate_cache_key("new question")


def test_graph_cache_hit_bypasses_model_nodes(monkeypatch):
    import app.orchestration.graph as graph_module

    calls = []

    class Cached:
        def run(self, state):
            state.update(cached_response=True, cache_hit=True, response="cached")
            return state

    class ShouldNotRun:
        def run(self, state):
            calls.append(True)
            return state

    monkeypatch.setattr(graph_module, "cache_agent", Cached())
    monkeypatch.setattr(graph_module, "complexity_agent", ShouldNotRun())
    monkeypatch.setattr(graph_module, "context_agent", ShouldNotRun())
    monkeypatch.setattr(graph_module, "router_agent", ShouldNotRun())
    monkeypatch.setattr(graph_module, "generate_agent", ShouldNotRun())
    monkeypatch.setattr(graph_module, "quality_agent", ShouldNotRun())

    result = graph_module.build_graph().invoke({"query": "cached question"})
    assert result["response"] == "cached"
    assert calls == []


def test_graph_cache_miss_runs_normal_model_flow(monkeypatch):
    import app.orchestration.graph as graph_module

    calls = []

    class CacheMiss:
        def run(self, state):
            state.update(cache_hit=False, cached_response=False)
            return state

    class Node:
        def __init__(self, name):
            self.name = name

        def run(self, state):
            calls.append(self.name)
            if self.name == "quality":
                state["escalation"] = False
            if self.name == "generate":
                state["response"] = "generated"
            return state

    monkeypatch.setattr(graph_module, "cache_agent", CacheMiss())
    monkeypatch.setattr(graph_module, "complexity_agent", Node("complexity"))
    monkeypatch.setattr(graph_module, "context_agent", Node("context"))
    monkeypatch.setattr(graph_module, "router_agent", Node("router"))
    monkeypatch.setattr(graph_module, "generate_agent", Node("generate"))
    monkeypatch.setattr(graph_module, "quality_agent", Node("quality"))

    result = graph_module.build_graph().invoke({"query": "new question"})
    assert result["response"] == "generated"
    assert calls == ["complexity", "context", "router", "generate", "quality"]


@pytest.mark.integration
def test_real_redis_connection_set_get_ttl_and_delete():
    import redis
    from app.providers.config import REDIS_DB, REDIS_HOST, REDIS_PORT

    client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
                         decode_responses=True, socket_connect_timeout=0.2,
                         socket_timeout=0.2)
    try:
        client.ping()
    except redis.RedisError:
        pytest.skip("Redis integration service is unavailable")
    cache = RedisCache(client)
    key = generate_cache_key(f"integration-{time.time_ns()}")
    try:
        cache.set(key, {"ok": True}, ttl=1)
        assert cache.get(key) == {"ok": True}
        assert cache.exists(key)
        assert client.ttl(key) <= 1
        time.sleep(1.05)
        assert cache.get(key) is None
        assert cache.delete(key) == 0
        assert cache.get(key) is None
    finally:
        cache.delete(key)
