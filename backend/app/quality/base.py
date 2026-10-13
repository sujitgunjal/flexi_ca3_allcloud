from typing import Protocol


class QualityEvaluatorError(RuntimeError):
    """The quality evaluator could not be reached or was not configured."""


class QualityEvaluator(Protocol):
    """Replaceable evaluator. The local Ollama implementation is the default."""

    name: str

    def evaluate_raw(
        self,
        query: str,
        response: str,
        *,
        correction: str | None = None,
    ) -> str:
        """Return the evaluator's raw JSON text. Do not answer the user."""
