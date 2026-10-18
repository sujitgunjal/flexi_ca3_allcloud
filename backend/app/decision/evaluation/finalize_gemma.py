"""Fit and score gemma4:31b-cloud on the existing labeled dataset.

Writes only under calibration/artifacts/gemma4-31b-cloud/.
Does not modify dataset.json or any llama artifact.

The calibrator is fit on this model's calibration rows only.
The routing threshold is chosen on this model's validation rows only.
The test split is scored once after that choice.
"""

import json
import sys
import time

from app.decision.calibration.calibrator import fit_isotonic_calibrator
from app.decision.evaluation.finalize_selected import _baseline_test, _recall, _score
from app.decision.evaluation.prompt_experiment import _classify_once
from app.decision.evaluation.routing_eval import score_routing, select_threshold
from app.decision.paths import ARTIFACT_DIR, DATASET_PATH
from app.decision.prompts.candidate import CANDIDATE_SYSTEM_PROMPT
from app.decision.providers.ollama_provider import OllamaDecisionProvider

MODEL_NAME = "gemma4:31b-cloud"
OUTPUT_DIR = ARTIFACT_DIR / "gemma4-31b-cloud"
PREDICTIONS_PATH = OUTPUT_DIR / "predictions.json"
CALIBRATOR_PATH = OUTPUT_DIR / "calibrator.json"
REPORT_PATH = OUTPUT_DIR / "evaluation_report.json"
REPORT_MD_PATH = OUTPUT_DIR / "evaluation_report.md"
LLAMA_REPORT = ARTIFACT_DIR / "llama3-8b-candidate" / "evaluation_report.json"
PROTECTED_DIRS = {
    ARTIFACT_DIR / "llama3-8b-candidate",
    ARTIFACT_DIR / "llama3-8b",
    ARTIFACT_DIR / "llama3.2-3b",
    ARTIFACT_DIR / "prompt_validation",
}


def run() -> dict:
    if OUTPUT_DIR in PROTECTED_DIRS or OUTPUT_DIR == ARTIFACT_DIR:
        raise SystemExit(f"Refusing to write Gemma results into {OUTPUT_DIR}")
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    stored = [
        row for row in _load()
        if row.get("model") == MODEL_NAME and row.get("prompt") == "candidate"
    ]
    provider = OllamaDecisionProvider(model=MODEL_NAME)
    if provider.model_name != MODEL_NAME:
        raise SystemExit(f"Expected {MODEL_NAME}, got {provider.model_name}.")

    pending = [row for row in dataset if not _has(stored, row["id"])]
    print(f"[gemma] {len(pending)} rows left of {len(dataset)}. Output: {OUTPUT_DIR}")
    for index, record in enumerate(pending, start=1):
        print(f"[gemma] {index}/{len(pending)} {record['split']} {record['id']}")
        started = time.perf_counter()
        raw, output_valid = _classify_once(provider, CANDIDATE_SYSTEM_PROMPT, record["query"])
        usage = dict(getattr(provider, "last_call", {}) or {})
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
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "prompt_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("output_tokens"),
            }
        )
        _save(stored)

    predictions = [_ordered(stored, row) for row in dataset]
    calibration_rows = [row for row in predictions if row["split"] == "calibration" and row["output_valid"]]
    validation_rows = [row for row in predictions if row["split"] == "validation" and row["output_valid"]]
    test_rows = [row for row in predictions if row["split"] == "test" and row["output_valid"]]
    calibrator = fit_isotonic_calibrator(calibration_rows)
    calibrator.artifact["model"] = MODEL_NAME
    calibrator.artifact["split"] = "calibration"
    calibrator.artifact["rows"] = len(calibration_rows)
    calibrator.save(CALIBRATOR_PATH)

    validation_calibrated = [calibrator.calibrate(row["raw"]) for row in validation_rows]
    threshold_choice = select_threshold(validation_rows, validation_calibrated)
    selected_threshold = threshold_choice["selected_threshold"]
    test_calibrated = [calibrator.calibrate(row["raw"]) for row in test_rows]
    llama_report = json.loads(LLAMA_REPORT.read_text(encoding="utf-8")) if LLAMA_REPORT.exists() else {}
    report = {
        "decision_model": f"ollama/{MODEL_NAME}",
        "prompt": "candidate",
        "calibration_rows": len(calibration_rows),
        "validation_rows": len(validation_rows),
        "test_rows": len(test_rows),
        "invalid_ids": [row["id"] for row in predictions if not row["output_valid"]],
        "validation_selected_threshold": selected_threshold,
        "validation_sweep": threshold_choice["sweep"],
        "test_raw": _score(test_rows),
        "test_calibrated": _score(test_rows, test_calibrated),
        "llama3_8b_candidate_test_raw": llama_report.get("test_raw"),
        "llama3_8b_candidate_test_calibrated": llama_report.get("test_calibrated"),
        "baseline_test_raw": _score(_baseline_test()),
        "routing_at_selected_threshold": score_routing(test_rows, test_calibrated, selected_threshold),
        "latency": _latency_summary(predictions),
        "tokens": _token_summary(predictions),
        "estimated_cost": None,
        "cost_note": (
            "Ollama does not return a dollar cost for gemma4:31b-cloud. "
            "Token counts are prompt_eval_count and eval_count when the provider sent them."
        ),
        "note": (
            "gemma4:31b-cloud was scored with the existing candidate prompt and labeled dataset. "
            "The calibrator was fit on this model's calibration rows only. "
            "The threshold was selected on this model's validation rows only. "
            "The test split was scored once. Llama predictions and calibrators were not reused."
        ),
    }
    report["conclusion"] = _conclusion(report)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    REPORT_MD_PATH.write_text(_markdown(report), encoding="utf-8")
    print(report["conclusion"])
    print(f"Selected threshold: {selected_threshold}")
    print(f"Saved {REPORT_MD_PATH}")
    return report


def _conclusion(report: dict) -> str:
    new = report["test_calibrated"]["complexity"]
    old = (report.get("llama3_8b_candidate_test_calibrated") or {}).get("complexity")
    if not old:
        return "Gemma test metrics were scored. No llama3:8b candidate report was available for comparison."
    return (
        "On the untouched test split, calibrated gemma4:31b-cloud "
        f"accuracy is {new['accuracy']} against calibrated llama3:8b {old['accuracy']}. "
        f"Macro-F1 {old['macro_f1']} -> {new['macro_f1']}. "
        f"Complex recall {_recall(old, 'complex')} -> {_recall(new, 'complex')}."
    )


def _latency_summary(rows: list[dict]) -> dict | None:
    values = sorted(float(row["latency_ms"]) for row in rows if row.get("latency_ms") is not None)
    if not values:
        return None
    return {
        "count": len(values),
        "mean_ms": round(sum(values) / len(values), 2),
        "median_ms": _percentile(values, 50),
        "p95_ms": _percentile(values, 95),
    }


def _token_summary(rows: list[dict]) -> dict:
    prompt = [row.get("prompt_tokens") for row in rows if isinstance(row.get("prompt_tokens"), int)]
    output = [row.get("output_tokens") for row in rows if isinstance(row.get("output_tokens"), int)]
    return {
        "rows_with_prompt_tokens": len(prompt),
        "rows_with_output_tokens": len(output),
        "prompt_tokens": sum(prompt),
        "output_tokens": sum(output),
    }


def _percentile(values: list[float], percentile: int) -> float:
    index = min(len(values) - 1, max(0, round((percentile / 100) * (len(values) - 1))))
    return values[index]


def _markdown(report: dict) -> str:
    latency = report["latency"] or {}
    tokens = report["tokens"]
    lines = [
        "# gemma4:31b-cloud decision evaluation",
        "",
        report["note"],
        "",
        f"Calibration rows used: {report['calibration_rows']}.",
        f"Validation rows used for the threshold: {report['validation_rows']}.",
        f"Test rows scored: {report['test_rows']}.",
        f"Invalid ids: {', '.join(report['invalid_ids']) or 'none'}.",
        f"Validation-selected threshold: {report['validation_selected_threshold']}.",
        "",
        "## Latency and tokens",
        "",
        f"Mean {latency.get('mean_ms')} ms, median {latency.get('median_ms')} ms, p95 {latency.get('p95_ms')} ms.",
        f"Prompt tokens {tokens['prompt_tokens']}, output tokens {tokens['output_tokens']}.",
        report["cost_note"],
        "",
        "## Complexity on the test split",
        "",
        "| | Accuracy | Macro precision | Macro recall | Macro-F1 | Complex recall | Brier |",
        "|---|---:|---:|---:|---:|---:|---:|",
        _metric_row("gemma raw", report["test_raw"]["complexity"]),
        _metric_row("gemma calibrated", report["test_calibrated"]["complexity"]),
        "",
        "## Conclusion",
        "",
        report["conclusion"],
        "",
    ]
    return "\n".join(lines)


def _metric_row(name: str, scores: dict) -> str:
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
