
import sys

from app.orchestration.graph import llm_graph

sys.stdout.reconfigure(errors="replace")


initial_state = {
    "query": "Reply with one short sentence.",
    "conversation_history": [],
    "cache_hit": False,
    "cost": 0.0,
    "latency": 0.0,
}


result = llm_graph.invoke(initial_state)


print("\n========== FINAL STATE ==========")

for key, value in result.items():
    print(f"{key}: {value}")


expected = {
    "cache_hit": False,
    "optimized_context": initial_state["query"],
}

failures = []

for key, value in expected.items():
    if result.get(key) != value:
        failures.append(
            f"{key}: expected {value!r}, got {result.get(key)!r}"
        )


# Validate the selected model.
if result.get("selected_model") not in {"local", "cheap", "strong"}:
    failures.append(
        f"selected_model: unexpected {result.get('selected_model')!r}"
    )


# Validate complexity classification.
if result.get("complexity") not in {"simple", "medium", "complex"}:
    failures.append(
        f"complexity: unexpected {result.get('complexity')!r}"
    )


# Validate quality score.
quality_score = result.get("quality_score")

if (
    not isinstance(quality_score, (int, float))
    or isinstance(quality_score, bool)
    or not 0.0 <= quality_score <= 1.0
):
    failures.append(
        f"quality_score: expected a score between 0 and 1, "
        f"got {quality_score!r}"
    )


# Validate decision confidence fields.
decision = result.get("decision") or {}
complexity = decision.get("complexity") or {}

if (
    "raw_confidence" not in complexity
    or "calibrated_confidence" not in complexity
):
    failures.append(
        "decision: raw and calibrated confidence were not both present"
    )


# Validate generated response.
response = result.get("response", "")

if not isinstance(response, str) or not response.strip():
    failures.append(
        f"response: expected a model reply, got {response!r}"
    )


# Validate escalation state.
if not isinstance(result.get("escalation"), bool):
    failures.append(
        f"escalation: expected a boolean, got {result.get('escalation')!r}"
    )


if failures:
    print("\n========== PIPELINE CHECK FAILED ==========")

    for failure in failures:
        print(failure)

    raise SystemExit(1)


print("\n========== PIPELINE CHECK PASSED ==========")
print(
    "Cache -> Complexity -> Context -> Router -> "
    "Generate -> Quality -> Optional Escalation"
)
