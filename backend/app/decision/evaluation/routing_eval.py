"""Score model-tier choices on a split that was not used to fit the calibrator."""

import json
from collections import Counter

from app.decision.paths import RULES_PATH
from app.decision.routing.policy import RoutingPolicy
from app.decision.schemas.decision import TASKS, DecisionScore


TIERS = ("local", "cheap", "strong")
THRESHOLD_CANDIDATES = (0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80)


def gold_model(labels: dict) -> str:
    """Route the ground-truth labels as the policy would at full confidence.

    Context changes the note, not the model tier. Uncertainty does not apply,
    because the labels are the reference and are not a probability.
    """

    if labels["complexity"] == "complex" or labels["reasoning"] == "high":
        return "strong"
    if labels["complexity"] == "simple" and labels["reasoning"] == "low":
        return "local"
    return "cheap"


def select_threshold(records: list[dict], probability_rows: list[dict]) -> dict:
    """Pick a threshold from validation rows only.

    The score is routing accuracy against gold_model. Ties prefer fewer
    fallbacks, then the current default of 0.55.
    """

    sweeps = [
        score_routing(records, probability_rows, threshold)
        for threshold in THRESHOLD_CANDIDATES
    ]
    selected = max(
        sweeps,
        key=lambda row: (
            row["routing_accuracy"],
            -row["uncertain_rate"],
            -abs(row["threshold"] - 0.55),
        ),
    )
    return {"selected_threshold": selected["threshold"], "sweep": sweeps}


def score_routing(
    records: list[dict],
    probability_rows: list[dict],
    threshold: float,
) -> dict:
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    rules["confidence_threshold"] = threshold
    policy = RoutingPolicy(rules)
    gold = []
    predicted = []
    uncertain = 0
    tier_counts = {tier: 0 for tier in TIERS}
    examples = []

    for record, probabilities in zip(records, probability_rows):
        decision = policy.route(_scores(probabilities))
        expected = gold_model(record["labels"])
        gold.append(expected)
        predicted.append(decision.selected_model)
        tier_counts[decision.selected_model] = (
            tier_counts.get(decision.selected_model, 0) + 1
        )
        if decision.uncertain:
            uncertain += 1
        if decision.selected_model != expected and len(examples) < 8:
            examples.append(
                {
                    "id": record["id"],
                    "query": record["query"],
                    "gold_model": expected,
                    "selected_model": decision.selected_model,
                    "uncertain": decision.uncertain,
                    "labels": record["labels"],
                }
            )

    matrix = [
        [0 for _ in TIERS]
        for _ in TIERS
    ]
    index = {tier: position for position, tier in enumerate(TIERS)}
    for expected, chosen in zip(gold, predicted):
        matrix[index[expected]][index.get(chosen, 0)] += 1

    correct = sum(expected == chosen for expected, chosen in zip(gold, predicted))
    return {
        "threshold": threshold,
        "count": len(records),
        "routing_accuracy": _ratio(correct, len(records)),
        "uncertain_count": uncertain,
        "uncertain_rate": _ratio(uncertain, len(records)),
        "selected_model_counts": tier_counts,
        "gold_model_counts": dict(Counter(gold)),
        "confusion_matrix": {"labels": list(TIERS), "matrix": matrix},
        "mismatches": examples,
    }


def _scores(probabilities_by_task: dict) -> dict[str, DecisionScore]:
    scores = {}
    for task, classes in TASKS.items():
        probabilities = probabilities_by_task[task]
        label = max(classes, key=lambda name: probabilities[name])
        confidence = float(probabilities[label])
        scores[task] = DecisionScore(
            label=label,
            raw_probabilities=probabilities,
            raw_confidence=confidence,
            calibrated_probabilities=probabilities,
            calibrated_confidence=confidence,
        )
    return scores


def _ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)
