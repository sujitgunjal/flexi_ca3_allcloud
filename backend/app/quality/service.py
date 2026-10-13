import os

from app.quality.base import QualityEvaluator, QualityEvaluatorError
from app.quality.ollama_evaluator import OllamaQualityEvaluator
from app.quality.schemas import QualityResult
from app.quality.validation import (
    QualityValidationError,
    invalid_quality_result,
    parse_quality_output,
)


class QualityService:
    def __init__(self, evaluator: QualityEvaluator | None = None):
        self.evaluator = evaluator or get_quality_evaluator()

    def evaluate(self, query: str, response: str) -> QualityResult:
        provider_name = getattr(self.evaluator, "name", "unknown")
        try:
            text = self.evaluator.evaluate_raw(query, response)
        except QualityEvaluatorError:
            return invalid_quality_result(
                provider_name,
                "The quality evaluator could not be reached.",
            )

        try:
            return parse_quality_output(text, provider=provider_name)
        except QualityValidationError as exc:
            try:
                corrected = self.evaluator.evaluate_raw(
                    query,
                    response,
                    correction=(
                        f"{exc}. Return only the corrected JSON object. "
                        "Each decision must be YES or NO. Do not answer the query."
                    ),
                )
            except QualityEvaluatorError:
                return invalid_quality_result(
                    provider_name,
                    "The quality evaluator could not be reached.",
                )
            try:
                return parse_quality_output(corrected, provider=provider_name)
            except QualityValidationError:
                return invalid_quality_result(
                    provider_name,
                    "The quality evaluation could not be validated.",
                )


def get_quality_evaluator() -> QualityEvaluator:
    selected = os.getenv("QUALITY_PROVIDER", "ollama").strip().lower()
    if selected in {"", "ollama", "local"}:
        return OllamaQualityEvaluator()
    if selected == "jev":
        raise QualityEvaluatorError(
            "The paid Jev quality API is not enabled. Use QUALITY_PROVIDER=ollama."
        )
    raise QualityEvaluatorError(
        f"Unknown quality provider '{selected}'. Use 'ollama'."
    )
