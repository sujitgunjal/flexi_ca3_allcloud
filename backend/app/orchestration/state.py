from typing import Any, TypedDict


class RequestState(TypedDict, total=False):
    query: str
    conversation_history: list[dict[str, Any]]

    complexity: str
    reasoning: str
    context_requirement: str
    optimized_context: str
    optimized_history: list[dict[str, Any]]
    original_token_count: int
    optimized_token_count: int
    messages_selected: int
    context_reduction_percent: float
    embedding_source: str
    selected_model: str
    initial_selected_model: str
    routing_reason: str
    uncertain: bool
    decision: dict[str, Any]

    cache_hit: bool
    cache_key: str
    metrics_request_id: int
    cache_unavailable: bool
    cached_response: bool

    quality_score: float
    quality_reason: str
    quality_relevant: str
    quality_complete: str
    quality_escalate: str
    quality_evaluation: dict[str, Any]
    quality_escalation_count: int
    escalation: bool

    cost: float
    latency: float

    response: str
    actual_model: str
    input_tokens: int | None
    output_tokens: int | None
    fallback_used: bool
    escalation_attempted: bool
