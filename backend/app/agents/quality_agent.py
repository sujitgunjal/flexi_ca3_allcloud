
from app.orchestration.state import RequestState


class QualityAgent:
    QUALITY_THRESHOLD = 0.70
    MIN_RESPONSE_LENGTH = 20

    ERROR_MARKERS = (
        "internal server error",
        "service unavailable",
        "bad gateway",
        "rate limit exceeded",
        "provider error",
        "model unavailable",
    )

    def run(self, state: RequestState) -> RequestState:
        """Apply lightweight heuristic checks to a generated response."""

        response = state.get("response", "")
        normalized = response.strip().lower()

        if not normalized:
            quality_score = 0.0
            quality_reason = "Response is empty"

        elif len(normalized) < self.MIN_RESPONSE_LENGTH:
            quality_score = 0.30
            quality_reason = "Response is too short"

        elif any(marker in normalized for marker in self.ERROR_MARKERS):
            quality_score = 0.20
            quality_reason = "Response contains a provider error marker"

        else:
            quality_score = 0.85
            quality_reason = "Response passed basic heuristic checks"

        escalation_required = quality_score < self.QUALITY_THRESHOLD

        state["quality_score"] = quality_score
        state["quality_reason"] = quality_reason
        state["escalation"] = escalation_required

        print(f"[QualityAgent] Score: {quality_score}")
        print(f"[QualityAgent] Reason: {quality_reason}")
        print(
            f"[QualityAgent] Escalation required: "
            f"{escalation_required}"
        )

        return state
