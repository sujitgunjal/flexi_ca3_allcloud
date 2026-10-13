"""Compare the live decision prompt with a candidate on the validation split.

Does not read the test split, fit a calibrator, or write the existing artifact files.
llama3.2:3b with the current prompt is taken from the archived predictions.
"""

import json
import sys
import time

from app.decision.evaluation.metrics import classification_report
from app.decision.paths import ARTIFACT_DIR, DATASET_PATH
from app.decision.prompts.candidate import CANDIDATE_SYSTEM_PROMPT
from app.decision.providers.ollama_provider import SYSTEM_PROMPT, OllamaDecisionProvider
from app.decision.schemas.decision import TASKS
from app.decision.service import _uniform_distributions
from app.decision.validation.probability_validator import (
    ProbabilityValidationError,
    parse_model_output,
)

OUTPUT_DIR = ARTIFACT_DIR / "prompt_validation"
PREDICTIONS_PATH = OUTPUT_DIR / "validation_predictions.json"
REPORT_PATH = OUTPUT_DIR / "validation_report.json"
REPORT_MD_PATH = OUTPUT_DIR / "validation_report.md"
BASELINE_PREDICTIONS = ARTIFACT_DIR / "llama3.2-3b" / "raw_predictions.json"
BASELINE_MODEL = "llama3.2:3b"
ALTERNATIVE_MODEL = "llama3:8b"

# A gain of two complex validation rows, without giving back macro-F1 or another class.
MIN_COMPLEX_RECALL_GAIN = 0.12
MAX_MACRO_F1_DROP = 0.02
MAX_OTHER_RECALL_DROP = 0.15


def run() -> dict:
    _reject_leaked_examples()
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    validation_rows = [row for row in dataset if row["split"] == "validation"]
    if len(validation_rows) != 48:
        raise SystemExit(f"Expected 48 validation rows, found {len(validation_rows)}.")
    if any(row["split"] == "test" for row in validation_rows):
        raise SystemExit("Refusing to score test rows in prompt development.")

    stored = [
        row
        for row in _load_predictions()
        if not (row["model"] == BASELINE_MODEL and row["prompt"] == "current")
    ]
    stored.extend(_baseline_rows(validation_rows))
    conditions = (
        (BASELINE_MODEL, "candidate", CANDIDATE_SYSTEM_PROMPT),
        (ALTERNATIVE_MODEL, "current", SYSTEM_PROMPT),
        (ALTERNATIVE_MODEL, "candidate", CANDIDATE_SYSTEM_PROMPT),
    )
    for model_name, prompt_name, prompt in conditions:
        provider = OllamaDecisionProvider(model=model_name)
        for index, record in enumerate(validation_rows, start=1):
            key = (model_name, prompt_name, record["id"])
            if _has(stored, key):
                continue
            print(f"[prompt] {model_name} {prompt_name} {index}/48 {record['id']}")
            stored.append(_classify(provider, prompt_name, prompt, record))
            _save(stored)

    report = _report(stored, validation_rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _save(stored)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    REPORT_MD_PATH.write_text(_markdown(report), encoding="utf-8")
    print(report["decision"])
    print(f"Saved {REPORT_MD_PATH}")
    return report


def _classify(
    provider: OllamaDecisionProvider,
    prompt_name: str,
    prompt: str,
    record: dict,
) -> dict:
    started = time.perf_counter()
    raw, output_valid = _classify_once(provider, prompt, record["query"])
    return {
        "id": record["id"],
        "model": provider.model_name,
        "prompt": prompt_name,
        "labels": record["labels"],
        "raw": raw,
        "output_valid": output_valid,
        "latency_seconds": round(time.perf_counter() - started, 4),
    }


def _classify_once(
    provider: OllamaDecisionProvider,
    prompt: str,
    query: str,
) -> tuple[dict, bool]:
    text = provider.classify_raw(query, system_prompt=prompt)
    try:
        return parse_model_output(text), True
    except ProbabilityValidationError as exc:
        text = provider.classify_raw(
            query,
            system_prompt=prompt,
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


def _baseline_rows(validation_rows: list[dict]) -> list[dict]:
    if not BASELINE_PREDICTIONS.exists():
        raise SystemExit(f"Missing {BASELINE_PREDICTIONS}")
    archived = json.loads(BASELINE_PREDICTIONS.read_text(encoding="utf-8"))
    by_id = {
        row["id"]: row
        for row in archived
        if row["split"] == "validation"
    }
    rows = []
    for record in validation_rows:
        archived_row = by_id.get(record["id"])
        if archived_row is None:
            raise SystemExit(f"Archived baseline is missing validation row {record['id']}")
        rows.append(
            {
                "id": record["id"],
                "model": BASELINE_MODEL,
                "prompt": "current",
                "labels": record["labels"],
                "raw": archived_row["raw"],
                "output_valid": archived_row["output_valid"],
                "latency_seconds": None,
            }
        )
    return rows


def _report(stored: list[dict], validation_rows: list[dict]) -> dict:
    conditions = []
    for model_name, prompt_name in (
        (BASELINE_MODEL, "current"),
        (BASELINE_MODEL, "candidate"),
        (ALTERNATIVE_MODEL, "current"),
        (ALTERNATIVE_MODEL, "candidate"),
    ):
        rows = [
            row
            for row in stored
            if row["model"] == model_name and row["prompt"] == prompt_name
        ]
        if len(rows) != len(validation_rows):
            raise SystemExit(
                f"{model_name} {prompt_name} has {len(rows)} rows, expected {len(validation_rows)}."
            )
        valid = [row for row in rows if row["output_valid"]]
        conditions.append(
            {
                "model": model_name,
                "prompt": prompt_name,
                "count": len(rows),
                "invalid_outputs": len(rows) - len(valid),
                "invalid_ids": [row["id"] for row in rows if not row["output_valid"]],
                "tasks": _score(valid),
            }
        )

    baseline = conditions[0]
    decision = _decide(baseline, conditions[1:])
    return {
        "split": "validation",
        "rows": len(validation_rows),
        "test_split_used": False,
        "calibrator_refit": False,
        "rationale": (
            "The live prompt defines the three class names and shows only a simple arithmetic example. "
            "On the archived llama3.2:3b validation predictions, most complex questions were labeled simple or medium. "
            "llama3:8b previously labeled every held-out complex question as medium. "
            "Those errors follow from a missing boundary, so a rubric and four class examples may correct them. "
            "The examples are new and are not validation or test rows."
        ),
        "conditions": conditions,
        "decision": decision,
    }


def _score(rows: list[dict]) -> dict:
    scores = {}
    for task, classes in TASKS.items():
        labels = [row["labels"][task] for row in rows]
        predictions = [
            max(classes, key=lambda name: row["raw"][task][name])
            for row in rows
        ]
        report = classification_report(labels, predictions, classes)
        scores[task] = {
            "accuracy": report["accuracy"],
            "macro_precision": report["macro_precision"],
            "macro_recall": report["macro_recall"],
            "macro_f1": report["macro_f1"],
            "per_class_recall": {
                item["label"]: item["recall"] for item in report["per_class"]
            },
            "confusion_matrix": report["confusion_matrix"],
            "support": len(rows),
        }
    return scores


def _decide(baseline: dict, others: list[dict]) -> str:
    base = baseline["tasks"]["complexity"]
    adoptable = []
    for condition in others:
        complexity = condition["tasks"]["complexity"]
        if _is_meaningful(base, complexity, baseline, condition):
            adoptable.append(condition)

    if not adoptable:
        return (
            "No candidate prompt or alternative model beat llama3.2:3b with the current prompt "
            "on validation complexity. The live prompt stays unchanged."
        )

    selected = max(
        adoptable,
        key=lambda condition: (
            condition["tasks"]["complexity"]["per_class_recall"]["complex"],
            condition["tasks"]["complexity"]["macro_f1"],
            -condition["invalid_outputs"],
        ),
    )
    return (
        f"Selected {selected['model']} with the {selected['prompt']} prompt on validation. "
        f"Complex recall {base['per_class_recall']['complex']} -> "
        f"{selected['tasks']['complexity']['per_class_recall']['complex']}, "
        f"macro-F1 {base['macro_f1']} -> {selected['tasks']['complexity']['macro_f1']}."
    )


def _is_meaningful(base: dict, candidate: dict, base_condition: dict, candidate_condition: dict) -> bool:
    complex_gain = candidate["per_class_recall"]["complex"] - base["per_class_recall"]["complex"]
    if complex_gain < MIN_COMPLEX_RECALL_GAIN:
        return False
    if candidate["macro_f1"] < base["macro_f1"] - MAX_MACRO_F1_DROP:
        return False
    for label in ("simple", "medium"):
        if candidate["per_class_recall"][label] < base["per_class_recall"][label] - MAX_OTHER_RECALL_DROP:
            return False
    if candidate_condition["invalid_outputs"] > base_condition["invalid_outputs"] + 2:
        return False
    return True


def _markdown(report: dict) -> str:
    lines = [
        "# Validation prompt experiment",
        "",
        report["rationale"],
        "",
        "Scores use raw class labels on the validation split. The test split was not read.",
        "The calibrator was not fit. llama3.2:3b with the current prompt is the archived baseline.",
        "",
        f"Adoption rule: complex recall must rise by at least {MIN_COMPLEX_RECALL_GAIN}, "
        f"macro-F1 may fall by at most {MAX_MACRO_F1_DROP}, and simple or medium recall "
        f"may fall by at most {MAX_OTHER_RECALL_DROP}.",
        "",
        "## Complexity",
        "",
        "| Model | Prompt | Accuracy | Macro-F1 | Simple recall | Medium recall | Complex recall | Invalid |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for condition in report["conditions"]:
        complexity = condition["tasks"]["complexity"]
        recall = complexity["per_class_recall"]
        lines.append(
            f"| {condition['model']} | {condition['prompt']} | {complexity['accuracy']} | "
            f"{complexity['macro_f1']} | {recall['simple']} | {recall['medium']} | "
            f"{recall['complex']} | {condition['invalid_outputs']} |"
        )
    lines.extend(["", "Confusion matrices are rows = true label, columns = simple, medium, complex.", ""])
    for condition in report["conditions"]:
        matrix = condition["tasks"]["complexity"]["confusion_matrix"]["matrix"]
        lines.append(
            f"- `{condition['model']}` / `{condition['prompt']}`: `{matrix}`"
        )
    lines.extend(["", "## Other decisions", ""])
    for task in ("reasoning", "context"):
        lines.append(f"### {task}")
        lines.append("")
        lines.append("| Model | Prompt | Accuracy | Macro-F1 | Low recall | Medium recall | High recall |")
        lines.append("|---|---|---:|---:|---:|---:|---:|")
        for condition in report["conditions"]:
            scores = condition["tasks"][task]
            recall = scores["per_class_recall"]
            lines.append(
                f"| {condition['model']} | {condition['prompt']} | {scores['accuracy']} | "
                f"{scores['macro_f1']} | {recall['low']} | {recall['medium']} | {recall['high']} |"
            )
        lines.append("")
    lines.extend(["## Decision", "", report["decision"], ""])
    return "\n".join(lines)


def _reject_leaked_examples() -> None:
    dataset = DATASET_PATH.read_text(encoding="utf-8").lower()
    needles = (
        "what is a quorum in a distributed system",
        "what filename did i tell you to edit",
        "words in a sentence that appear more than once",
        "a checkout service saves the order and then charges the card",
    )
    leaked = [needle for needle in needles if needle in dataset]
    if leaked:
        raise SystemExit(f"Candidate examples appear in the dataset: {leaked}")


def _load_predictions() -> list[dict]:
    if not PREDICTIONS_PATH.exists():
        return []
    return json.loads(PREDICTIONS_PATH.read_text(encoding="utf-8"))


def _save(rows: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PREDICTIONS_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _has(rows: list[dict], key: tuple[str, str, str]) -> bool:
    model_name, prompt_name, row_id = key
    return any(
        row["model"] == model_name and row["prompt"] == prompt_name and row["id"] == row_id
        for row in rows
    )


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    run()


if __name__ == "__main__":
    main()
