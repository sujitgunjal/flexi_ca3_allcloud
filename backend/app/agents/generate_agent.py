
import logging

from app.orchestration.state import RequestState
from app.providers import generate_response
from app.providers.registry import get_tier

logger = logging.getLogger(__name__)


def _failure_category(error: Exception) -> str:
    name = type(error).__name__.lower()
    if "timeout" in name or isinstance(error, TimeoutError):
        return "timeout"
    if "connection" in name:
        return "connection_error"
    return "provider_error"


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

        except Exception as primary_error:
            # Keep the established tier fallback as the first attempt. A
            # remote-provider outage then gets one final chance on local Ollama.
            fallback_models = {
                "local": ("cheap",),
                "cheap": ("strong", "local"),
                "strong": ("cheap", "local"),
            }.get(model, ("cheap", "local"))
            failures = [(model, primary_error)]
            result = None
            actual_model = model

            for fallback_model in fallback_models:
                failed_model, failed_error = failures[-1]
                logger.warning(
                    "Generation failed provider/model=%s/%s category=%s; "
                    "trying fallback provider/model=%s/%s",
                    _provider_name(failed_model), failed_model,
                    _failure_category(failed_error),
                    _provider_name(fallback_model), fallback_model,
                )
                try:
                    result = generate_response(
                        model=fallback_model,
                        prompt=prompt,
                        history=history,
                    )
                except Exception as fallback_error:
                    failures.append((fallback_model, fallback_error))
                    logger.error(
                        "Fallback failed provider/model=%s/%s category=%s; "
                        "fallback_succeeded=false",
                        _provider_name(fallback_model), fallback_model,
                        _failure_category(fallback_error),
                    )
                    continue

                actual_model = fallback_model
                logger.info(
                    "Fallback succeeded provider/model=%s/%s after %s "
                    "provider failures; fallback_succeeded=true",
                    _provider_name(fallback_model), fallback_model,
                    len(failures),
                )
                break

            if result is None:
                # Re-raise the last real provider exception for the API's
                # controlled 502 handling; do not claim a generated response.
                raise failures[-1][1]

            fallback_used = True
            state["routing_reason"] = (
                f"Primary model '{model}' failed; fallback model "
                f"'{actual_model}' succeeded after "
                f"{len(failures)} provider failure(s)"
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


def _provider_name(model: str) -> str:
    return get_tier(model).provider
