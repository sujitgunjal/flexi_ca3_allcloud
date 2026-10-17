import asyncio
import json
import math
import threading
from types import SimpleNamespace
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api import chat as chat_api


def create_test_client(monkeypatch):
    captured_states = []

    class TestCache:
        def set(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(chat_api, "cache", TestCache())
    monkeypatch.setattr(chat_api, "log_request", lambda _metrics: SimpleNamespace(id=1))
    monkeypatch.setattr(chat_api, "record_generation_metrics", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat_api, "record_cache_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat_api, "record_event", lambda *_args, **_kwargs: None)

    def invoke(state):
        captured_states.append(state)
        return {
            "selected_model": "cheap",
            "response": "Test response",
            "decision": {
                "provider": "test-provider",
                "decision_model": "test-decision-model",
                "complexity": {
                    "raw_confidence": 0.9,
                    "calibrated_confidence": 0.85,
                },
            },
            "complexity": "low",
            "uncertain": False,
            "routing_reason": "test routing decision",
        }

    monkeypatch.setattr(chat_api.llm_graph, "invoke", invoke)
    monkeypatch.setattr(
        chat_api,
        "get_tier",
        lambda _: SimpleNamespace(model="test-answer-model"),
    )

    app = FastAPI()
    app.include_router(chat_api.router, prefix="/chat")
    return TestClient(app), captured_states


def test_chat_generates_conversation_id_when_not_supplied(monkeypatch):
    client, captured_states = create_test_client(monkeypatch)

    response = client.post("/chat", json={"message": "What is Docker?"})

    assert response.status_code == 200
    body = response.json()
    UUID(body["conversation_id"])
    UUID(body["request_id"])
    assert body["status"] == "success"
    assert body["message"] == "Test response"
    assert body["decision"]["provider"] == "test-provider"
    assert body["note"]
    assert captured_states[0]["conversation_history"] == []


def test_chat_preserves_supplied_conversation_id(monkeypatch):
    client, _ = create_test_client(monkeypatch)

    response = client.post(
        "/chat",
        json={
            "conversation_id": "123",
            "message": "Explain the previous architecture",
        },
    )

    assert response.status_code == 200
    assert response.json()["conversation_id"] == "123"


def test_chat_passes_history_with_supplied_conversation_id(monkeypatch):
    client, captured_states = create_test_client(monkeypatch)
    history = [
        {"role": "user", "content": "What is an LLM gateway?"},
        {"role": "assistant", "content": "An LLM gateway is..."},
    ]

    response = client.post(
        "/chat",
        json={
            "conversation_id": "123",
            "message": "Explain the previous architecture",
            "history": history,
        },
    )

    assert response.status_code == 200
    assert response.json()["conversation_id"] == "123"
    assert captured_states[0]["conversation_history"] == history


def test_chat_returns_success_when_cache_write_fails(monkeypatch):
    from redis.exceptions import RedisError

    class FailingCache:
        def set(self, *_args, **_kwargs):
            raise RedisError("simulated cache failure")

    client, _ = create_test_client(monkeypatch)
    monkeypatch.setattr(chat_api, "cache", FailingCache())

    response = client.post("/chat", json={"message": "What is Docker?"})

    assert response.status_code == 200
    assert response.json()["message"] == "Test response"


def test_chat_persists_source_query_then_hits_semantic_cache(monkeypatch):
    from app.agents import cache_agent as cache_agent_module
    from app.agents.cache_agent import CacheAgent
    from app.cache.redis_cache import RedisCache, generate_cache_key

    class MemoryRedis:
        def __init__(self):
            self.values = {}

        def get(self, key):
            return self.values.get(key)

        def set(self, key, value, ex=None):
            self.values[key] = value

        def scan_iter(self, match=None, count=None):
            return iter(key for key in self.values if key.startswith("llm_cache:"))

    source_query = "What is HTTP?"
    followup_query = "Explain HTTP in simple terms"
    similarity = 0.8677494373576463
    response_cache = RedisCache(MemoryRedis())

    class Embedder:
        def embed(self, texts):
            assert texts == [followup_query, source_query]
            return [
                [similarity, math.sqrt(1 - similarity**2)],
                [1.0, 0.0],
            ]

    cache_agent = CacheAgent(response_cache, embedder=Embedder())
    monkeypatch.setattr(cache_agent_module, "record_cache_event", lambda *_args, **_kwargs: None)
    client, _ = create_test_client(monkeypatch)
    monkeypatch.setattr(chat_api, "cache", response_cache)
    generated = []

    def invoke(state):
        state = cache_agent.run(state)
        if state.get("cached_response"):
            return state
        generated.append(state["query"])
        state.update(
            selected_model="cheap",
            actual_model="cheap",
            response="HTTP is a protocol for transferring web data.",
            decision={
                "provider": "test-provider",
                "decision_model": "test-decision-model",
                "complexity": {
                    "raw_confidence": 0.9,
                    "calibrated_confidence": 0.85,
                },
            },
            complexity="low",
            uncertain=False,
            routing_reason="test routing decision",
        )
        return state

    monkeypatch.setattr(chat_api.llm_graph, "invoke", invoke)

    first_response = client.post("/chat", json={"message": source_query})
    cache_key = generate_cache_key(source_query)
    saved_entry = response_cache.get(cache_key)
    assert first_response.status_code == 200
    assert saved_entry["_cache_query"] == source_query
    assert response_cache.client.get(cache_key) is not None

    followup_response = client.post("/chat", json={"message": followup_query})

    assert followup_response.status_code == 200
    assert followup_response.json()["message"] == first_response.json()["message"]
    assert followup_response.json()["details"]["cache_hit"] is True
    assert generated == [source_query]


@pytest.mark.anyio
@pytest.mark.parametrize("blocked_operation", ["cache", "metrics"])
async def test_chat_sends_response_before_optional_write_finishes(
    monkeypatch,
    blocked_operation,
):
    from fastapi import FastAPI
    from app.api import chat as chat_api

    started = threading.Event()
    release = threading.Event()
    sent_messages = []

    def block():
        started.set()
        release.wait(timeout=3)

    class BlockingCache:
        def set(self, *_args, **_kwargs):
            if blocked_operation == "cache":
                block()

    def record_metrics(*_args, **_kwargs):
        if blocked_operation == "metrics":
            block()

    monkeypatch.setattr(chat_api, "cache", BlockingCache())
    monkeypatch.setattr(chat_api, "log_request", lambda _metrics: SimpleNamespace(id=1))
    monkeypatch.setattr(chat_api, "record_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat_api, "record_generation_metrics", record_metrics)
    monkeypatch.setattr(
        chat_api.llm_graph,
        "invoke",
        lambda _state: {"selected_model": "local", "actual_model": "local", "response": "fast answer"},
    )

    app = FastAPI()
    app.include_router(chat_api.router, prefix="/chat")
    response_body_sent = asyncio.Event()
    request_messages = [
        {
            "type": "http.request",
            "body": json.dumps({"message": "question"}).encode(),
            "more_body": False,
        }
    ]

    async def receive():
        if request_messages:
            return request_messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        sent_messages.append(message)
        if message["type"] == "http.response.body":
            response_body_sent.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/chat",
        "raw_path": b"/chat",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "server": ("testserver", 80),
        "client": ("testclient", 123),
    }
    app_task = asyncio.create_task(app(scope, receive, send))
    try:
        await asyncio.wait_for(response_body_sent.wait(), timeout=1)
        assert await asyncio.to_thread(started.wait, 1)
        status = next(
            item["status"]
            for item in sent_messages
            if item["type"] == "http.response.start"
        )
        assert status == 200
    finally:
        release.set()
        await asyncio.wait_for(app_task, timeout=2)
