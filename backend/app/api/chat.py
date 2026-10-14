
import logging
import time
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field

from app.orchestration.graph import llm_graph
from app.providers.registry import get_tier
from app.cache.redis_cache import cache, generate_cache_key
from app.services.cost_service import calculate_cost
from app.services.metrics_service import (
    log_request,
    record_cache_event,
    record_generation_metrics,
)
from app.services.trace_service import record_event

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatMessage(BaseModel):
    role: str = Field(
        ...,
        description="Message role: user, assistant, or system",
    )
    content: str


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        description="Current user message",
    )
    conversation_id: Optional[str] = None
    history: List[ChatMessage] = Field(default_factory=list)


class ChatDetails(BaseModel):
    model_tier: str | None = None
    actual_model: str | None = None
    complexity: str | None = None
    quality_score: float | None = None
    quality_status: str | None = None
    quality_relevant: str | None = None
    quality_complete: str | None = None
    quality_escalate: str | None = None
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float | None = None
    cache_hit: bool | None = None
    escalated: bool | None = None
    fallback_used: bool | None = None
    routing_reason: str | None = None


class ChatResponse(BaseModel):
    request_id: str
    conversation_id: str
    status: str
    message: str
    note: str
    decision: dict | None = None
    details: ChatDetails | None = None


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    request_id = str(uuid4())
    conversation_id = request.conversation_id or str(uuid4())
    metric_record = log_request({"query": request.message})
    _record_trace_safely(metric_record.id, "gateway", "request_received")

    initial_state = {
        "query": request.message,
        "conversation_history": [
            {"role": message.role, "content": message.content}
            for message in request.history
        ],
        "cache_hit": False,
        "cost": 0.0,
        "latency": 0.0,
        "metrics_request_id": metric_record.id,
    }

    start_time = time.perf_counter()

    try:
        result = llm_graph.invoke(initial_state)
        logger.info("Chat request stage=graph_complete")
    except Exception as exc:
        elapsed_ms = round(
            (time.perf_counter() - start_time) * 1000, 2
        )
        # Avoid logging provider exception text: SDK errors can include
        # request/response details. The category is enough to correlate with
        # the provider/model diagnostics emitted by GenerateAgent.
        logger.error(
            "LLM graph execution failed category=%s",
            type(exc).__name__,
        )

        return JSONResponse(
            status_code=502,
            content={"detail": "LLM provider or orchestration error"},
            background=BackgroundTask(
                _record_failed_chat_safely,
                metric_record.id,
                {"latency_ms": elapsed_ms, "completed": False},
                "generation_failed",
                {"error_category": type(exc).__name__},
            ),
        )

    elapsed_ms = round(
        (time.perf_counter() - start_time) * 1000, 2
    )

    selected_model = (
        result.get("initial_selected_model") or result.get("selected_model")
    )
    answer_model_name = result.get("actual_model") or selected_model
    response_text = result.get("response") or ""

    if not response_text:
        return JSONResponse(
            status_code=502,
            content={"detail": "LLM provider returned an empty response"},
            background=BackgroundTask(
                _record_failed_chat_safely,
                metric_record.id,
                {
                    "latency_ms": elapsed_ms,
                    "selected_model": (
                        result.get("initial_selected_model")
                        or result.get("selected_model")
                    ),
                    "completed": False,
                },
                "empty_response",
                {},
            ),
        )

    input_tokens = result.get("input_tokens")
    output_tokens = result.get("output_tokens")
    final_model = result.get("actual_model")

    estimated_cost = calculate_cost(
        final_model,
        input_tokens,
        output_tokens,
    )

    quality_evaluation = result.get("quality_evaluation") or {}
    quality_is_indeterminate = quality_evaluation.get("output_valid") is False
    quality_score = (
        None if quality_is_indeterminate else result.get("quality_score")
    )
    quality_status = (
        "indeterminate"
        if quality_is_indeterminate
        else "pass"
        if quality_score is not None and quality_score >= 0.70
        else "fail"
        if quality_score is not None
        else None
    )

    metric_values = {
        "complexity": result.get("complexity"),
        "selected_model": selected_model,
        "final_model": final_model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "quality_score": quality_score,
        "quality_status": quality_status,
        "escalated": bool(result.get("escalation_attempted", False)),
        "fallback_used": bool(result.get("fallback_used", False)),
        "completed": True,
        "latency_ms": elapsed_ms,
        "estimated_cost": estimated_cost,
    }

    cache_key = (
        result.get("cache_key")
        or generate_cache_key(request.message)
    )

    cache_value = None
    if not result.get("cache_hit") and not result.get("cache_unavailable"):
        cache_value = {
            "response": response_text,
            "selected_model": selected_model,
            "decision": result.get("decision"),
            "complexity": result.get("complexity"),
            "uncertain": result.get("uncertain"),
            "routing_reason": result.get("routing_reason"),
            "_cache_query": request.message,
        }

    # These writes are optional observations. Run them after FastAPI sends the
    # response so a slow database or cache cannot keep the client waiting.
    background_tasks.add_task(
        _persist_chat_observations,
        metric_record.id,
        metric_values,
        cache_key if cache_value is not None else None,
        cache_value,
    )
    background_tasks.add_task(
        _record_trace_safely,
        metric_record.id,
        "gateway",
        "request_completed",
        {
            "selected_model": selected_model,
            "final_model": final_model,
            "quality_status": quality_status,
            "escalated": bool(result.get("escalation_attempted", False)),
            "fallback_used": bool(result.get("fallback_used", False)),
        },
    )
    if result.get("escalation_attempted"):
        background_tasks.add_task(
            _record_trace_safely,
            metric_record.id,
            "escalation",
            "escalation_attempted",
            {"initial_model": selected_model, "final_model": final_model},
        )
    if result.get("fallback_used"):
        background_tasks.add_task(
            _record_trace_safely,
            metric_record.id,
            "fallback",
            "provider_fallback_used",
            {"final_model": final_model},
        )

    decision = result.get("decision") or {}
    complexity = decision.get("complexity", {})

    try:
        answer_model = get_tier(answer_model_name).model
    except ValueError:
        answer_model = answer_model_name

    response = ChatResponse(
        request_id=request_id,
        conversation_id=conversation_id,
        status="success",
        message=response_text,
        decision=decision or None,
        details=ChatDetails(
            model_tier=selected_model,
            actual_model=answer_model,
            complexity=result.get("complexity"),
            quality_score=quality_score,
            quality_status=quality_status,
            quality_relevant=result.get("quality_relevant"),
            quality_complete=result.get("quality_complete"),
            quality_escalate=result.get("quality_escalate"),
            latency_ms=elapsed_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=estimated_cost,
            cache_hit=result.get("cache_hit"),
            escalated=bool(result.get("escalation_attempted", False)),
            fallback_used=bool(result.get("fallback_used", False)),
            routing_reason=result.get("routing_reason"),
        ),
        note=(
            f"Decision engine: {decision.get('provider', 'n/a')} "
            f"({decision.get('decision_model', 'n/a')}). "
            f"Answer model: {answer_model_name} ({answer_model}). "
            f"Complexity: {result.get('complexity')} "
            f"(raw confidence {complexity.get('raw_confidence')}, "
            f"calibrated confidence "
            f"{complexity.get('calibrated_confidence')}). "
            f"Uncertain: {result.get('uncertain')}. "
            f"Reason: {result.get('routing_reason')}. "
            f"Context: {result.get('messages_selected', 0)} messages, "
            f"{result.get('original_token_count', 0)} -> "
            f"{result.get('optimized_token_count', 0)} tokens "
            f"({result.get('context_reduction_percent', 0)}% reduction)."
        ),
    )
    logger.info("Chat request stage=response_ready cache_write_deferred=true")
    return response


def _record_generation_metrics_safely(
    request_id: int,
    values: dict,
) -> None:
    try:
        record_generation_metrics(request_id, **values)
    except Exception as exc:
        logger.warning(
            "Generation metrics write failed category=%s",
            type(exc).__name__,
        )


def _record_trace_safely(
    request_id: int,
    stage: str,
    event: str,
    metadata: dict | None = None,
) -> None:
    try:
        record_event(request_id, stage, event, metadata)
    except Exception as exc:
        logger.warning(
            "Request trace write failed category=%s", type(exc).__name__
        )


def _record_failed_chat_safely(
    request_id: int,
    metric_values: dict,
    event: str,
    metadata: dict,
) -> None:
    _record_generation_metrics_safely(request_id, metric_values)
    _record_trace_safely(request_id, "gateway", event, metadata)


def _persist_chat_observations(
    request_id: int,
    metric_values: dict,
    cache_key: str | None,
    cache_value: dict | None,
) -> None:
    _record_generation_metrics_safely(request_id, metric_values)
    if cache_key is None or cache_value is None:
        return

    try:
        cache.set(cache_key, cache_value)
    except Exception as exc:
        logger.warning(
            "Response cache write failed category=%s; response returned uncached",
            type(exc).__name__,
        )
        try:
            record_cache_event(
                request_id,
                False,
                cache_key,
                fallback_used=True,
            )
        except Exception as metrics_error:
            logger.warning(
                "Cache failure metrics write failed category=%s",
                type(metrics_error).__name__,
            )
