"""Fit and score the validation-selected decision setup.

Selected setup: llama3:8b with the candidate prompt.
Writes only under calibration/artifacts/llama3-8b-candidate/.
Does not change the live prompt, the deployed threshold, or older artifact files.
"""

import json
import sys

from app.decision.calibration.calibrator import (
    ProbabilityCalibrator,
    fit_isotonic_calibrator,
)
from app.decision.evaluation.metrics import classification_report, brier_score
from app.decision.evaluation.prompt_experiment import _classify_once
from app.decision.evaluation.routing_eval import score_routing, select_threshold
from app.decision.paths import ARTIFACT_DIR, DATASET_PATH
from app.decision.prompts.candidate import CANDIDATE_SYSTEM_PROMPT
from app.decision.providers.ollama_provider import OllamaDecisionProvider
from app.decision.schemas.decision import TASKS

OUTPUT_DIR = ARTIFACT_DIR / "llama3-8b-candidate"
PREDICTIONS_PATH = OUTPUT_DIR / "predictions.json"
CALIBRATOR_PATH = OUTPUT_DIR / "calibrator.json"
REPORT_PATH = OUTPUT_DIR / "evaluation_report.json"
REPORT_MD_PATH = OUTPUT_DIR / "evaluation_report.md"
VALIDATION_PREDICTIONS = ARTIFACT_DIR / "prompt_validation" / "validation_predictions.json"
BASELINE_PREDICTIONS = ARTIFACT_DIR / "llama3.2-3b" / "raw_predictions.json"
MODEL_NAME = "llama3:8b"


def run() -> dict:
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in dataset}
    stored = _load()
    _import_validation(stored, by_id)
    provider = OllamaDecisionProvider(model=MODEL_NAME)
    if provider.model_name != MODEL_NAME:
        raise SystemExit(f"Expected {MODEL_NAME}, got {provider.model_name}.")

    pending = [
        row
        for row in dataset
        if row["split"] in {"calibration", "test"} and not _has(stored, row["id"])
    ]
    print(
        f"[final] {MODEL_NAME} candidate prompt. "
        f"{len(pending)} calibration/test rows left. Validation rows are reused."
    )
    for index, record in enumerate(pending, start=1):
        print(f"[final] {index}/{len(pending)} {record['split']} {record['id']}")
        raw, output_valid = _classify_once(provider, CANDIDATE_SYSTEM_PROMPT, record["query"])
        stored.append(
            {
                "id": record["id"],
                "split": record["split"],
                "domain": record["domain"],
                "query": record["query"],
                "labels": record["labels"],
                "raw": raw,
                "output_valid": output_valid,
                "model": MODEL_NAME,
                "prompt": "candidate",
            }
        )
        _save(stored)

    predictions = [_ordered(stored, row) for row in dataset]
    calibration_rows = [
        row
        for row in predictions
        if row["split"] == "calibration" and row["output_valid"]
    ]
    validation_rows = [
        row
        for row in predictions
        if row["split"] == "validation" and row["output_valid"]
    ]
    test_rows = [row for row in predictions if row["split"] == "test" and row["output_valid"]]
    calibrator = fit_isotonic_calibrator(calibration_rows)
    calibrator.save(CALIBRATOR_PATH)

    validation_calibrated = [calibrator.calibrate(row["raw"]) for row in validation_rows]
    threshold_choice = select_threshold(validation_rows, validation_calibrated)
    test_calibrated = [calibrator.calibrate(row["raw"]) for row in test_rows]
    selected_threshold = threshold_choice["selected_threshold"]
    report = {
        "decision_model": f"ollama/{MODEL_NAME}",
        "prompt": "candidate",
        "live_prompt_changed": False,
        "live_model_changed": False,
        "calibration_rows": len(calibration_rows),
        "validation_rows": len(validation_rows),
        "test_rows": len(test_rows),
        "invalid_ids": [row["id"] for row in predictions if not row["output_valid"]],
        "validation_selected_threshold": selected_threshold,
        "validation_sweep": threshold_choice["sweep"],
        "deployed_threshold_unchanged": 0.55,
        "test_raw": _score(test_rows),
        "test_calibrated": _score(test_rows, test_calibrated),
        "baseline_test_raw": _score(_baseline_test()),
        "routing_at_selected_threshold": score_routing(
            test_rows,
            test_calibrated,
            selected_threshold,
        ),
        "note": (
            "The candidate prompt and llama3:8b were selected on the validation split. "
            "The calibrator was then fit on this model's calibration rows only. "
            "The threshold was selected on validation. The test split was scored once. "
            "The live llama3.2:3b prompt was not replaced, because that prompt cut simple recall on validation."
        ),
    }
    report["conclusion"] = _conclusion(report)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    REPORT_MD_PATH.write_text(_markdown(report), encoding="utf-8")
    print(report["conclusion"])
    print(f"Saved {REPORT_MD_PATH}")
    return report


def _import_validation(stored: list[dict], by_id: dict) -> None:
    if not VALIDATION_PREDICTIONS.exists():
        raise SystemExit(f"Missing {VALIDATION_PREDICTIONS}")
    rows = json.loads(VALIDATION_PREDICTIONS.read_text(encoding="utf-8"))
    for row in rows:
        if row["model"] != MODEL_NAME or row["prompt"] != "candidate":
            continue
        if _has(stored, row["id"]):
            continue
        source = by_id[row["id"]]
        if source["split"] != "validation":
            raise SystemExit(f"{row['id']} is not a validation row.")
        stored.append(
            {
                "id": row["id"],
                "split": source["split"],
                "domain": source["domain"],
                "query": source["query"],
                "labels": source["labels"],
                "raw": row["raw"],
                "output_valid": row["output_valid"],
                "model": MODEL_NAME,
                "prompt": "candidate",
            }
        )


def _baseline_test() -> list[dict]:
    rows = json.loads(BASELINE_PREDICTIONS.read_text(encoding="utf-8"))
    return [row for row in rows if row["split"] == "test" and row["output_valid"]]


def _score(records: list[dict], probability_rows: list[dict] | None = None) -> dict:
    if probability_rows is None:
        probability_rows = [row["raw"] for row in records]
    scores = {}
    for task, classes in TASKS.items():
        labels = [row["labels"][task] for row in records]
        probabilities = [row[task] for row in probability_rows]
        predictions = [max(classes, key=lambda name: probs[name]) for probs in probabilities]
        report = classification_report(labels, predictions, classes)
        scores[task] = {
            **report,
            "brier_score": brier_score(probabilities, labels, classes),
        }
    return scores


def _conclusion(report: dict) -> str:
    new = report["test_raw"]["complexity"]
    old = report["baseline_test_raw"]["complexity"]
    new_recall = _recall(new, "complex")
    old_recall = _recall(old, "complex")
    if new["accuracy"] > old["accuracy"] and new["macro_f1"] > old["macro_f1"] and new_recall > old_recall:
        verdict = "On the untouched test split, llama3:8b with the candidate prompt improves complexity accuracy, macro-F1, and complex recall over the llama3.2:3b baseline."
    else:
        verdict = "On the untouched test split, llama3:8b with the candidate prompt does not improve accuracy, macro-F1, and complex recall together over the llama3.2:3b baseline."
    return (
        f"{verdict} Accuracy {old['accuracy']} -> {new['accuracy']}. "
        f"Macro-F1 {old['macro_f1']} -> {new['macro_f1']}. "
        f"Complex recall {old_recall} -> {new_recall}."
    )


def _recall(scores: dict, label: str) -> float:
    for item in scores["per_class"]:
        if item["label"] == label:
            return item["recall"]
    return 0.0


def _markdown(report: dict) -> str:
    lines = [
        "# Selected model final evaluation",
        "",
        report["note"],
        "",
        f"Calibration rows used: {report['calibration_rows']}.",
        f"Validation rows used for the threshold: {report['validation_rows']}.",
        f"Test rows scored: {report['test_rows']}.",
        f"Invalid ids: {', '.join(report['invalid_ids']) or 'none'}.",
        f"Validation-selected threshold: {report['validation_selected_threshold']}.",
        "routing/rules.json was not changed.",
        "",
        "## Complexity on the test split",
        "",
        "| | Accuracy | Macro precision | Macro recall | Macro-F1 | Complex recall | Brier |",
        "|---|---:|---:|---:|---:|---:|---:|",
        _row("llama3.2:3b current, raw", report["baseline_test_raw"]["complexity"]),
        _row("llama3:8b candidate, raw", report["test_raw"]["complexity"]),
        _row("llama3:8b candidate, calibrated", report["test_calibrated"]["complexity"]),
        "",
        "Confusion rows are true simple, medium, complex.",
        "",
        f"Baseline raw: `{report['baseline_test_raw']['complexity']['confusion_matrix']['matrix']}`",
        "",
        f"8b candidate raw: `{report['test_raw']['complexity']['confusion_matrix']['matrix']}`",
        "",
        f"8b candidate calibrated: `{report['test_calibrated']['complexity']['confusion_matrix']['matrix']}`",
        "",
        "## Reasoning and context",
        "",
    ]
    for task in ("reasoning", "context"):
        lines.append(f"### {task}")
        lines.append("")
        lines.append("| | Accuracy | Macro-F1 | Brier |")
        lines.append("|---|---:|---:|---:|")
        for name, block in (
            ("3b current raw", report["baseline_test_raw"][task]),
            ("8b candidate raw", report["test_raw"][task]),
            ("8b candidate calibrated", report["test_calibrated"][task]),
        ):
            lines.append(
                f"| {name} | {block['accuracy']} | {block['macro_f1']} | {block['brier_score']} |"
            )
        lines.append("")
        lines.append(f"8b candidate raw confusion: `{report['test_raw'][task]['confusion_matrix']['matrix']}`")
        lines.append("")
    routing = report["routing_at_selected_threshold"]
    lines.extend(
        [
            "## Routing",
            "",
            f"At the validation-selected threshold {routing['threshold']}, "
            f"routing accuracy is {routing['routing_accuracy']} and the uncertain rate is {routing['uncertain_rate']}.",
            f"Selected tiers: {routing['selected_model_counts']}.",
            "",
            "## Conclusion",
            "",
            report["conclusion"],
            "",
        ]
    )
    return "\n".join(lines)


def _row(name: str, scores: dict) -> str:
    return (
        f"| {name} | {scores['accuracy']} | {scores['macro_precision']} | "
        f"{scores['macro_recall']} | {scores['macro_f1']} | {_recall(scores, 'complex')} | "
        f"{scores['brier_score']} |"
    )


def _ordered(stored: list[dict], record: dict) -> dict:
    for row in stored:
        if row["id"] == record["id"]:
            return row
    raise SystemExit(f"Missing prediction for {record['id']}")


def _load() -> list[dict]:
    if not PREDICTIONS_PATH.exists():
        return []
    return json.loads(PREDICTIONS_PATH.read_text(encoding="utf-8"))


def _save(rows: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PREDICTIONS_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _has(rows: list[dict], row_id: str) -> bool:
    return any(row["id"] == row_id for row in rows)


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    run()


if __name__ == "__main__":
    main()
