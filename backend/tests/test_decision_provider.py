import json
import logging
import urllib.error

import pytest

from app.agents.decision_agent import ComplexityAgent
from app.decision.base import DecisionProviderError
from app.decision.prompts.candidate import CANDIDATE_SYSTEM_PROMPT
from app.decision.providers.ollama_provider import OllamaDecisionProvider
from app.decision.service import DecisionService


CLASSIFICATION = json.dumps(
    {
        "complexity": {"simple": 0.2, "medium": 0.3, "complex": 0.5},
        "reasoning": {"low": 0.1, "medium": 0.2, "high": 0.7},
        "context": {"low": 0.8, "medium": 0.1, "high": 0.1},
    }
)


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        body = {"message": {"content": CLASSIFICATION}}
        return json.dumps(body).encode()


def test_cloud_decision_model_uses_hosted_ollama_without_local_suffix(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "super-secret-key")
    monkeypatch.delenv("DECISION_OLLAMA_MODEL", raising=False)
    captured = {}

    def _urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode())
        return _Response()

    monkeypatch.setattr(
        "app.decision.providers.ollama_provider.urllib.request.urlopen",
        _urlopen,
    )
    provider = OllamaDecisionProvider(model="gemma4:31b-cloud")
    content = provider.classify_raw("Classify the routing task only.")

    assert content == CLASSIFICATION
    assert provider.model_name == "gemma4:31b-cloud"
    assert captured["url"] == "https://ollama.com/api/chat"
    assert "127.0.0.1" not in captured["url"]
    assert "localhost" not in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer super-secret-key"
    assert captured["body"]["model"] == "gemma4:31b"
    assert captured["body"]["format"] == "json"
    assert captured["body"]["options"]["temperature"] == 0
    assert captured["body"]["messages"][0]["content"] == CANDIDATE_SYSTEM_PROMPT
    assert captured["timeout"] == provider.timeout_seconds


def test_local_daemon_stays_in_use_when_cloud_key_is_absent(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    captured = {}

    def _urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode())
        return _Response()

    monkeypatch.setattr(
        "app.decision.providers.ollama_provider.urllib.request.urlopen",
        _urlopen,
    )
    provider = OllamaDecisionProvider(
        model="gemma4:31b-cloud",
        api_base="http://127.0.0.1:11434",
    )
    provider.classify_raw("What is HTTP?")

    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["body"]["model"] == "gemma4:31b-cloud"
    assert "Authorization" not in captured["headers"]


def test_non_cloud_model_is_not_redirected_when_api_key_is_set(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "super-secret-key")
    captured = {}

    def _urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        return _Response()

    monkeypatch.setattr(
        "app.decision.providers.ollama_provider.urllib.request.urlopen",
        _urlopen,
    )
    OllamaDecisionProvider(model="llama3:8b").classify_raw("What is HTTP?")

    assert captured["url"].startswith("http://localhost:11434/") or captured["url"].startswith(
        "http://127.0.0.1:11434/"
    )
    assert captured["body"]["model"] == "llama3:8b"


def test_unreachable_local_ollama_raises_the_url_error_chain(monkeypatch, caplog):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

    def _urlopen(_request, timeout=0):
        raise urllib.error.URLError(ConnectionRefusedError(111, "connection refused"))

    monkeypatch.setattr(
        "app.decision.providers.ollama_provider.urllib.request.urlopen",
        _urlopen,
    )
    provider = OllamaDecisionProvider(
        model="gemma4:31b-cloud",
        api_base="http://127.0.0.1:11434",
    )
    query = "unique-query-text-should-stay-out-of-logs"

    with caplog.at_level(logging.ERROR):
        with pytest.raises(DecisionProviderError) as caught:
            provider.classify_raw(query)

    assert isinstance(caught.value.__cause__, urllib.error.URLError)
    assert isinstance(caught.value.__cause__.reason, ConnectionRefusedError)
    assert "super-secret-key" not in str(caught.value)
    assert query not in str(caught.value)
    assert "stage=decision_classify" in caplog.text
    assert "reason=ConnectionRefusedError" in caplog.text
    assert query not in caplog.text

    agent = ComplexityAgent(service=DecisionService(provider=provider))
    with pytest.raises(RuntimeError) as wrapped:
        agent.run({"query": query})

    assert isinstance(wrapped.value.__cause__, DecisionProviderError)
    assert isinstance(wrapped.value.__cause__.__cause__, urllib.error.URLError)
    assert query not in str(wrapped.value)


def test_hosted_http_error_does_not_log_the_api_key(monkeypatch, caplog):
    monkeypatch.setenv("OLLAMA_API_KEY", "super-secret-key")

    def _urlopen(request, timeout=0):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(
        "app.decision.providers.ollama_provider.urllib.request.urlopen",
        _urlopen,
    )
    provider = OllamaDecisionProvider(model="gemma4:31b-cloud")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(DecisionProviderError) as caught:
            provider.classify_raw("What is HTTP?")

    assert "HTTP 401" in str(caught.value)
    assert isinstance(caught.value.__cause__, urllib.error.HTTPError)
    assert "super-secret-key" not in str(caught.value)
    assert "super-secret-key" not in caplog.text
    assert "status=401" in caplog.text


def test_chat_logs_graph_stage_without_returning_exception_text(monkeypatch, caplog):
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import chat as chat_api

    monkeypatch.setattr(chat_api, "log_request", lambda _metrics: SimpleNamespace(id=1))
    monkeypatch.setattr(chat_api, "record_generation_metrics", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat_api, "record_event", lambda *_args, **_kwargs: None)
    secret = "secret-prompt-and-database-url"
    monkeypatch.setattr(
        chat_api.llm_graph,
        "invoke",
        lambda _state: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    app = FastAPI()
    app.include_router(chat_api.router, prefix="/chat")

    with caplog.at_level(logging.ERROR):
        response = TestClient(app).post("/chat", json={"message": "question"})

    assert response.status_code == 502
    assert response.json()["detail"] == "LLM provider or orchestration error"
    assert secret not in response.text
    assert "stage=graph_invoke" in caplog.text
    assert "category=RuntimeError" in caplog.text
    assert secret not in caplog.text
