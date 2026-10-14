# Evaluation

This directory contains the fixed workload and documentation for comparing a strong-model baseline with the proposed gateway.

- `dataset.json` contains 100 query records across simple, medium, complex, coding, and long-context categories.
- `results.csv` is a headers-only baseline-versus-gateway template with request-level metrics, including context token counts, tokens saved, and reduction percentage. No experiment results have been added.
- The request outcome column `completed` distinguishes completed responses from failed attempts. `selected_model` is the initial routed tier and `final_model` is the tier that produced the final response; fallback is tracked separately from quality escalation.
- `metrics.md` defines escalation rate and the success rate among evaluated escalations, including eligible populations and zero-denominator behavior.
- `metrics.md` defines the evaluation measures; `data_contract.md` documents fields available to the logging layer.
- `metrics_api.md` documents the Day 2 request logging and retrieval API.
- `run_evaluation.py` validates the dataset and prints its size and category counts. It does not call LLMs or create experiment results.
- `cache_simulation.py` runs a small in-memory repeated-query simulation to demonstrate cache metric arithmetic. It is not a production cache and does not write experimental results.

Context reduction is `((context_before_tokens - context_after_tokens) / context_before_tokens) * 100`. Token reduction measures context size only; it does not measure answer quality. Evaluate quality separately using the quality measures in `metrics.md`.

Run the lightweight dataset check from the repository root:

```bash
python evaluation/run_evaluation.py
python evaluation/cache_simulation.py
```

For actual future experiments, run each query through both paths under recorded conditions, then add measured per-request observations to `results.csv`. Do not interpret the empty template as experimental results.
