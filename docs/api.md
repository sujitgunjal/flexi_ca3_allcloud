# Gateway API

The FastAPI application is served from the configured backend base URL (default
`http://localhost:8000`). Interactive OpenAPI documentation is available at
`/docs`.

## Request metrics and analytics

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/metrics` or `/metrics/summary` | Existing all-time metrics summary. |
| `GET` | `/metrics/recent` | Up to 100 latest persisted request records. |
| `GET` | `/metrics/{request_id}` | Retrieve one persisted request record. |
| `GET` | `/metrics/{request_id}/trace` | Retrieve that request's trace events. |
| `POST` | `/metrics/log` | Persist a request metric record. |
| `GET` | `/metrics/analytics?days=30` | Analytics aggregates and daily request trends. |

`days` accepts 1–365 and controls the trend window; summary totals cover all
persisted request records. The analytics response includes request outcomes,
known cache outcomes and hit rate, model usage, measured token totals, average
recorded latency, reported estimated cost, escalation/fallback counts, context
token reduction, and daily request counts. Optional totals and rates are `null`
when the source measurements are unavailable. Successful and failed requests
are counted only when `completed` is explicitly true or false; legacy records
with no outcome remain separately counted as unknown.

## Decision evaluation

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/evaluation/results` | Retrieve the persisted decision-evaluation report, or `{ "available": false, "report": null }` when none exists. |
| `POST` | `/evaluation/run` | Run the existing decision evaluator against saved raw predictions and return its report. |

The run endpoint does not invoke a model or alter routing policy. It recalculates
metrics from the prediction artifact and rewrites the evaluator's report
artifacts. A concurrent run returns `409`; missing prediction inputs also return
`409`. The saved report lives at the configured `REPORT_PATH` in
`app/decision/paths.py`.