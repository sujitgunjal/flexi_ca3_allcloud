import json
import sys

from app.decision.calibration.calibrator import (
    ProbabilityCalibrator,
    fit_isotonic_calibrator,
)
from app.decision.paths import (
    CALIBRATOR_PATH,
    DATASET_PATH,
    PREDICTIONS_PATH,
)
from app.decision.providers.ollama_provider import OllamaDecisionProvider
from app.decision.schemas.decision import TASKS
from app.decision.service import _uniform_distributions, get_calibrator
from app.decision.validation.probability_validator import (
    ProbabilityValidationError,
    parse_model_output,
)


def load_dataset() -> list[dict]:
    records = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    _validate_dataset(records)
    return records


def train(refresh: bool = False) -> ProbabilityCalibrator:
    records = load_dataset()
    predictions = [] if refresh else _load_predictions()
    by_id = {item["id"]: item for item in predictions}
    provider = OllamaDecisionProvider()

    print(
        f"[trainer] Decision model: ollama/{provider.model_name}. "
        "Jev is not used."
    )

    for index, record in enumerate(records, start=1):
        existing = by_id.get(record["id"])
        if existing and existing.get("output_valid") and not refresh:
            # Keep the saved raw probabilities, but take labels and split from
            # the dataset. A label correction must not require a new Ollama call.
            existing["split"] = record["split"]
            existing["domain"] = record["domain"]
            existing["query"] = record["query"]
            existing["labels"] = record["labels"]
            continue

        print(f"[trainer] {index}/{len(records)} {record['id']}")
        raw, output_valid = _classify_record(provider, record["query"])
        by_id[record["id"]] = {
            "id": record["id"],
            "split": record["split"],
            "domain": record["domain"],
            "query": record["query"],
            "labels": record["labels"],
            "raw": raw,
            "output_valid": output_valid,
        }
        _save_predictions(
            [by_id[item["id"]] for item in records if item["id"] in by_id]
        )

    predictions = [by_id[record["id"]] for record in records]
    _save_predictions(predictions)

    calibration_rows = [
        item
        for item in predictions
        if item["split"] == "calibration" and item["output_valid"]
    ]
    if len(calibration_rows) < 9:
        print(
            "[trainer] Not enough valid calibration rows. "
            "Saving an identity calibrator."
        )
        calibrator = ProbabilityCalibrator()
    else:
        calibrator = fit_isotonic_calibrator(calibration_rows)
        print(
            f"[trainer] Fitted isotonic calibrator on "
            f"{len(calibration_rows)} calibration rows."
        )

    path = calibrator.save(CALIBRATOR_PATH)
    get_calibrator(force_reload=True)
    print(f"[trainer] Saved {path}")
    return calibrator


def _classify_record(
    provider: OllamaDecisionProvider,
    query: str,
) -> tuple[dict[str, dict[str, float]], bool]:
    text = provider.classify_raw(query)
    try:
        return parse_model_output(text), True
    except ProbabilityValidationError as exc:
        text = provider.classify_raw(
            query,
            correction=(
                f"{exc}. Return only the corrected JSON object. "
                "Each decision must sum to 1 and must not be all zeros. "
                "Do not answer the query."
            ),
        )
        try:
            return parse_model_output(text), True
        except ProbabilityValidationError:
            return _uniform_distributions(), False


def _load_predictions() -> list[dict]:
    if not PREDICTIONS_PATH.exists():
        return []
    return json.loads(PREDICTIONS_PATH.read_text(encoding="utf-8"))


def _save_predictions(predictions: list[dict]) -> None:
    PREDICTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREDICTIONS_PATH.write_text(
        json.dumps(predictions, indent=2),
        encoding="utf-8",
    )


def _validate_dataset(records: list[dict]) -> None:
    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Dataset ids must be unique")

    for record in records:
        if record["split"] not in {"calibration", "validation", "test"}:
            raise ValueError(f"{record['id']} has an unknown split")
        for task, classes in TASKS.items():
            label = record["labels"][task]
            if label not in classes:
                raise ValueError(f"{record['id']} has an invalid {task} label")


def main() -> None:
    refresh = "--refresh" in sys.argv
    train(refresh=refresh)


if __name__ == "__main__":
    main()
