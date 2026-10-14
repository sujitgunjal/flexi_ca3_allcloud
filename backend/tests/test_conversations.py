import mongomock
from types import SimpleNamespace
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.api import conversations as conversations_api
from app.chat_history.store import MongoConversationStore


def _store() -> MongoConversationStore:
    return MongoConversationStore(mongomock.MongoClient()["switchboard"])


def _client(monkeypatch, store: MongoConversationStore | None = None):
    captured = []

    class TestCache:
        def set(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(chat_api, "cache", TestCache())
    monkeypatch.setattr(chat_api, "log_request", lambda _metrics: SimpleNamespace(id=1))
    monkeypatch.setattr(chat_api, "record_generation_metrics", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat_api, "record_cache_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat_api, "record_event", lambda *_args, **_kwargs: None)

    def invoke(state):
        captured.append(state)
        return {
            "selected_model": "cheap",
            "actual_model": "cheap",
            "response": f"Answer to {state['query']}",
            "decision": {"provider": "ollama", "decision_model": "llama3:8b"},
            "complexity": "simple",
            "uncertain": False,
            "routing_reason": "confident simple request",
            "quality_score": 0.9,
            "quality_relevant": "YES",
            "quality_complete": "YES",
            "quality_escalate": "NO",
            "input_tokens": 12,
            "output_tokens": 20,
            "cache_hit": False,
            "escalation_attempted": False,
            "fallback_used": False,
        }

    monkeypatch.setattr(chat_api.llm_graph, "invoke", invoke)
    monkeypatch.setattr(
        chat_api,
        "get_tier",
        lambda _tier: SimpleNamespace(model="nvidia/test-model"),
    )
    conversations_api.set_conversation_store(store if store is not None else _store())

    app = FastAPI()
    app.include_router(conversations_api.router, prefix="/conversations")
    app.include_router(chat_api.router, prefix="/chat")
    return TestClient(app), captured


def test_conversation_can_be_created_reopened_renamed_and_deleted(monkeypatch):
    client, _captured = _client(monkeypatch)

    created = client.post("/conversations")
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    UUID(conversation_id)
    assert created.json()["title"] == "New chat"
    assert created.json()["messages"] == []

    renamed = client.patch(
        f"/conversations/{conversation_id}",
        json={"title": "Routing notes"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Routing notes"

    listed = client.get("/conversations")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == conversation_id
    assert listed.json()[0]["title"] == "Routing notes"

    opened = client.get(f"/conversations/{conversation_id}")
    assert opened.status_code == 200
    assert opened.json()["title"] == "Routing notes"

    deleted = client.delete(f"/conversations/{conversation_id}")
    assert deleted.status_code == 204
    assert client.get(f"/conversations/{conversation_id}").status_code == 404
    assert client.get("/conversations").json() == []


def test_send_uses_chat_workflow_and_keeps_details_on_the_assistant_message(monkeypatch):
    client, captured = _client(monkeypatch)
    conversation_id = client.post("/conversations").json()["id"]

    first = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"message": "What does HTTP stand for?"},
    )
    assert first.status_code == 200
    body = first.json()
    assert body["conversation"]["title"] == "What does HTTP stand for?"
    assert captured[0]["conversation_history"] == []
    assert captured[0]["query"] == "What does HTTP stand for?"

    messages = body["conversation"]["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["details"] is None
    details = messages[1]["details"]
    assert details["model_tier"] == "cheap"
    assert details["actual_model"] == "nvidia/test-model"
    assert details["complexity"] == "simple"
    assert details["quality_status"] == "pass"
    assert details["quality_relevant"] == "YES"
    assert details["latency_ms"] >= 0
    assert details["input_tokens"] == 12
    assert details["output_tokens"] == 20
    assert details["cache_hit"] is False
    assert details["escalated"] is False
    assert messages[1]["request_id"] == body["request_id"]

    second = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"message": "Give the long form again."},
    )
    assert second.status_code == 200
    assert captured[1]["conversation_history"] == [
        {"role": "user", "content": "What does HTTP stand for?"},
        {"role": "assistant", "content": "Answer to What does HTTP stand for?"},
    ]
    reopened = client.get(f"/conversations/{conversation_id}").json()
    assert len(reopened["messages"]) == 4
    assert reopened["messages"][1]["details"]["actual_model"] == "nvidia/test-model"
    assert reopened["messages"][3]["content"] == "Answer to Give the long form again."
    assert reopened["title"] == "What does HTTP stand for?"


def test_custom_title_survives_a_later_message(monkeypatch):
    client, _captured = _client(monkeypatch)
    conversation_id = client.post("/conversations").json()["id"]
    client.patch(f"/conversations/{conversation_id}", json={"title": "Kept title"})

    response = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"message": "Hello"},
    )
    assert response.json()["conversation"]["title"] == "Kept title"


def test_history_persists_in_the_same_database(monkeypatch):
    database = mongomock.MongoClient()["switchboard"]
    first_store = MongoConversationStore(database)
    client, _captured = _client(monkeypatch, first_store)
    conversation_id = client.post("/conversations").json()["id"]
    client.post(
        f"/conversations/{conversation_id}/messages",
        json={"message": "Persist this"},
    )

    reopened = MongoConversationStore(database).get_conversation(conversation_id)
    assert reopened is not None
    assert reopened["messages"][0]["content"] == "Persist this"
    assert reopened["messages"][1]["details"]["complexity"] == "simple"


def test_missing_mongo_configuration_returns_503(monkeypatch):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    conversations_api.set_conversation_store(None)
    app = FastAPI()
    app.include_router(conversations_api.router, prefix="/conversations")
    client = TestClient(app)

    response = client.get("/conversations")

    assert response.status_code == 503
    assert "MONGODB_URI" in response.json()["detail"]
