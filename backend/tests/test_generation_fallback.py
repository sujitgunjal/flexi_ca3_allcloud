from types import SimpleNamespace

import pytest


def _completion_response(text="ok"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2),
    )


def test_cloud_success_and_configured_timeout_reach_litellm(monkeypatch):
    import app.providers as providers
    import app.providers.litellm_client as client

    calls = []
    monkeypatch.setattr(providers, "PROVIDER_TIMEOUT_SECONDS", 4.25)
    monkeypatch.setattr(client, "completion", lambda **kwargs: calls.append(kwargs) or _completion_response())

    result = providers.generate_response("strong", "question")

    assert result["response"] == "ok"
    assert result["output_tokens"] == 2
    assert calls[0]["timeout"] == 4.25
    assert calls[0]["num_retries"] == 0
    assert calls[0]["stream"] is False
    assert calls[0]["api_base"].startswith("https://")


def test_tier_labels_resolve_to_configured_providers_and_models():
    from app.providers.config import (
        CHEAP_MODEL,
        NVIDIA_API_BASE,
        OLLAMA_API_BASE,
        OLLAMA_MODEL,
        STRONG_MODEL,
    )
    from app.providers.registry import get_tier

    local = get_tier("local")
    cheap = get_tier("cheap")
    strong = get_tier("strong")

    assert (local.provider, local.model) == ("ollama", OLLAMA_MODEL)
    assert local.api_base == OLLAMA_API_BASE
    assert cheap.provider == "nvidia"
    assert cheap.model == CHEAP_MODEL
    assert cheap.api_base == NVIDIA_API_BASE
    assert strong.provider == "nvidia"
    assert strong.model == STRONG_MODEL
    assert strong.api_base == NVIDIA_API_BASE


def test_cheap_fallback_invocation_also_gets_configured_timeout(monkeypatch):
    import app.providers as providers
    import app.providers.litellm_client as client

    calls = []
    monkeypatch.setattr(providers, "PROVIDER_TIMEOUT_SECONDS", 3)
    monkeypatch.setattr(client, "completion", lambda **kwargs: calls.append(kwargs) or _completion_response())
    providers.generate_response("cheap", "question")

    assert calls[0]["timeout"] == 3
    assert calls[0]["num_retries"] == 0


def test_strong_timeout_falls_back_to_cheap(monkeypatch):
    import app.agents.generate_agent as agent_module

    calls = []
    def generate_response(model, **_kwargs):
        calls.append(model)
        if model == "strong":
            raise TimeoutError("provider timed out")
        return {"response": "fallback answer"}

    monkeypatch.setattr(agent_module, "generate_response", generate_response)
    state = agent_module.GenerateAgent().run({"selected_model": "strong", "query": "q"})
    assert calls == ["strong", "cheap"]
    assert state["response"] == "fallback answer"
    assert state["actual_model"] == "cheap"
    assert state["fallback_used"] is True
    assert state["escalation_attempted"] is False


def test_strong_and_cheap_timeouts_fall_back_to_local(monkeypatch):
    import app.agents.generate_agent as agent_module

    calls = []

    def generate_response(model, **_kwargs):
        calls.append(model)
        if model in {"strong", "cheap"}:
            raise TimeoutError("remote provider timeout")
        return {"response": "local answer"}

    monkeypatch.setattr(agent_module, "generate_response", generate_response)
    state = agent_module.GenerateAgent().run({"selected_model": "strong", "query": "q"})
    assert calls == ["strong", "cheap", "local"]
    assert state["response"] == "local answer"
    assert state["actual_model"] == "local"
    assert state["fallback_used"] is True
    assert state["escalation_attempted"] is False


def test_strong_provider_error_falls_back_to_cheap(monkeypatch):
    import app.agents.generate_agent as agent_module

    calls = []
    def generate_response(model, **_kwargs):
        calls.append(model)
        if model == "strong":
            raise RuntimeError("provider unavailable")
        return {"response": "fallback answer"}

    monkeypatch.setattr(agent_module, "generate_response", generate_response)
    state = agent_module.GenerateAgent().run({"selected_model": "strong", "query": "q"})
    assert calls == ["strong", "cheap"]
    assert state["fallback_used"] is True


@pytest.mark.parametrize("failure", [TimeoutError("timeout"), RuntimeError("provider error")])
def test_cheap_failure_uses_strong_then_local_when_remote_attempts_fail(
    monkeypatch, failure
):
    import app.agents.generate_agent as agent_module

    calls = []

    def generate_response(model, **_kwargs):
        calls.append(model)
        if model == "cheap":
            raise failure
        if model == "strong":
            raise TimeoutError("remote provider unavailable")
        return {"response": "local answer"}

    monkeypatch.setattr(agent_module, "generate_response", generate_response)
    state = agent_module.GenerateAgent().run({"selected_model": "cheap", "query": "q"})
    assert calls == ["cheap", "strong", "local"]
    assert state["response"] == "local answer"
    assert state["actual_model"] == "local"
    assert state["fallback_used"] is True


def test_primary_and_fallback_errors_propagate_without_retry(monkeypatch):
    import app.agents.generate_agent as agent_module

    calls = []
    def fail(model, **_kwargs):
        calls.append(model)
        raise TimeoutError("bounded provider timeout")

    monkeypatch.setattr(agent_module, "generate_response", fail)
    with pytest.raises(TimeoutError):
        agent_module.GenerateAgent().run({"selected_model": "strong", "query": "q"})
    assert calls == ["strong", "cheap", "local"]


def test_local_generation_uses_ollama_timeout_and_override(monkeypatch):
    import app.providers as providers
    import app.providers.ollama as ollama

    calls = []
    monkeypatch.setattr(ollama, "completion", lambda **kwargs: calls.append(kwargs) or _completion_response("local answer"))
    monkeypatch.setattr(providers, "OLLAMA_TIMEOUT_SECONDS", 31)

    result = providers.generate_response("local", "question")
    assert result["response"] == "local answer"
    assert calls[0]["model"].startswith("ollama/")
    assert calls[0]["api_base"] == ollama.OLLAMA_API_BASE
    assert calls[0]["timeout"] == 31
    assert calls[0]["stream"] is False

    providers.generate_response("local", "question", timeout=2)
    assert calls[1]["timeout"] == 2


def test_chat_returns_controlled_502_when_generation_and_fallback_fail(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import chat as chat_api

    monkeypatch.setattr(chat_api, "log_request", lambda _metrics: SimpleNamespace(id=1))
    monkeypatch.setattr(chat_api, "record_generation_metrics", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat_api.llm_graph, "invoke", lambda _state: (_ for _ in ()).throw(RuntimeError("internal failure")))
    app = FastAPI()
    app.include_router(chat_api.router, prefix="/chat")

    response = TestClient(app).post("/chat", json={"message": "question"})
    assert response.status_code == 502
    assert response.json()["detail"] == "LLM provider or orchestration error"
    assert "internal failure" not in response.text


def test_chat_returns_success_when_local_fallback_succeeds(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import chat as chat_api

    class TestCache:
        def set(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(chat_api, "cache", TestCache())
    monkeypatch.setattr(chat_api, "log_request", lambda _metrics: SimpleNamespace(id=1))
    recorded = []
    monkeypatch.setattr(chat_api, "record_generation_metrics", lambda *_args, **kwargs: recorded.append(kwargs))
    monkeypatch.setattr(
        chat_api.llm_graph,
        "invoke",
        lambda _state: {
            "selected_model": "strong",
            "actual_model": "local",
            "fallback_used": True,
            "response": "Local fallback answer",
            "decision": {},
            "complexity": "complex",
            "uncertain": False,
            "routing_reason": "NVIDIA tiers failed; local succeeded",
        },
    )
    app = FastAPI()
    app.include_router(chat_api.router, prefix="/chat")

    response = TestClient(app).post("/chat", json={"message": "question"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["message"] == "Local fallback answer"
    assert recorded[0]["selected_model"] == "strong"
    assert recorded[0]["final_model"] == "local"
    assert recorded[0]["fallback_used"] is True
    assert recorded[0]["escalated"] is False


def test_chat_quality_escalation_records_final_tier_without_fallback(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import chat as chat_api

    class TestCache:
        def set(self, *_args, **_kwargs):
            return None

    recorded = []
    monkeypatch.setattr(chat_api, "cache", TestCache())
    monkeypatch.setattr(chat_api, "log_request", lambda _metrics: SimpleNamespace(id=1))
    monkeypatch.setattr(chat_api, "record_generation_metrics", lambda *_args, **kwargs: recorded.append(kwargs))
    monkeypatch.setattr(chat_api, "record_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        chat_api.llm_graph,
        "invoke",
        lambda _state: {
            "selected_model": "strong",
            "initial_selected_model": "cheap",
            "actual_model": "strong",
            "escalation_attempted": True,
            "fallback_used": False,
            "response": "Escalated answer",
            "decision": {},
            "complexity": "medium",
            "uncertain": False,
            "routing_reason": "Quality escalation succeeded",
        },
    )
    app = FastAPI()
    app.include_router(chat_api.router, prefix="/chat")

    response = TestClient(app).post("/chat", json={"message": "question"})

    assert response.status_code == 200
    assert recorded[0]["selected_model"] == "cheap"
    assert recorded[0]["final_model"] == "strong"
    assert recorded[0]["escalated"] is True
    assert recorded[0]["fallback_used"] is False
