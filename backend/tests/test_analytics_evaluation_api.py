import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import evaluation as evaluation_api
from app.api.evaluation import router as evaluation_router
from app.api.metrics import router as metrics_router
from app.database.database import Base
from app.database.models import RequestLog
from app.services import metrics_service


api_app = FastAPI()
api_app.include_router(metrics_router, prefix="/metrics")
api_app.include_router(evaluation_router, prefix="/evaluation")


@pytest.fixture
def isolated_database(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(metrics_service, "SessionLocal", factory)
    monkeypatch.setattr(
        metrics_service,
        "initialize_database",
        lambda: Base.metadata.create_all(engine),
    )
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_analytics_aggregates_persisted_request_measurements(isolated_database):
    now = datetime.now(timezone.utc)
    rows = [
        RequestLog(
            timestamp=now,
            query="successful",
            selected_model="cheap",
            final_model="strong",
            completed=True,
            cache_hit=True,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            latency_ms=100,
            estimated_cost=0.25,
            context_before_tokens=100,
            context_after_tokens=40,
            escalated=True,
        ),
        RequestLog(
            timestamp=now - timedelta(days=1),
            query="failed",
            selected_model="cheap",
            completed=False,
            cache_hit=False,
            input_tokens=20,
            output_tokens=10,
            latency_ms=300,
            fallback_used=True,
            context_before_tokens=200,
            context_after_tokens=160,
        ),
        RequestLog(timestamp=now, query="outcome unknown"),
        RequestLog(
            timestamp=now - timedelta(days=45),
            query="old",
            selected_model="local",
            completed=None,
        ),
    ]
    with isolated_database() as session:
        session.add_all(rows)
        session.commit()

    response = TestClient(api_app).get("/metrics/analytics")
    assert response.status_code == 200
    assert response.json() == {
        "total_requests": 4,
        "successful_requests": 1,
        "failed_requests": 1,
        "unknown_outcome_requests": 2,
        "cache_hits": 1,
        "cache_misses": 1,
        "cache_hit_rate": 0.5,
        "model_usage": {"strong": 1, "cheap": 1, "local": 1},
        "tokens_input": 120,
        "tokens_output": 60,
        "tokens_total": 180,
        "average_latency_ms": 200,
        "estimated_cost_total": 0.25,
        "escalations": 1,
        "fallbacks": 1,
        "context_requests": 2,
        "context_tokens_before": 300,
        "context_tokens_after": 200,
        "context_tokens_saved": 100,
        "context_reduction_percent": pytest.approx(100 / 3),
        "trend": [
            {
                "date": (now - timedelta(days=1)).date().isoformat(),
                "requests": 1,
                "successful_requests": 0,
                "failed_requests": 1,
                "tokens": 30,
            },
            {
                "date": now.date().isoformat(),
                "requests": 2,
                "successful_requests": 1,
                "failed_requests": 0,
                "tokens": 150,
            },
        ],
    }


def test_analytics_empty_history_keeps_unmeasured_fields_unavailable(isolated_database):
    response = TestClient(api_app).get("/metrics/analytics")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_requests"] == 0
    assert payload["successful_requests"] == payload["failed_requests"] == 0
    assert payload["cache_hit_rate"] is None
    assert payload["tokens_total"] is None
    assert payload["average_latency_ms"] is None
    assert payload["estimated_cost_total"] is None
    assert payload["context_reduction_percent"] is None
    assert payload["trend"] == []


def test_analytics_rejects_invalid_trend_window(isolated_database):
    response = TestClient(api_app).get("/metrics/analytics?days=0")
    assert response.status_code == 422


def test_metrics_recent_and_lookup_routes_remain_compatible(isolated_database):
    record = metrics_service.log_request({"query": "existing API"})
    client = TestClient(api_app)
    assert client.get("/metrics/recent").json()[0]["id"] == record.id
    assert client.get(f"/metrics/{record.id}").json()["query"] == "existing API"
    assert client.get("/metrics").status_code == 200


def test_evaluation_results_returns_saved_report_or_empty(isolated_database, tmp_path, monkeypatch):
    report_path = tmp_path / "evaluation_report.json"
    monkeypatch.setattr(evaluation_api, "REPORT_PATH", report_path)
    client = TestClient(api_app)

    empty = client.get("/evaluation/results")
    assert empty.status_code == 200
    assert empty.json() == {"available": False, "report": None}

    report = {"decision_model": "test", "count": 10}
    report_path.write_text(json.dumps(report), encoding="utf-8")
    saved = client.get("/evaluation/results")
    assert saved.status_code == 200
    assert saved.json() == {"available": True, "report": report}


def test_evaluation_results_surfaces_malformed_saved_report(tmp_path, monkeypatch):
    report_path = tmp_path / "evaluation_report.json"
    report_path.write_text("{", encoding="utf-8")
    monkeypatch.setattr(evaluation_api, "REPORT_PATH", report_path)
    response = TestClient(api_app).get("/evaluation/results")
    assert response.status_code == 500
    assert response.json()["detail"] == "Saved evaluation report is unreadable."


def test_evaluation_run_returns_saved_runner_output(monkeypatch):
    report = {"decision_model": "test", "count": 7}
    monkeypatch.setattr(evaluation_api, "_run_evaluation", lambda: report)
    response = TestClient(api_app).post("/evaluation/run")
    assert response.status_code == 200
    assert response.json() == report


def test_evaluation_run_prevents_duplicate_and_explains_missing_predictions(monkeypatch):
    client = TestClient(api_app)
    assert evaluation_api._run_lock.acquire(blocking=False)
    try:
        duplicate = client.post("/evaluation/run")
    finally:
        evaluation_api._run_lock.release()
    assert duplicate.status_code == 409

    def missing_predictions():
        raise SystemExit("No raw predictions found.")

    monkeypatch.setattr(evaluation_api, "_run_evaluation", missing_predictions)
    missing = client.post("/evaluation/run")
    assert missing.status_code == 409
    assert missing.json()["detail"] == "No raw predictions found."


def test_generation_metrics_persists_completed_outcome(isolated_database):
    record = metrics_service.log_request({"query": "timed out"})
    assert metrics_service.record_generation_metrics(
        record.id,
        latency_ms=12.5,
        completed=False,
    )
    stored = metrics_service.get_request(record.id)
    assert stored is not None
    assert stored.completed is False
    assert stored.latency_ms == 12.5
