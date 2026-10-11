from app.orchestration.state import RequestState


class QualityAgent:

    QUALITY_THRESHOLD = 0.70

    def run(self, state: RequestState) -> RequestState:
        print("[QualityAgent] Evaluating response quality...")

        response = state.get("response", "")
        preview = response[:120].encode("ascii", errors="replace").decode("ascii")

        print(
            f"[QualityAgent] Received response ({len(response)} chars): "
            f"{preview}"
        )

        # Basic placeholder heuristic for the escalation workflow.
        quality_score = 0.0 if not response.strip() else 0.90

        state["quality_score"] = quality_score
        state["escalation"] = quality_score < self.QUALITY_THRESHOLD

        print(f"[QualityAgent] Quality score: {quality_score}")
        print(f"[QualityAgent] Escalation required: {state['escalation']}")

        return state