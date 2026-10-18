import json
import os

from app.decision.paths import RULES_PATH
from app.decision.schemas.decision import DecisionScore


class RoutingDecision:
    def __init__(self, selected_model: str, uncertain: bool, reason: str):
        self.selected_model = selected_model
        self.uncertain = uncertain
        self.reason = reason


class RoutingPolicy:
    """Configurable routing rules. The decision model does not choose the LLM."""

    def __init__(self, rules: dict | None = None):
        self.rules = rules or _load_rules()

    def route(self, scores: dict[str, DecisionScore]) -> RoutingDecision:
        threshold = float(self.rules["confidence_threshold"])
        models = self.rules["models"]
        complexity = scores["complexity"]
        reasoning = scores["reasoning"]
        context = scores["context"]
        complexity_confident = complexity.calibrated_confidence >= threshold
        reasoning_confident = reasoning.calibrated_confidence >= threshold

        if complexity_confident and complexity.label == "complex":
            model = models["complex_or_high_reasoning"]
            reason = (
                "Calibrated complexity is complex "
                f"({complexity.calibrated_confidence:.2f}), "
                f"so the strong model '{model}' is used"
            )
            uncertain = False
        elif reasoning_confident and reasoning.label == "high":
            model = models["complex_or_high_reasoning"]
            reason = (
                "Calibrated reasoning is high "
                f"({reasoning.calibrated_confidence:.2f}), "
                f"so the strong model '{model}' is used"
            )
            uncertain = False
        elif complexity_confident and complexity.label == "simple" and reasoning.label == "low":
            model = models["simple_low_reasoning"]
            reason = (
                "Calibrated decision is simple with low reasoning, "
                f"so the cheaper model '{model}' is used"
            )
            uncertain = False
        elif complexity_confident:
            model = models["medium"]
            reason = (
                "Calibrated complexity is "
                f"{complexity.label} ({complexity.calibrated_confidence:.2f}), "
                f"so the balanced model '{model}' is used"
            )
            uncertain = False
        else:
            model = models["uncertain_fallback"]
            reason = (
                "Calibrated complexity confidence "
                f"{complexity.calibrated_confidence:.2f} is below {threshold:.2f}, "
                f"so the fallback model '{model}' is used"
            )
            uncertain = True

        if context.label == "high":
            reason += ". Context requirement is high"

        return RoutingDecision(
            selected_model=model,
            uncertain=uncertain,
            reason=reason,
        )


def _load_rules() -> dict:
    if RULES_PATH.exists():
        rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    else:
        rules = {
            "confidence_threshold": 0.5,
            "models": {
                "simple_low_reasoning": "local",
                "medium": "cheap",
                "complex_or_high_reasoning": "strong",
                "uncertain_fallback": "cheap",
            },
        }

    threshold = os.getenv("DECISION_CONFIDENCE_THRESHOLD")
    if threshold:
        rules["confidence_threshold"] = float(threshold)

    fallback = os.getenv("DECISION_FALLBACK_MODEL")
    if fallback:
        rules["models"]["uncertain_fallback"] = fallback

    return rules
