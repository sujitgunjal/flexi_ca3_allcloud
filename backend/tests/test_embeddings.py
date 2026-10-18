import json

import pytest

from app.context.embeddings import (
    HashEmbedder,
    OllamaEmbedder,
    VoyageEmbedder,
    embedding_identity,
    get_embedder,
)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _voyage_payload(*vectors):
    return {
        "data": [
            {"index": index, "embedding": vector}
            for index, vector in enumerate(vectors)
        ]
    }


def test_voyage_provider_selects_voyage_embedder(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "voyage")
    monkeypatch.setenv("VOYAGE_EMBEDDING_MODEL", "voyage-4-lite")

    embedder = get_embedder()

    assert isinstance(embedder, VoyageEmbedder)
    assert embedder.model == "voyage-4-lite"


def test_ollama_provider_remains_selectable(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("EMBEDDING_MODEL", "nomic-embed-text:latest")

    embedder = get_embedder()

    assert isinstance(embedder, OllamaEmbedder)
    assert embedder.model == "nomic-embed-text:latest"


def test_voyage_request_uses_endpoint_model_auth_and_input_type(monkeypatch):
    captured = {}

    def urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _Response(_voyage_payload([0.1, 0.2]))

    monkeypatch.setattr("app.context.embeddings.urllib.request.urlopen", urlopen)
    embedder = VoyageEmbedder(
        model="voyage-4-lite",
        api_base="https://api.voyageai.com/v1",
        api_key="test-voyage-key",
        timeout=12,
    )

    vectors = embedder.embed(["history text"], input_type="document")

    assert vectors == [[0.1, 0.2]]
    assert captured["url"] == "https://api.voyageai.com/v1/embeddings"
    assert captured["timeout"] == 12
    assert captured["headers"]["Authorization"] == "Bearer test-voyage-key"
    assert captured["body"] == {
        "model": "voyage-4-lite",
        "input": ["history text"],
        "input_type": "document",
    }


def test_voyage_reorders_vectors_by_index(monkeypatch):
    def urlopen(_request, timeout=0):
        return _Response({
            "data": [
                {"index": 1, "embedding": [0.0, 1.0]},
                {"index": 0, "embedding": [1.0, 0.0]},
            ]
        })

    monkeypatch.setattr("app.context.embeddings.urllib.request.urlopen", urlopen)
    vectors = VoyageEmbedder(api_key="test-voyage-key").embed(["a", "b"])

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]


def test_missing_voyage_key_is_rejected_before_request():
    with pytest.raises(RuntimeError, match="VOYAGE_API_KEY"):
        VoyageEmbedder(api_key="").embed(["question"])


def test_malformed_voyage_response_is_rejected(monkeypatch):
    monkeypatch.setattr(
        "app.context.embeddings.urllib.request.urlopen",
        lambda *_args, **_kwargs: _Response({"data": [{"embedding": []}]}),
    )

    with pytest.raises(RuntimeError, match="malformed"):
        VoyageEmbedder(api_key="test-voyage-key").embed(["question"])


def test_voyage_timeout_uses_existing_context_fallback(monkeypatch):
    from app.agents.context_agent import ContextAgent

    monkeypatch.setenv("EMBEDDING_PROVIDER", "voyage")
    monkeypatch.setenv("VOYAGE_API_KEY", "test-voyage-key")

    def urlopen(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr("app.context.embeddings.urllib.request.urlopen", urlopen)
    result = ContextAgent().run({
        "query": "How does Redis expire a cache key?",
        "conversation_history": [
            {"role": "assistant", "content": "A Redis TTL expires the cached response automatically."},
        ],
        "context_requirement": "medium",
    })

    assert result["embedding_source"] == "local_hash"
    assert result["messages_selected"] == 1


def test_cache_and_context_share_the_factory(monkeypatch):
    from app.agents.cache_agent import CacheAgent
    from app.agents.context_agent import ContextAgent
    from app.cache.redis_cache import RedisCache

    class Memory:
        def get(self, _key):
            return None

        def set(self, *_args, **_kwargs):
            return None

        def scan_iter(self, match=None, count=None):
            return iter(())

    monkeypatch.setenv("EMBEDDING_PROVIDER", "voyage")
    monkeypatch.setenv("VOYAGE_EMBEDDING_MODEL", "voyage-4-lite")
    shared = get_embedder()
    cache_embedder = CacheAgent(RedisCache(Memory())).embedder
    context_embedder, source = ContextAgent()._embedder()

    assert isinstance(shared, VoyageEmbedder)
    assert isinstance(cache_embedder, VoyageEmbedder)
    assert isinstance(context_embedder, VoyageEmbedder)
    assert cache_embedder.model == context_embedder.model == "voyage-4-lite"
    assert source == "voyage:voyage-4-lite"


def test_context_uses_query_and_document_input_types():
    from app.agents.context_agent import ContextAgent

    calls = []

    class Recorder:
        def embed(self, texts, input_type=None):
            calls.append((list(texts), input_type))
            return [[1.0, 0.0] for _ in texts]

    ContextAgent(embedder=Recorder()).run({
        "query": "How does Redis expire a cache key?",
        "conversation_history": [
            {"role": "assistant", "content": "A Redis TTL expires the cached response."},
        ],
        "context_requirement": "low",
    })

    assert calls[0][1] == "query"
    assert calls[1][1] == "document"


def test_incompatible_embedding_models_are_not_scanned_together(monkeypatch):
    from app.cache.redis_cache import RedisCache, generate_cache_key
    from tests.test_cache import MemoryRedis

    monkeypatch.setenv("EMBEDDING_PROVIDER", "voyage")
    monkeypatch.setenv("VOYAGE_EMBEDDING_MODEL", "voyage-4-lite")
    cache = RedisCache(MemoryRedis())
    cache.client.values["llm_cache:ollama:nomic-embed-text:latest:old"] = json.dumps({
        "response": "old answer",
        "_cache_query": "What is HTTP?",
    })
    cache.set(generate_cache_key("What is SMTP?"), {
        "response": "smtp",
        "_cache_query": "What is SMTP?",
    })

    class Embedder:
        def embed(self, texts):
            assert all("HTTP" not in text for text in texts[1:])
            return [[1.0, 0.0] for _ in texts]

    assert embedding_identity() == "voyage:voyage-4-lite"
    assert "ollama:nomic-embed-text" not in generate_cache_key("What is HTTP?")
    assert cache.find_semantic("Explain SMTP", Embedder())["response"] == "smtp"


def test_mismatched_vector_widths_do_not_score_as_similar():
    from app.cache.redis_cache import _cosine

    nomic_width = [0.1] * 768
    voyage_width = [0.1] * 1024
    assert _cosine(nomic_width, voyage_width) == 0.0
    assert len(HashEmbedder().embed(["same"])[0]) == 64
