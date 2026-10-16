from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.schemas.metrics import (
    AnalyticsResponse,
    MetricsSummary,
    RequestLogResponse,
    RequestMetrics,
    TraceEventResponse,
)
from app.services.metrics_service import (
    get_analytics,
    get_recent_requests,
    get_request,
    get_summary_metrics,
    log_request,
)
from app.services.trace_service import get_trace

router = APIRouter()


class MetricsLogResponse(BaseModel):
    success: bool
    request_id: int


@router.post("/log", response_model=MetricsLogResponse, status_code=201)
def create_metrics_log(metrics: RequestMetrics):
    record = log_request(metrics)
    return MetricsLogResponse(success=True, request_id=record.id)


@router.get("/recent", response_model=list[RequestLogResponse])
def recent_metrics():
    return get_recent_requests()


@router.get("/analytics", response_model=AnalyticsResponse)
def analytics(days: int = Query(default=30, ge=1, le=365)):
    return get_analytics(days=days)


@router.get("", response_model=MetricsSummary)
@router.get("/summary", response_model=MetricsSummary)
def summary_metrics(baseline_tokens: int | None = Query(default=None, ge=0),
                    baseline_cost: float | None = Query(default=None, ge=0)):
    return get_summary_metrics(baseline_tokens=baseline_tokens, baseline_cost=baseline_cost)


@router.get("/{request_id}/trace", response_model=list[TraceEventResponse])
def request_trace(request_id: int):
    if get_request(request_id) is None:
        raise HTTPException(status_code=404, detail="Request metrics not found")
    return get_trace(request_id)


@router.get("/{request_id}", response_model=RequestLogResponse)
def metrics_by_id(request_id: int):
    record = get_request(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Request metrics not found")
    return record
