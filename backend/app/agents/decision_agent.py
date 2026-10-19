import logging
import traceback

from app.decision.base import DecisionProviderError
from app.decision.service import DecisionService
from app.orchestration.state import RequestState

logger = logging.getLogger(__name__)


class ComplexityAgent:

    def __init__(self, service: DecisionService | None = None):
        self.service = service or DecisionService()

    def run(self, state: RequestState) -> RequestState:
        print("[ComplexityAgent] Requesting a structured decision...")
        query = state.get("query", "")

        try:
            decision = self.service.decide(query)
        except DecisionProviderError as exc:
            cause = exc.__cause__
            logger.error(
                "Complexity decision failed stage=complexity category=%s cause=%s\n%s",
                type(exc).__name__,
                type(cause).__name__ if cause is not None else "none",
                "".join(traceback.format_tb(exc.__traceback__)),
            )
            raise RuntimeError(str(exc)) from exc

        payload = decision.model_dump()
        state["complexity"] = decision.complexity.label
        state["reasoning"] = decision.reasoning.label
        state["context_requirement"] = decision.context.label
        state["selected_model"] = decision.selected_model
        state["routing_reason"] = decision.routing_reason
        state["uncertain"] = decision.uncertain
        state["decision"] = payload

        print(
            "[ComplexityAgent] "
            f"complexity={decision.complexity.label} "
            f"reasoning={decision.reasoning.label} "
            f"context={decision.context.label}"
        )
        return state
