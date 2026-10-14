"""Validation and response schemas for request metrics."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RequestMetrics(BaseModel):
    """Measurements available at any stage of a gateway request."""

    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, allow_inf_nan=False
    )

    query: str = Field(min_length=1)
    complexity: str | None = Field(default=None, max_length=32)
    selected_model: str | None = Field(
        default=None,
        max_length=128,
        description="Model tier routed for the initial inference attempt; retained across quality escalation.",
    )
    final_model: str | None = Field(
        default=None,
        max_length=128,
        description="Model tier that produced the final response, including any provider fallback or quality escalation.",
    )
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0)
    estimated_cost: float | None = Field(default=None, ge=0)
    cache_hit: bool | None = None
    cache_key: str | None = Field(default=None, max_length=256)
    cache_lookup_latency_ms: float | None = Field(default=None, ge=0)
    context_before_tokens: int | None = Field(default=None, ge=0)
    context_after_tokens: int | None = Field(default=None, ge=0)
    context_reduction_percent: float | None = None
    quality_score: float | None = Field(default=None, ge=0, le=1)
    quality_status: str | None = Field(default=None, max_length=32)
    escalated: bool | None = Field(
        default=None,
        description="Whether quality-based escalation was attempted; independent of provider fallback.",
    )
    fallback_used: bool | None = Field(
        default=None,
        description="Whether provider/model fallback was used after a generation failure; independent of quality escalation.",
    )
    completed: bool | None = Field(
        default=None,
        description="Whether a non-empty response was successfully returned. Null is unknown or legacy.",
    )

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("query must not be blank")
        return value

    @model_validator(mode="after")
    def context_counts_must_not_expand(self):
        before, after = self.context_before_tokens, self.context_after_tokens
        if before is not None and after is not None and after > before:
            raise ValueError("context_after_tokens cannot exceed context_before_tokens")
        return self


class RequestLogResponse(RequestMetrics):
    id: int
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class MetricsSummary(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    total_requests: int
    total_tokens: int
    average_latency_ms: float
    average_cost: float
    cache_hits: int
    cache_hit_rate: float
    average_quality_score: float | None
    escalation_count: int
    completed_eligible_requests: int
    escalation_rate: float = Field(
        description="Completed escalated requests divided by all requests with completed=true; 0.0 for an empty denominator."
    )
    escalation_success_rate: float = Field(
        description="Success rate among evaluated escalations: final quality pass outcomes divided by completed escalations with final quality pass or fail; 0.0 for an empty denominator."
    )
    escalation_success_eligible_attempts: int = Field(
        description="Completed escalated requests with final quality pass or fail; denominator for escalation_success_rate."
    )
    fallback_count: int
    model_usage_count: dict[str, int]
    requests: dict[str, int]
    cache: dict[str, float | int]
    tokens: dict[str, Any]
    latency: dict[str, float]
    cost: dict[str, Any]
    models: dict[str, dict[str, float | int]]
    context: dict[str, int | float | None]


class TraceEventResponse(BaseModel):
    request_id: int
    timestamp: datetime
    stage: str
    event: str
    metadata: dict[str, Any]
