
"""Provider-independent persistence and aggregation for request metrics."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database.database import SessionLocal, initialize_database
from app.database.models import RequestLog
from app.schemas.metrics import RequestMetrics
from app.services.cost_service import calculate_cost


def calculate_context_reduction(
    original_tokens: int | None,
    optimized_tokens: int | None,
) -> float | None:
    """Calculate percent of context tokens removed; reject invalid counts."""
    if original_tokens is None or optimized_tokens is None:
        return None
    if original_tokens < 0 or optimized_tokens < 0:
        raise ValueError("Context token counts must be non-negative")
    if optimized_tokens > original_tokens:
        raise ValueError(
            "Optimized context token count cannot exceed original token count"
        )
    if original_tokens == 0:
        return None
    return ((original_tokens - optimized_tokens) / original_tokens) * 100


def derive_metrics(metrics: RequestMetrics) -> RequestMetrics:
    """Fill derived values from the available measurements."""
    values = metrics.model_dump()

    if (
        values["total_tokens"] is None
        and values["input_tokens"] is not None
        and values["output_tokens"] is not None
    ):
        values["total_tokens"] = (
            values["input_tokens"] + values["output_tokens"]
        )

    before = values["context_before_tokens"]
    after = values["context_after_tokens"]
    if before is not None and after is not None:
        values["context_reduction_percent"] = calculate_context_reduction(
            before, after
        )

    if values["estimated_cost"] is None:
        values["estimated_cost"] = calculate_cost(
            values["final_model"] or values["selected_model"],
            values["input_tokens"],
            values["output_tokens"],
        )

    return RequestMetrics.model_validate(values)


def _validated_metrics(
    metrics: RequestMetrics | Mapping[str, Any],
) -> RequestMetrics:
    if isinstance(metrics, RequestMetrics):
        return metrics
    return RequestMetrics.model_validate(metrics)


def log_request(
    metrics: RequestMetrics | Mapping[str, Any],
    *,
    session: Session | None = None,
) -> RequestLog:
    """Create an initial request log."""
    record_data = derive_metrics(_validated_metrics(metrics)).model_dump()
    initialize_database()

    owns_session = session is None
    db = session or SessionLocal()

    try:
        record = RequestLog(**record_data)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()


def record_cache_event(
    request_id: int,
    cache_hit: bool,
    cache_key: str | None = None,
    lookup_latency_ms: float | None = None,
    *,
    fallback_used: bool | None = None,
    session: Session | None = None,
) -> bool:
    """Attach cache observations to an existing request log."""
    initialize_database()
    owns_session = session is None
    db = session or SessionLocal()

    try:
        values = {
            "cache_hit": cache_hit,
            "cache_key": cache_key,
            "cache_lookup_latency_ms": lookup_latency_ms,
        }
        if fallback_used is not None:
            values["fallback_used"] = fallback_used

        result = db.execute(
            update(RequestLog)
            .where(RequestLog.id == request_id)
            .values(**values)
        )
        db.commit()
        return result.rowcount > 0
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()


def record_context_event(
    request_id: int,
    before_tokens: int,
    after_tokens: int,
    reduction_percent: float | None = None,
    *,
    session: Session | None = None,
) -> bool:
    """Store context-optimization measurements on an existing request log."""
    initialize_database()
    owns_session = session is None
    db = session or SessionLocal()

    try:
        # Recalculate the percentage from the counts to keep it consistent.
        reduction = calculate_context_reduction(before_tokens, after_tokens)

        result = db.execute(
            update(RequestLog)
            .where(RequestLog.id == request_id)
            .values(
                context_before_tokens=before_tokens,
                context_after_tokens=after_tokens,
                context_reduction_percent=(
                    reduction if reduction is not None else reduction_percent
                ),
            )
        )
        db.commit()
        return result.rowcount > 0
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()



def record_generation_metrics(
    request_id: int,
    *,
    complexity: str | None = None,
    selected_model: str | None = None,
    final_model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    quality_score: float | None = None,
    quality_status: str | None = None,
    escalated: bool | None = None,
    fallback_used: bool | None = None,
    latency_ms: float | None = None,
    estimated_cost: float | None = None,
    session: Session | None = None,
) -> bool:
    """Persist final generation, token usage, quality, latency, and cost."""
    initialize_database()
    owns_session = session is None
    db = session or SessionLocal()

    try:
        values = {
            "complexity": complexity,
            "selected_model": selected_model,
            "final_model": final_model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "quality_score": quality_score,
            "quality_status": quality_status,
            "escalated": escalated,
            "fallback_used": fallback_used,
            "latency_ms": latency_ms,
            "estimated_cost": estimated_cost,
        }

        # Don't overwrite existing values with unspecified values.
        values = {
            key: value
            for key, value in values.items()
            if value is not None
        }

        # Calculate total tokens whenever both counts are available.
        if input_tokens is not None and output_tokens is not None:
            values["total_tokens"] = input_tokens + output_tokens

        result = db.execute(
            update(RequestLog)
            .where(RequestLog.id == request_id)
            .values(**values)
        )
        db.commit()
        return result.rowcount > 0
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()



def get_recent_requests(limit: int = 100) -> list[RequestLog]:
    """Return recent request logs, newest first."""
    initialize_database()
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(RequestLog)
                .order_by(RequestLog.timestamp.desc(), RequestLog.id.desc())
                .limit(limit)
            )
        )


def get_request(request_id: int) -> RequestLog | None:
    """Fetch one request log by ID."""
    initialize_database()
    with SessionLocal() as db:
        return db.get(RequestLog, request_id)


def get_summary_metrics(
    baseline_tokens: int | None = None,
    baseline_cost: float | None = None,
) -> dict[str, Any]:
    """Aggregate available measurements, leaving unknown values unestimated."""
    initialize_database()

    with SessionLocal() as db:
        records = list(db.scalars(select(RequestLog)))

    total = len(records)
    hits = sum(record.cache_hit is True for record in records)
    misses = sum(record.cache_hit is False for record in records)

    inputs = sum(record.input_tokens or 0 for record in records)
    outputs = sum(record.output_tokens or 0 for record in records)
    tokens = sum(record.total_tokens or 0 for record in records)

    latency_values = [
        record.latency_ms
        for record in records
        if record.latency_ms is not None
    ]
    costs = [
        record.estimated_cost
        for record in records
        if record.estimated_cost is not None
    ]

    model_usage: dict[str, int] = {}
    cost_by_model: dict[str, float] = {}
    miss_cost = 0.0
    saved_cost = 0.0

    for record in records:
        model = record.final_model or record.selected_model
        if model:
            model_usage[model] = model_usage.get(model, 0) + 1
            if record.estimated_cost is not None:
                cost_by_model[model] = (
                    cost_by_model.get(model, 0.0) + record.estimated_cost
                )

        cost = record.estimated_cost
        if cost is None:
            cost = calculate_cost(
                model,
                record.input_tokens,
                record.output_tokens,
            )

        if record.cache_hit is True and cost is not None:
            saved_cost += cost
        if record.cache_hit is False and record.estimated_cost is not None:
            miss_cost += record.estimated_cost

    percentages = {
        model: count / total * 100 if total else 0
        for model, count in model_usage.items()
    }

    context_records = [
        record
        for record in records
        if record.context_before_tokens is not None
        and record.context_after_tokens is not None
        and record.context_before_tokens >= 0
        and record.context_after_tokens >= 0
        and record.context_after_tokens <= record.context_before_tokens
    ]

    context_before = sum(
        record.context_before_tokens for record in context_records
    )
    context_after = sum(
        record.context_after_tokens for record in context_records
    )

    context_percentages = [
        calculate_context_reduction(
            record.context_before_tokens,
            record.context_after_tokens,
        )
        for record in context_records
    ]
    context_percentages = [
        value for value in context_percentages if value is not None
    ]

    quality_values = [
        record.quality_score
        for record in records
        if record.quality_score is not None
    ]

    # Eligible means a completed request with an explicit escalation outcome.
    # Older rows and incomplete/failed requests have completed=NULL/False and
    # cannot enter either denominator.
    completed_eligible = [
        record for record in records if record.completed is True
    ]
    completed_escalations = [
        record for record in completed_eligible if record.escalated is True
    ]
    evaluated_escalations = [
        record for record in completed_escalations
        if record.quality_status in {"pass", "fail"}
    ]

    summary = {
        "total_requests": total,
        "total_tokens": tokens,
        "average_latency_ms": (
            sum(latency_values) / len(latency_values)
            if latency_values else 0
        ),
        "average_cost": sum(costs) / len(costs) if costs else 0,
        "cache_hits": hits,
        "cache_hit_rate": hits / total if total else 0,
        "average_quality_score": (
            sum(quality_values) / len(quality_values)
            if quality_values else None
        ),
        "escalation_count": sum(
            record.escalated is True for record in records
        ),
        "completed_eligible_requests": len(completed_eligible),
        "escalation_rate": (
            len(completed_escalations) / len(completed_eligible)
            if completed_eligible else 0
        ),
        "escalation_success_rate": (
            sum(
                record.quality_status == "pass"
                for record in evaluated_escalations
            )
            / len(evaluated_escalations)
            if evaluated_escalations else 0
        ),
        "escalation_success_eligible_attempts": len(evaluated_escalations),
        "fallback_count": sum(
            record.fallback_used is True for record in records
        ),
        "model_usage_count": model_usage,
        "requests": {"total": total},
        "cache": {
            "hits": hits,
            "misses": misses,
            "hit_rate": hits / total if total else 0,
            "api_calls_avoided": hits,
            "estimated_cost_saved": saved_cost,
        },
        "tokens": {
            "input": inputs,
            "output": outputs,
            "total": tokens,
            "average_input": inputs / total if total else 0,
            "average_output": outputs / total if total else 0,
            "average_total": tokens / total if total else 0,
            "token_reduction_percent": (
                (baseline_tokens - tokens) / baseline_tokens * 100
                if baseline_tokens else None
            ),
        },
        "latency": {
            "average_ms": (
                sum(latency_values) / len(latency_values)
                if latency_values else 0
            )
        },
        "cost": {
            "total": sum(costs),
            "average_per_request": sum(costs) / len(costs) if costs else 0,
            "by_model": cost_by_model,
            "cache_miss_cost": miss_cost,
            "estimated_saved": saved_cost,
            "cost_reduction_percent": (
                (baseline_cost - sum(costs)) / baseline_cost * 100
                if baseline_cost else None
            ),
        },
        "models": {
            "usage_counts": model_usage,
            "usage_percentages": percentages,
        },
        "context": {
            "requests_with_metrics": len(context_records),
            "total_original_tokens": context_before,
            "total_optimized_tokens": context_after,
            "total_tokens_saved": context_before - context_after,
            "average_original_tokens": (
                context_before / len(context_records)
                if context_records else 0
            ),
            "average_optimized_tokens": (
                context_after / len(context_records)
                if context_records else 0
            ),
            "overall_reduction_percent": calculate_context_reduction(
                context_before, context_after
            ),
            "average_per_request_reduction_percent": (
                sum(context_percentages) / len(context_percentages)
                if context_percentages else None
            ),
        },
    }

    return summary
