# Metrics logging API

The FastAPI backend exposes provider-independent request logging backed by `RequestLog`.

## Log a request

`POST /metrics/log` accepts the query plus any measurements already available. All measurement fields are optional, so early pipeline stages can submit only `query`, `complexity`, and `selected_model`.

```json
{
  "query": "Explain Docker",
  "complexity": "simple",
  "selected_model": "cheap-model",
  "input_tokens": 100,
  "output_tokens": 150,
  "latency_ms": 500,
  "cache_hit": false
}
```

Successful response (`201`):

```json
{"success": true, "request_id": 1}
```

Example application call:

```python
from app.services.metrics_service import log_request

record = log_request({
    "query": query,
    "complexity": complexity,
    "selected_model": model,
    "input_tokens": input_tokens,
    "output_tokens": output_tokens,
    "latency_ms": latency,
    "cache_hit": cache_hit,
})
print(record.id)
```

## Retrieve metrics

- `GET /metrics/recent` returns the latest 100 records, newest first.
- `GET /metrics/{request_id}` returns one record or `404` when it is missing.
- `GET /metrics/summary` returns aggregate metrics.
- `GET /metrics/{request_id}/trace` returns trace events in chronological order.

## Cache and trace integration

The cache implementation can report observations through the service without accessing ORM models:

```python
from app.services.metrics_service import record_cache_event

record_cache_event(request_id, cache_hit=True, cache_key="abc123", lookup_latency_ms=2.4)
```

Future agents can record flexible JSON metadata the same way:

```python
from app.services.trace_service import record_event

record_event(request_id, "routing", "model_selected", {"model": "cheap-model", "reason": "medium_complexity"})
```

Trace stages include `gateway`, `cache`, `complexity`, `context`, `routing`, `model`, `quality`, `escalation`, and `fallback`. Events are free-form strings, with common names such as `request_received`, `cache_hit`, `cache_miss`, `complexity_classified`, `context_optimized`, `model_selected`, `model_completed`, `quality_pass`, `quality_fail`, `escalation`, and `fallback`. Metadata is JSON-compatible.

## Fields and calculations

The request accepts `query`, `complexity`, `selected_model`, `final_model`, `input_tokens`, `output_tokens`, `total_tokens`, `latency_ms`, `estimated_cost`, `cache_hit`, `context_before_tokens`, `context_after_tokens`, `context_reduction_percent`, `quality_score`, `quality_status`, `escalated`, `fallback_used`, and `completed`. Only `query` is required. Token counts, latency, and cost must be non-negative; quality score is from 0 to 1.

When both input and output counts exist, total tokens are their sum unless the caller supplied `total_tokens`. Context reduction is `((before - after) / before) * 100`; when `before` is zero, it is `0`. Explicit values for derived fields are preserved.

The cost utility uses configurable rates per million tokens. Current values are clearly marked demo placeholders in `backend/app/services/cost_service.py`, not real provider prices. Unknown models or missing token counts produce no calculated cost. A supplied `estimated_cost` is kept.

The summary retains the Day 2 flat fields and adds groups: `requests`, `cache`, `tokens`, `latency`, `cost`, and `models`. Cache misses count explicit false observations; unknown cache values are excluded from hit/miss counts but remain in the overall hit-rate denominator. API calls avoided equal cache hits. Estimated cache savings sum each hit's recorded request cost or estimate it with the configurable placeholder rates; unknown model/token data adds no estimate. Token averages divide sums by all requests. Supply optional `baseline_tokens` and `baseline_cost` query parameters to `/metrics/summary` (or `/metrics`) for reduction percentages. A zero baseline yields `null`. Pricing rates are placeholders, not provider quotes.

For example, a chronological trace can contain `gateway/request_received`, `cache/cache_miss`, `complexity/complexity_classified`, and `routing/model_selected`, with per-event metadata.

Chat sets `completed=true` only when it returns a non-empty response, and `false` when generation fails or returns an empty response. Legacy `completed=null` rows are unknown and are not backfilled or included in completed-request denominators. `selected_model` means the model tier routed for the initial inference attempt and is retained across quality retries; `final_model` means the tier that actually produced the final response, including a provider fallback. Historical unknown model values remain null.

`escalation_rate` is completed rows with `escalated=true` divided by all rows with `completed=true`, including both completed escalated and non-escalated requests. `escalation_success_rate` is the **success rate among evaluated escalations**: completed escalated requests with final quality status `pass`, divided by completed escalated requests whose final quality status is `pass` or `fail`. The response field `escalation_success_eligible_attempts` gives that denominator. `pass` counts as success and `fail` as unsuccessful; missing, pending, and `indeterminate` outcomes are excluded from numerator and denominator. Each rate returns `0.0` when its denominator is empty. `escalated` records quality-based escalation; `fallback_used` separately records provider/model fallback after generation failure. Either can occur without the other. Quality fields contain the final evaluation only; pre-escalation quality is not persisted.
