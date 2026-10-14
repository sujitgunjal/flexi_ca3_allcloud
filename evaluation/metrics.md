# Evaluation metrics

## Comparison setup

**Baseline:** Every request → Strong Model → Response.

**Proposed Gateway:** Request → Cache → Complexity → Context Optimization → Model Selection → LLM → Quality Check → Escalation/Fallback → Response.

**Research question:**

> Can a multi-agent resource optimization layer reduce LLM inference cost and context consumption while maintaining comparable response quality and acceptable latency?

Run the same dataset against both paths, record per-request observations, and compare totals and distributions. Keep model/provider, dataset version, and run conditions with the eventual results so comparisons are interpretable. Do not treat this Day 1 template as measured results.

## Metrics

| Metric | What to record and calculate | Why it matters |
|---|---|---|
| Cost | Estimated cost per request and total cost for baseline and gateway. `cost_reduction = ((baseline_cost - gateway_cost) / baseline_cost) * 100` | Measures the main resource-saving goal. Handle a zero baseline cost before calculating a percentage. |
| Tokens | Input, output, and total tokens; context tokens before and after optimization. `context_tokens_saved = before - after`; `context_reduction_percent = ((before - after) / before) * 100` | Shows inference consumption and whether context optimization reduces prompt size. Reduction is undefined when original tokens are missing or zero. Token reduction is not itself a measure of answer quality; assess quality separately. |

| Latency | Average latency, P95 latency, and latency per model | Captures user-perceived delay and reveals whether optimization adds overhead or improves response time. |
| Routing | Percentage of requests sent to local, cheap, and strong models | Shows how the gateway distributes work and whether it avoids unnecessary strong-model use. |
| Cache | Cache hits, misses, hit rate, and API calls avoided. `cache_hit_rate = cache_hits / total_requests` | Measures requests served without inference. Future calculations must avoid division by zero. |
| Quality | Record the evaluator score on the API's 0–1 scale, plus the final `pass`, `fail`, or `indeterminate` status. Track average score, quality pass rate, escalation rate, and the success rate among evaluated escalations. | Checks that savings do not come at the cost of useful answers and indicates when escalation is needed. The current chat pass threshold is 0.70. |
| Reliability | Fallback count, fallback rate, and successful fallback rate | Indicates how often provider failure recovery is needed and whether it restores a usable response. |

The results template records `context_before_tokens`, `context_after_tokens`, `context_tokens_saved`, and `context_reduction_percent`. Only measured values should be entered.

For rates, state the denominator used and omit or explicitly define rates when the denominator is zero. Record baseline and gateway measurements from the same query where possible.

## Escalation analytics

Completed eligible requests are rows with `completed=true`. Rows with `completed=false` and legacy rows with `completed=null` are excluded; unknown completion is never inferred from other fields.

- **Escalation rate** = completed rows with `escalated=true` / all completed eligible requests. Its denominator includes both completed escalated and completed non-escalated requests.
- **Success rate among evaluated escalations** = completed escalated rows whose final quality status is `pass` / completed escalated rows whose final quality status is `pass` or `fail`. `pass` is successful; `fail` is unsuccessful. Missing, pending, and `indeterminate` quality outcomes are excluded from this denominator and are not treated as failures.

The success-rate denominator is exposed as `escalation_success_eligible_attempts`. Both rates return `0.0` when their denominator is zero. `escalated` records quality-based escalation attempts; `fallback_used` separately records provider/model fallback after generation failure, and either may be true without the other. `selected_model` is the model tier routed for the initial inference attempt and remains stable across escalation. `final_model` is the tier that actually generated the final response, including fallback. Historical rows retain their stored values; unavailable original/final models, completion, escalation, or quality outcomes remain unknown rather than being backfilled. The stored quality result is the final available evaluation only; pre-escalation quality is not persisted, so quality improvement caused by escalation cannot be calculated.
