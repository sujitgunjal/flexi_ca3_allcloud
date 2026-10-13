import json

from pydantic import ValidationError

from app.quality.schemas import QualityEvaluation, QualityResult, YesNoDecision


class QualityValidationError(ValueError):
    """The evaluator output is not a usable quality decision."""


def parse_quality_output(text: str, *, provider: str) -> QualityResult:
    payload = _load_json_object(text)
    try:
        evaluation = QualityEvaluation.model_validate(payload)
    except ValidationError as exc:
        raise QualityValidationError(str(exc)) from exc
    return _result(evaluation, output_valid=True, provider=provider)


def invalid_quality_result(provider: str, reason: str) -> QualityResult:
    """A rejected evaluation does not escalate, so a bad parse cannot loop."""

    decision = YesNoDecision(decision="NO", reason=reason)
    return _result(
        QualityEvaluation(relevant=decision, complete=decision, escalate=decision),
        output_valid=False,
        provider=provider,
    )


def empty_response_result(provider: str) -> QualityResult:
    evaluation = QualityEvaluation(
        relevant=YesNoDecision(
            decision="NO",
            reason="The response is empty, so it does not address the request.",
        ),
        complete=YesNoDecision(
            decision="NO",
            reason="An empty response leaves the request unanswered.",
        ),
        escalate=YesNoDecision(
            decision="YES",
            reason="A stronger model could reasonably produce a response.",
        ),
    )
    return _result(evaluation, output_valid=True, provider=provider)


def _result(
    evaluation: QualityEvaluation,
    *,
    output_valid: bool,
    provider: str,
) -> QualityResult:
    return QualityResult(
        relevant=evaluation.relevant,
        complete=evaluation.complete,
        escalate=evaluation.escalate,
        output_valid=output_valid,
        provider=provider,
        quality_score=_score(evaluation, output_valid),
        quality_reason=_reason(evaluation),
    )


def _score(evaluation: QualityEvaluation, output_valid: bool) -> float:
    if not output_valid:
        return 0.5
    if evaluation.escalate.decision == "YES":
        return 0.4
    if evaluation.relevant.decision == "YES" and evaluation.complete.decision == "YES":
        return 0.9
    if evaluation.relevant.decision == "YES":
        return 0.55
    return 0.25


def _reason(evaluation: QualityEvaluation) -> str:
    return (
        f"Relevant {evaluation.relevant.decision}: {evaluation.relevant.reason} "
        f"Complete {evaluation.complete.decision}: {evaluation.complete.reason} "
        f"Escalate {evaluation.escalate.decision}: {evaluation.escalate.reason}"
    ).strip()


def _load_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise QualityValidationError("Quality evaluation did not contain a JSON object")

    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise QualityValidationError("Quality evaluation JSON could not be parsed") from exc

    if not isinstance(payload, dict):
        raise QualityValidationError("Quality evaluation must be a JSON object")
    return payload
