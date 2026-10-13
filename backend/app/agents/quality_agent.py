from app.orchestration.state import RequestState
from app.quality.service import QualityService
from app.quality.validation import empty_response_result


class QualityAgent:
    def __init__(self, service: QualityService | None = None):
        self.service = service or QualityService()

    def run(self, state: RequestState) -> RequestState:
        query = state.get("query", "")
        response = state.get("response", "")
        provider_name = getattr(self.service.evaluator, "name", "unknown")

        if not response.strip():
            result = empty_response_result(provider_name)
        else:
            result = self.service.evaluate(query, response)

        state["quality_score"] = result.quality_score
        state["quality_reason"] = result.quality_reason
        state["quality_relevant"] = result.relevant.decision
        state["quality_complete"] = result.complete.decision
        state["quality_escalate"] = result.escalate.decision
        state["quality_evaluation"] = result.model_dump()
        state["escalation"] = result.escalation_required

        print(
            "[QualityAgent] "
            f"relevant={result.relevant.decision} "
            f"complete={result.complete.decision} "
            f"escalate={result.escalate.decision}"
        )
        print(f"[QualityAgent] Score: {result.quality_score}")
        print(
            "[QualityAgent] Escalation required: "
            f"{result.escalation_required}"
        )
        return state
