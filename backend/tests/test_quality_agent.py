import json

import pytest

from app.agents.quality_agent import QualityAgent
from app.decision.providers.ollama_provider import OllamaDecisionProvider
from app.orchestration.graph import prepare_escalation, route_after_quality
from app.providers.config import OLLAMA_MODEL
from app.quality.escalation import next_stronger_tier
from app.quality.ollama_evaluator import (
    DEFAULT_QUALITY_OLLAMA_MODEL,
    OllamaQualityEvaluator,
)
from app.quality.service import QualityService


class ScriptedEvaluator:
    name = "scripted"

    def __init__(self, text: str):
        self.text = text
        self.calls = 0

    def evaluate_raw(self, query: str, response: str, *, correction: str | None = None) -> str:
        self.calls += 1
        return self.text


def _decision(relevant: str, complete: str, escalate: str) -> str:
    return json.dumps(
        {
            "relevant": {"decision": relevant, "reason": f"Relevance is {relevant}."},
            "complete": {"decision": complete, "reason": f"Completeness is {complete}."},
            "escalate": {"decision": escalate, "reason": f"Escalation is {escalate}."},
        }
    )


def _run(text: str, response: str = "A useful answer.") -> dict:
    agent = QualityAgent(QualityService(ScriptedEvaluator(text)))
    return agent.run({"query": "Explain the request.", "response": response})


def test_relevant_response_is_accepted():
    state = _run(_decision("YES", "YES", "NO"))

    assert state["quality_relevant"] == "YES"
    assert state["quality_complete"] == "YES"
    assert state["escalation"] is False
    assert state["quality_score"] == 0.9


def test_irrelevant_response_is_marked_no():
    state = _run(_decision("NO", "NO", "YES"))

    assert state["quality_relevant"] == "NO"
    assert "Relevance is NO" in state["quality_reason"]


def test_complete_response_keeps_complete_yes():
    state = _run(_decision("YES", "YES", "NO"))

    assert state["quality_complete"] == "YES"


def test_incomplete_response_is_marked_no():
    state = _run(_decision("YES", "NO", "YES"))

    assert state["quality_complete"] == "NO"
    assert state["quality_relevant"] == "YES"
    assert state["escalation"] is True


def test_escalation_moves_to_the_next_stronger_model(monkeypatch):
    monkeypatch.setenv("QUALITY_MAX_ESCALATIONS", "1")
    state = _run(_decision("NO", "NO", "YES"))
    state["actual_model"] = "local"
    state["selected_model"] = "local"
    state["initial_selected_model"] = "cheap"

    assert route_after_quality(state) == "escalate"
    prepared = prepare_escalation(state)

    assert prepared["selected_model"] == "cheap"
    assert prepared["initial_selected_model"] == "cheap"
    assert prepared["quality_escalation_count"] == 1
    assert prepared["escalation_attempted"] is True
    assert route_after_quality(prepared) == "end"


def test_escalation_captures_initial_tier_before_retry_changes_selected_model():
    state = {
        "selected_model": "cheap",
        "actual_model": "cheap",
        "escalation": True,
        "quality_escalation_count": 0,
    }

    prepared = prepare_escalation(state)

    assert prepared["initial_selected_model"] == "cheap"
    assert prepared["selected_model"] == "strong"
    assert prepared["escalation_attempted"] is True


def test_escalation_stops_at_the_retry_limit(monkeypatch):
    monkeypatch.setenv("QUALITY_MAX_ESCALATIONS", "1")
    state = {
        "escalation": True,
        "actual_model": "cheap",
        "selected_model": "cheap",
        "quality_escalation_count": 1,
    }

    assert route_after_quality(state) == "end"


def test_escalation_stops_when_no_stronger_model_exists():
    state = {
        "escalation": True,
        "actual_model": "strong",
        "quality_escalation_count": 0,
    }

    assert next_stronger_tier("local") == "cheap"
    assert next_stronger_tier("cheap") == "strong"
    assert next_stronger_tier("strong") is None
    assert route_after_quality(state) == "end"


def test_malformed_evaluation_does_not_escalate():
    state = _run("this is not json")

    assert state["escalation"] is False
    assert state["quality_evaluation"]["output_valid"] is False
    assert 0.0 <= state["quality_score"] <= 1.0


def test_quality_model_uses_quality_ollama_model_only(monkeypatch):
    monkeypatch.setenv("QUALITY_OLLAMA_MODEL", "gemma4:31b-cloud")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3:8b")

    assert OllamaQualityEvaluator().model_name == "gemma4:31b-cloud"
    assert OLLAMA_MODEL == "llama3:8b"


def test_quality_model_does_not_follow_ollama_model(monkeypatch):
    monkeypatch.delenv("QUALITY_OLLAMA_MODEL", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "llama3:8b")

    assert OllamaQualityEvaluator().model_name == DEFAULT_QUALITY_OLLAMA_MODEL
    assert DEFAULT_QUALITY_OLLAMA_MODEL == "gemma4:31b-cloud"


def test_quality_request_sends_the_quality_model(monkeypatch):
    monkeypatch.setenv("QUALITY_OLLAMA_MODEL", "gemma4:31b-cloud")
    captured = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"message":{"content":"{}"}}'

    def _urlopen(request, timeout=0):
        captured["body"] = json.loads(request.data.decode())
        return _Response()

    monkeypatch.setattr(
        "app.quality.ollama_evaluator.urllib.request.urlopen",
        _urlopen,
    )
    OllamaQualityEvaluator().evaluate_raw("What does HTTP stand for?", "A definition.")

    assert captured["body"]["model"] == "gemma4:31b-cloud"


def test_quality_request_uses_configured_finite_timeout(monkeypatch):
    from app.quality import ollama_evaluator
    from app.quality.base import QualityEvaluatorError

    monkeypatch.setattr(ollama_evaluator, "QUALITY_TIMEOUT_SECONDS", 17.5)
    captured = {}

    def _urlopen(_request, timeout=0):
        captured["timeout"] = timeout
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr(
        "app.quality.ollama_evaluator.urllib.request.urlopen",
        _urlopen,
    )
    with pytest.raises(QualityEvaluatorError):
        OllamaQualityEvaluator().evaluate_raw("question", "answer")

    assert captured["timeout"] == 17.5


def test_quality_timeout_becomes_invalid_quality_result_not_request_failure():
    from app.quality.base import QualityEvaluatorError

    class TimedOutEvaluator:
        name = "ollama"

        def evaluate_raw(self, *_args, **_kwargs):
            raise QualityEvaluatorError("quality provider timed out")

    result = QualityService(TimedOutEvaluator()).evaluate("question", "answer")
    assert result.output_valid is False
    assert result.escalation_required is False


def test_complexity_model_ignores_quality_ollama_model(monkeypatch):
    monkeypatch.setenv("QUALITY_OLLAMA_MODEL", "gemma4:31b-cloud")
    monkeypatch.delenv("DECISION_OLLAMA_MODEL", raising=False)

    assert OLLAMA_MODEL == "llama3:8b"
    assert OllamaDecisionProvider().model_name == "llama3:8b"


def test_decision_model_env_does_not_change_generation_or_quality_model(monkeypatch):
    monkeypatch.setenv("DECISION_OLLAMA_MODEL", "gemma4:31b-cloud")
    monkeypatch.setenv("QUALITY_OLLAMA_MODEL", "gemma4:31b-cloud")

    assert OllamaDecisionProvider().model_name == "gemma4:31b-cloud"
    assert OllamaQualityEvaluator().model_name == "gemma4:31b-cloud"
    assert OLLAMA_MODEL == "llama3:8b"


def test_empty_response_asks_for_one_escalation():
    state = _run(_decision("YES", "YES", "NO"), response="   ")

    assert state["quality_relevant"] == "NO"
    assert state["quality_complete"] == "NO"
    assert state["quality_escalate"] == "YES"
    assert state["escalation"] is True
