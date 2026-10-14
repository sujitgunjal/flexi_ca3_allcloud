
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from math import inf, nan
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.api.metrics import router as metrics_router
from app.schemas.metrics import RequestMetrics
from app.services import metrics_service
from app.services.cost_service import MODEL_PRICING, calculate_cost


metrics_app = FastAPI()
metrics_app.include_router(metrics_router, prefix="/metrics")


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

    from app.services import trace_service

    monkeypatch.setattr(trace_service, "SessionLocal", factory)
    monkeypatch.setattr(
        trace_service,
        "initialize_database",
        lambda: Base.metadata.create_all(engine),
    )

    yield engine

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_metrics_validation_and_optional_fields():
    early = RequestMetrics(
        query=" Explain Docker ",
        complexity="medium",
        selected_model="cheap",
    )
    assert early.query == "Explain Docker"
    assert early.input_tokens is None

    with pytest.raises(ValidationError):
        RequestMetrics(query="  ")

    with pytest.raises(ValidationError):
        RequestMetrics(query="valid", input_tokens=-1)

    with pytest.raises(ValidationError):
        RequestMetrics(query="valid", quality_score=6)

    with pytest.raises(ValidationError):
        RequestMetrics(query="valid", estimated_cost=inf)

    with pytest.raises(ValidationError):
        RequestMetrics(query="valid", context_reduction_percent=nan)


@pytest.mark.parametrize(
    "field",
    ["context_before_tokens", "context_after_tokens"],
)
def test_context_token_counts_must_be_non_negative(field):
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        RequestMetrics(query="valid", **{field: -1})


def test_derived_metrics_and_context_counts_are_source_of_truth():
    derived = metrics_service.derive_metrics(
        RequestMetrics(
            query="usage",
            input_tokens=100,
            output_tokens=50,
            context_before_tokens=1000,
            context_after_tokens=400,
        )
    )
    assert derived.total_tokens == 150
    assert derived.context_reduction_percent == 60

    explicit = metrics_service.derive_metrics(
        RequestMetrics(
            query="explicit",
            input_tokens=100,
            output_tokens=50,
            total_tokens=123,
            context_before_tokens=1000,
            context_after_tokens=400,
            context_reduction_percent=42,
        )
    )
    assert explicit.total_tokens == 123
    assert explicit.context_reduction_percent == 60


def test_context_reduction_zero_before_is_safe():
    result = metrics_service.derive_metrics(
        RequestMetrics(
            query="zero",
            context_before_tokens=0,
            context_after_tokens=0,
        )
    )
    assert result.context_reduction_percent is None


@pytest.mark.parametrize(
    "before,after,expected",
    [
        (5000, 1500, 70.0),
        (1000, 400, 60.0),
        (100, 100, 0.0),
        (100, 0, 100.0),
        (None, 0, None),
        (0, 0, None),
    ],
)
def test_calculate_context_reduction(before, after, expected):
    assert metrics_service.calculate_context_reduction(before, after) == expected


@pytest.mark.parametrize(
    "before,after",
    [(-1, 0), (1, -1), (100, 101)],
)
def test_calculate_context_reduction_rejects_invalid_counts(before, after):
    with pytest.raises(ValueError, match="non-negative|cannot exceed"):
        metrics_service.calculate_context_reduction(before, after)


def test_cost_utility_and_explicit_estimate():
    MODEL_PRICING["test-model"] = {"input": 1.0, "output": 2.0}

    try:
        assert calculate_cost("test-model", 1_000_000, 500_000) == 2.0
        assert calculate_cost("unconfigured", 1, 1) is None
    finally:
        MODEL_PRICING.pop("test-model")

    derived = metrics_service.derive_metrics(
        RequestMetrics(
            query="explicit cost",
            selected_model="cheap",
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.123,
        )
    )
    assert derived.estimated_cost == 0.123

    unknown = metrics_service.derive_metrics(
        RequestMetrics(
            query="unknown",
            selected_model="unconfigured",
            input_tokens=1,
            output_tokens=1,
        )
    )
    assert unknown.estimated_cost is None


def test_database_logging_retrieval_and_aggregation(isolated_database):
    with metrics_service.SessionLocal() as session:
        first = metrics_service.log_request(
            {
                "query": "one",
                "selected_model": "cheap",
                "input_tokens": 100,
                "output_tokens": 50,
                "latency_ms": 100,
                "estimated_cost": 0.01,
                "cache_hit": True,
                "quality_score": 0.8,
                "escalated": False,
                "fallback_used": False,
            },
            session=session,
        )
        first_id = first.id

        metrics_service.log_request(
            {
                "query": "two",
                "final_model": "strong",
                "total_tokens": 300,
                "latency_ms": 300,
                "estimated_cost": 0.03,
                "cache_hit": False,
                "quality_score": 0.4,
                "escalated": True,
                "fallback_used": True,
            },
            session=session,
        )

        metrics_service.log_request(
            {"query": "three", "cache_hit": None},
            session=session,
        )

    retrieved = metrics_service.get_request(first_id)
    assert retrieved is not None
    assert retrieved.total_tokens == 150

    assert [
        row.query for row in metrics_service.get_recent_requests()
    ] == ["three", "two", "one"]

    summary = metrics_service.get_summary_metrics()

    assert summary == {
        "total_requests": 3,
        "total_tokens": 450,
        "average_latency_ms": 200,
        "average_cost": 0.02,
        "cache_hits": 1,
        "cache_hit_rate": 1 / 3,
        "average_quality_score": pytest.approx(0.6),
        "escalation_count": 1,
        "completed_eligible_requests": 0,
        "escalation_rate": 0,
        "escalation_success_rate": 0,
        "escalation_success_eligible_attempts": 0,
        "fallback_count": 1,
        "model_usage_count": {"cheap": 1, "strong": 1},
        "requests": {"total": 3},
        "cache": {
            "hits": 1,
            "misses": 1,
            "hit_rate": 1 / 3,
            "api_calls_avoided": 1,
            "estimated_cost_saved": 0.01,
        },
        "tokens": {
            "input": 100,
            "output": 50,
            "total": 450,
            "average_input": 100 / 3,
            "average_output": 50 / 3,
            "average_total": 150,
            "token_reduction_percent": None,
        },
        "latency": {"average_ms": 200.0},
        "cost": {
            "total": 0.04,
            "average_per_request": 0.02,
            "by_model": {"cheap": 0.01, "strong": 0.03},
            "cache_miss_cost": 0.03,
            "estimated_saved": 0.01,
            "cost_reduction_percent": None,
        },
        "models": {
            "usage_counts": {"cheap": 1, "strong": 1},
            "usage_percentages": {
                "cheap": 1 / 3 * 100,
                "strong": 1 / 3 * 100,
            },
        },
        "context": {
            "requests_with_metrics": 0,
            "total_original_tokens": 0,
            "total_optimized_tokens": 0,
            "total_tokens_saved": 0,
            "average_original_tokens": 0,
            "average_optimized_tokens": 0,
            "overall_reduction_percent": None,
            "average_per_request_reduction_percent": None,
        },
    }


def test_empty_summary(isolated_database):
    assert metrics_service.get_summary_metrics() == {
        "total_requests": 0,
        "total_tokens": 0,
        "average_latency_ms": 0,
        "average_cost": 0,
        "cache_hits": 0,
        "cache_hit_rate": 0,
        "average_quality_score": None,
        "escalation_count": 0,
        "completed_eligible_requests": 0,
        "escalation_rate": 0,
        "escalation_success_rate": 0,
        "escalation_success_eligible_attempts": 0,
        "fallback_count": 0,
        "model_usage_count": {},
        "requests": {"total": 0},
        "cache": {
            "hits": 0,
            "misses": 0,
            "hit_rate": 0,
            "api_calls_avoided": 0,
            "estimated_cost_saved": 0.0,
        },
        "tokens": {
            "input": 0,
            "output": 0,
            "total": 0,
            "average_input": 0,
            "average_output": 0,
            "average_total": 0,
            "token_reduction_percent": None,
        },
        "latency": {"average_ms": 0},
        "cost": {
            "total": 0,
            "average_per_request": 0,
            "by_model": {},
            "cache_miss_cost": 0,
            "estimated_saved": 0.0,
            "cost_reduction_percent": None,
        },
        "models": {"usage_counts": {}, "usage_percentages": {}},
        "context": {
            "requests_with_metrics": 0,
            "total_original_tokens": 0,
            "total_optimized_tokens": 0,
            "total_tokens_saved": 0,
            "average_original_tokens": 0,
            "average_optimized_tokens": 0,
            "overall_reduction_percent": None,
            "average_per_request_reduction_percent": None,
        },
    }


def test_escalation_rates_use_only_completed_and_determinate_outcomes(
    isolated_database,
):
    outcomes = [
        # completed non-escalated: enters rate denominator only
        {"completed": True, "escalated": False, "quality_status": "pass"},
        # completed escalation pass
        {"completed": True, "escalated": True, "quality_status": "pass"},
        # completed escalation fail
        {"completed": True, "escalated": True, "quality_status": "fail"},
        # invalid evaluator result is indeterminate and excluded from success
        {"completed": True, "escalated": True, "quality_status": "indeterminate"},
        # missing/pending final quality is also excluded
        {"completed": True, "escalated": True, "quality_status": None},
        # failed request and legacy record are not eligible
        {"completed": False, "escalated": True, "quality_status": "fail"},
        {"completed": None, "escalated": True, "quality_status": "pass"},
    ]
    for index, outcome in enumerate(outcomes):
        metrics_service.log_request({"query": f"outcome {index}", **outcome})

    summary = metrics_service.get_summary_metrics()
    assert summary["completed_eligible_requests"] == 5
    assert summary["escalation_rate"] == 4 / 5
    assert summary["escalation_success_eligible_attempts"] == 2
    assert summary["escalation_success_rate"] == 1 / 2


def test_metrics_api_exposes_model_and_escalation_contract(isolated_database):
    client = TestClient(metrics_app)
    response = client.post(
        "/metrics/log",
        json={
            "query": "tracked",
            "selected_model": "cheap",
            "final_model": "strong",
            "completed": True,
            "escalated": True,
            "fallback_used": False,
            "quality_status": "pass",
        },
    )
    assert response.status_code == 201
    request_id = response.json()["request_id"]
    record = client.get(f"/metrics/{request_id}").json()
    assert (record["selected_model"], record["final_model"]) == ("cheap", "strong")
    assert record["escalated"] is True
    assert record["fallback_used"] is False
    summary = client.get("/metrics/summary").json()
    assert summary["completed_eligible_requests"] == 1
    assert summary["escalation_rate"] == 1.0
    assert summary["escalation_success_eligible_attempts"] == 1
    assert summary["escalation_success_rate"] == 1.0


def test_metrics_api_log_recent_lookup_and_validation(
    isolated_database, monkeypatch
):
    client = TestClient(metrics_app)

    body = {
        "query": "Explain Docker",
        "complexity": "simple",
        "selected_model": "cheap",
        "input_tokens": 100,
        "output_tokens": 150,
        "latency_ms": 500,
        "cache_hit": False,
    }

    response = client.post("/metrics/log", json=body)
    assert response.status_code == 201

    logged = response.json()
    assert logged["success"] is True
    request_id = logged["request_id"]

    assert client.get("/metrics/recent").json()[0]["id"] == request_id
    assert client.get(f"/metrics/{request_id}").json()["total_tokens"] == 250
    assert client.get(
        f"/metrics/{request_id}"
    ).json()["context_before_tokens"] is None
    assert client.get("/metrics").json()["total_requests"] == 1
    assert client.get("/metrics/99999").status_code == 404

    assert client.post(
        "/metrics/log",
        json={"query": "bad", "input_tokens": -2},
    ).status_code == 422

    assert client.post(
        "/metrics/log",
        json={"query": "negative original", "context_before_tokens": -1},
    ).status_code == 422

    assert client.post(
        "/metrics/log",
        json={"query": "negative optimized", "context_after_tokens": -1},
    ).status_code == 422

    assert client.post(
        "/metrics/log",
        json={
            "query": "expanded",
            "context_before_tokens": 10,
            "context_after_tokens": 11,
        },
    ).status_code == 422

    context_response = client.post(
        "/metrics/log",
        json={
            "query": "context",
            "context_before_tokens": 5000,
            "context_after_tokens": 1500,
            "context_reduction_percent": 12,
        },
    )
    assert context_response.status_code == 201

    context_id = context_response.json()["request_id"]
    retrieved_context = client.get(f"/metrics/{context_id}").json()

    assert (
        retrieved_context["context_before_tokens"],
        retrieved_context["context_after_tokens"],
        retrieved_context["context_reduction_percent"],
    ) == (5000, 1500, 70)

    summary_context = client.get("/metrics/summary").json()["context"]
    assert summary_context["requests_with_metrics"] == 1
    assert summary_context["total_tokens_saved"] == 3500


def test_context_event_and_analytics(isolated_database):
    first = metrics_service.log_request({"query": "a"})
    metrics_service.log_request(
        {
            "query": "b",
            "context_before_tokens": 1000,
            "context_after_tokens": 400,
            "context_reduction_percent": 1,
        }
    )

    assert metrics_service.record_context_event(first.id, 5000, 1500, 12)
    assert metrics_service.get_request(first.id).context_reduction_percent == 70

    context = metrics_service.get_summary_metrics()["context"]
    assert context == {
        "requests_with_metrics": 2,
        "total_original_tokens": 6000,
        "total_optimized_tokens": 1900,
        "total_tokens_saved": 4100,
        "average_original_tokens": 3000,
        "average_optimized_tokens": 950,
        "overall_reduction_percent": 68.33333333333333,
        "average_per_request_reduction_percent": 65.0,
    }


def test_cache_metrics_and_cost_savings(isolated_database):
    for index in range(10):
        record = metrics_service.log_request(
            {
                "query": str(index),
                "selected_model": "cheap-model",
                "input_tokens": 100,
                "output_tokens": 50,
                "estimated_cost": 0.01,
            }
        )
        metrics_service.record_cache_event(
            record.id,
            index < 3,
            cache_key=f"key-{index}",
            lookup_latency_ms=1.5,
        )

    summary = metrics_service.get_summary_metrics(
        baseline_tokens=2000,
        baseline_cost=0.2,
    )
    assert summary["cache"]["hits"] == 3
    assert summary["cache"]["misses"] == 7
    assert summary["cache"]["hit_rate"] == 0.3
    assert summary["cache"]["api_calls_avoided"] == 3
    assert summary["cost"]["estimated_saved"] == 0.03
    assert summary["tokens"]["total"] == 1500
    assert summary["tokens"]["token_reduction_percent"] == 25
    assert summary["cost"]["cost_reduction_percent"] == 50
    assert summary["models"]["usage_counts"] == {"cheap-model": 10}
    assert summary["models"]["usage_percentages"] == {"cheap-model": 100}


def test_trace_service_chronological_metadata_and_api(isolated_database):
    from app.services import trace_service

    record = metrics_service.log_request({"query": "trace test"})
    trace_service.record_event(
        record.id, "gateway", "request_received", {"path": "/chat"}
    )
    trace_service.record_event(
        record.id, "cache", "cache_miss", {"cache_key": "abc"}
    )

    events = trace_service.get_trace(record.id)
    assert [event["event"] for event in events] == [
        "request_received",
        "cache_miss",
    ]
    assert events[1]["metadata"] == {"cache_key": "abc"}

    client = TestClient(metrics_app)
    response = client.get(f"/metrics/{record.id}/trace")
    assert response.status_code == 200
    assert response.json()[1]["stage"] == "cache"
    assert client.get("/metrics/99999/trace").status_code == 404
