
import logging
import time
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.orchestration.graph import llm_graph
from app.providers.registry import get_tier
from app.cache.redis_cache import RedisError, cache, generate_cache_key
from app.services.cost_service import calculate_cost
from app.services.metrics_service import (
    log_request,
    record_cache_event,
    record_generation_metrics,
)

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


class ChatResponse(BaseModel):
    request_id: str
    conversation_id: str
    status: str
    message: str
    note: str
    decision: dict | None = None


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest):
    request_id = str(uuid4())
    conversation_id = request.conversation_id or str(uuid4())
    metric_record = log_request({"query": request.message})

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
    except Exception as exc:
        elapsed_ms = round(
            (time.perf_counter() - start_time) * 1000, 2
        )
        logger.exception("LLM graph execution failed")

        try:
            record_generation_metrics(
                metric_record.id,
                latency_ms=elapsed_ms,
            )
        except Exception:
            logger.exception("Failed to save failed-request latency")

        raise HTTPException(
            status_code=502,
            detail="LLM provider or orchestration error",
        ) from exc

    elapsed_ms = round(
        (time.perf_counter() - start_time) * 1000, 2
    )

    selected_model = (
        result.get("actual_model")
        or result.get("selected_model")
        or "cheap"
    )
    response_text = result.get("response") or ""

    if not response_text:
        try:
            record_generation_metrics(
                metric_record.id,
                latency_ms=elapsed_ms,
                selected_model=result.get("selected_model"),
                final_model=result.get("actual_model"),
            )
        except Exception:
            logger.exception("Failed to save empty-response metrics")

        raise HTTPException(
            status_code=502,
            detail="LLM provider returned an empty response",
        )

    input_tokens = result.get("input_tokens")
    output_tokens = result.get("output_tokens")
    final_model = (
        result.get("actual_model")
        or result.get("selected_model")
    )

    estimated_cost = calculate_cost(
        final_model,
        input_tokens,
        output_tokens,
    )

    quality_score = result.get("quality_score")
    quality_status = (
        "pass"
        if quality_score is not None and quality_score >= 0.70
        else "fail"
        if quality_score is not None
        else None
    )

    try:
        record_generation_metrics(
            metric_record.id,
            complexity=result.get("complexity"),
            selected_model=result.get("selected_model") or selected_model,
            final_model=final_model or selected_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            quality_score=quality_score,
            quality_status=quality_status,
            escalated=bool(
                result.get("escalation_attempted", False)
            ),
            fallback_used=bool(result.get("fallback_used", False)),
            latency_ms=elapsed_ms,
            estimated_cost=estimated_cost,
        )
    except Exception:
        logger.exception("Generation metrics could not be saved")

    cache_key = (
        result.get("cache_key")
        or generate_cache_key(request.message)
    )

    if not result.get("cache_hit") and not result.get("cache_unavailable"):
        try:
            cache.set(
                cache_key,
                {
                    "response": response_text,
                    "selected_model": selected_model,
                    "decision": result.get("decision"),
                    "complexity": result.get("complexity"),
                    "uncertain": result.get("uncertain"),
                    "routing_reason": result.get("routing_reason"),
                },
            )
        except RedisError:
            logger.exception(
                "Redis cache write failed; response returned uncached"
            )
            try:
                record_cache_event(
                    metric_record.id,
                    False,
                    cache_key,
                    fallback_used=True,
                )
            except Exception:
                logger.exception("Cache metrics could not be saved")

    decision = result.get("decision") or {}
    complexity = decision.get("complexity", {})

    try:
        answer_model = get_tier(selected_model).model
    except ValueError:
        answer_model = selected_model

    return ChatResponse(
        request_id=request_id,
        conversation_id=conversation_id,
        status="success",
        message=response_text,
        decision=decision or None,
        note=(
            f"Decision engine: {decision.get('provider', 'n/a')} "
            f"({decision.get('decision_model', 'n/a')}). "
            f"Answer model: {selected_model} ({answer_model}). "
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
