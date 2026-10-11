
from app.orchestration.state import RequestState
from app.providers import generate_response


class GenerateAgent:

    def run(self, state: RequestState) -> RequestState:
        model = state.get("selected_model", "cheap")
        prompt = state.get("query", "")

        state.setdefault("escalation_attempted", False)

        if "optimized_history" in state:
            history = state.get("optimized_history") or []
        else:
            history = state.get("conversation_history") or []

        print(f"[GenerateAgent] Generating response with model: {model}")

        try:
            result = generate_response(
                model=model,
                prompt=prompt,
                history=history,
            )
            actual_model = model
            fallback_used = False

        except Exception as error:
            fallback_model = {
                "local": "cheap",
                "cheap": "strong",
                "strong": "cheap",
            }.get(model, "cheap")

            print(
                f"[GenerateAgent] Model '{model}' failed: {error}. "
                f"Trying fallback model '{fallback_model}'"
            )

            result = generate_response(
                model=fallback_model,
                prompt=prompt,
                history=history,
            )
            actual_model = fallback_model
            fallback_used = True

            state["routing_reason"] = (
                f"Primary model '{model}' failed; "
                f"fallback model '{fallback_model}' succeeded"
            )

        state["response"] = result["response"]
        state["input_tokens"] = result.get("input_tokens")
        state["output_tokens"] = result.get("output_tokens")
        state["actual_model"] = actual_model
        state["fallback_used"] = fallback_used

        print(
            f"[GenerateAgent] Response created using model: "
            f"{actual_model}; input_tokens={state['input_tokens']}; "
            f"output_tokens={state['output_tokens']}"
        )

        return state
