import json
import sys
from collections import Counter, defaultdict

from app.decision.calibration.calibrator import ProbabilityCalibrator
from app.decision.evaluation.diagram import render_reliability_svg
from app.decision.evaluation.metrics import score_split, suggest_threshold
from app.decision.evaluation.report_text import render_markdown
from app.decision.evaluation.routing_eval import gold_model, score_routing, select_threshold
from app.decision.paths import (
    DATASET_PATH,
    DIAGRAM_PATH,
    PREDICTIONS_PATH,
    REPORT_MD_PATH,
    REPORT_PATH,
    RULES_PATH,
)
from app.decision.providers.ollama_provider import OllamaDecisionProvider
from app.decision.schemas.decision import TASKS


def evaluate() -> dict:
    if not PREDICTIONS_PATH.exists():
        raise SystemExit(
            "No raw predictions found. Run python -m app.decision.calibration.trainer first."
        )

    predictions = json.loads(PREDICTIONS_PATH.read_text(encoding="utf-8"))
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    deployed_threshold = float(rules["confidence_threshold"])

    validation_rows = _valid(predictions, "validation")
    test_rows = _valid(predictions, "test")
    if not test_rows:
        raise SystemExit("The final test split has no valid predictions.")

    calibrator = ProbabilityCalibrator.load()
    # Threshold is chosen here, before any test metric is computed.
    validation_calibrated = [
        calibrator.calibrate(item["raw"]) for item in validation_rows
    ]
    threshold_choice = select_threshold(validation_rows, validation_calibrated)
    selected_threshold = threshold_choice["selected_threshold"]
    complexity_threshold = _complexity_threshold(validation_rows, validation_calibrated)

    test_calibrated = [calibrator.calibrate(item["raw"]) for item in test_rows]
    provider = OllamaDecisionProvider()
    report = {
        "decision_model": f"ollama/{provider.model_name}",
        "split": "test",
        "count": len(test_rows),
        "invalid_outputs": sum(1 for item in predictions if not item["output_valid"]),
        "invalid_ids": [item["id"] for item in predictions if not item["output_valid"]],
        "calibration_rows": sum(
            1
            for item in predictions
            if item["split"] == "calibration" and item["output_valid"]
        ),
        "calibration_applied": calibrator.fitted,
        "dataset": _dataset_summary(dataset),
        "note": (
            "Classification and routing scores use only the final test split. "
            "The isotonic calibrator was fit on the calibration split. "
            "The confidence threshold was selected on the validation split. "
            "Neither step looked at the test labels."
        ),
        "tasks": score_split(test_rows, test_calibrated),
        "suggested_confidence_threshold": complexity_threshold,
        "routing": {
            "validation_selected_threshold": selected_threshold,
            "validation_sweep": threshold_choice["sweep"],
            "deployed_threshold": deployed_threshold,
            "gold_model_counts": dict(Counter(gold_model(row["labels"]) for row in test_rows)),
            "raw_at_selected_threshold": score_routing(
                test_rows,
                [row["raw"] for row in test_rows],
                selected_threshold,
            ),
            "calibrated_at_selected_threshold": score_routing(
                test_rows,
                test_calibrated,
                selected_threshold,
            ),
            "raw_at_deployed_threshold": score_routing(
                test_rows,
                [row["raw"] for row in test_rows],
                deployed_threshold,
            ),
            "calibrated_at_deployed_threshold": score_routing(
                test_rows,
                test_calibrated,
                deployed_threshold,
            ),
        },
        "errors": _errors(test_rows, test_calibrated),
    }
    report["recommendation_summary"] = _recommendations(report)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    REPORT_MD_PATH.write_text(render_markdown(report), encoding="utf-8")
    DIAGRAM_PATH.write_text(
        render_reliability_svg(report["tasks"]),
        encoding="utf-8",
    )
    _print_report(report)
    print(f"\nSaved {REPORT_PATH}")
    print(f"Saved {REPORT_MD_PATH}")
    print(f"Saved {DIAGRAM_PATH}")
    return report


def _complexity_threshold(records: list[dict], calibrated_rows: list[dict]) -> float:
    """Lowest validation threshold whose complexity accuracy is at least 0.75."""

    classes = TASKS["complexity"]
    confidences = []
    correct = []
    for record, calibrated in zip(records, calibrated_rows):
        probabilities = calibrated["complexity"]
        prediction = max(classes, key=lambda name: probabilities[name])
        confidences.append(probabilities[prediction])
        correct.append(prediction == record["labels"]["complexity"])
    return suggest_threshold(confidences, correct)


def _valid(predictions: list[dict], split: str) -> list[dict]:
    return [
        item
        for item in predictions
        if item["split"] == split and item["output_valid"]
    ]


def _dataset_summary(rows: list[dict]) -> dict:
    return {
        "rows": len(rows),
        "splits": dict(Counter(row["split"] for row in rows)),
        "complexity": dict(Counter(row["labels"]["complexity"] for row in rows)),
        "domains": dict(Counter(row["domain"] for row in rows)),
        "complexity_by_reasoning": _crosstab(rows, "reasoning"),
        "complexity_by_context": _crosstab(rows, "context"),
    }


def _crosstab(rows: list[dict], other: str) -> dict:
    table = {}
    for complexity in TASKS["complexity"]:
        table[complexity] = dict(
            Counter(
                row["labels"][other]
                for row in rows
                if row["labels"]["complexity"] == complexity
            )
        )
    return table


def _errors(records: list[dict], calibrated_rows: list[dict]) -> dict:
    report = {}
    for task, classes in TASKS.items():
        counts: Counter = Counter()
        examples: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for record, probabilities in zip(records, calibrated_rows):
            truth = record["labels"][task]
            predicted = max(classes, key=lambda name: probabilities[task][name])
            if truth == predicted:
                continue
            key = (truth, predicted)
            counts[key] += 1
            if len(examples[key]) < 3:
                query = record["query"]
                if len(query) > 160:
                    query = query[:157] + "..."
                examples[key].append({"id": record["id"], "query": query})
        report[task] = {
            "pairs": [
                {
                    "true": truth,
                    "predicted": predicted,
                    "count": count,
                    "examples": examples[(truth, predicted)],
                }
                for (truth, predicted), count in counts.most_common()
            ]
        }
    return report


def _recommendations(report: dict) -> str:
    sentences = [
        "Keep llama3.2:3b as the decision model. Do not treat the calibrator as training.",
    ]
    for task, scores in report["tasks"].items():
        raw = scores["raw"]
        calibrated = scores["calibrated"]
        if calibrated["brier_score"] < raw["brier_score"]:
            sentences.append(
                f"On {task}, calibration lowered the Brier score from "
                f"{raw['brier_score']} to {calibrated['brier_score']}, so the probabilities are closer to the observed frequencies."
            )
        elif calibrated["brier_score"] > raw["brier_score"]:
            sentences.append(
                f"On {task}, calibration raised the Brier score from "
                f"{raw['brier_score']} to {calibrated['brier_score']}. The class ranking should be fixed in the prompt or the model before trusting the map."
            )
        if calibrated["accuracy"] <= raw["accuracy"]:
            sentences.append(
                f"On {task}, calibrated accuracy ({calibrated['accuracy']}) is not higher than raw accuracy ({raw['accuracy']})."
            )

    context_matrix = report["tasks"]["context"]["calibrated"]["confusion_matrix"]
    predicted_totals = [
        sum(row[column] for row in context_matrix["matrix"])
        for column in range(len(context_matrix["labels"]))
    ]
    if predicted_totals.count(0) >= len(predicted_totals) - 1:
        only = context_matrix["labels"][predicted_totals.index(max(predicted_totals))]
        sentences.append(
            f"Every calibrated context prediction on the test split is {only}. "
            "Accuracy can rise because that class is common, while macro-F1 falls because the other classes are never selected. "
            "The map adjusted probabilities toward the majority class. It did not learn to read phrases such as 'you just wrote'."
        )

    top = report["errors"]["complexity"]["pairs"][:1]
    if top:
        pair = top[0]
        sentences.append(
            f"The most common complexity mistake is true {pair['true']} predicted as {pair['predicted']} ({pair['count']} test rows). "
            "Add two or three of those boundary cases to the decision prompt as labeled examples."
        )
    reasoning_top = report["errors"]["reasoning"]["pairs"][:1]
    if reasoning_top:
        pair = reasoning_top[0]
        sentences.append(
            f"The most common reasoning mistake is true {pair['true']} predicted as {pair['predicted']} ({pair['count']} test rows)."
        )

    sweep = report["routing"]["validation_sweep"]
    best_accuracy = max(row["routing_accuracy"] for row in sweep)
    best_rows = [row for row in sweep if row["routing_accuracy"] == best_accuracy]
    lowest_uncertain = min(row["uncertain_rate"] for row in best_rows)
    tied = [
        str(row["threshold"])
        for row in best_rows
        if row["uncertain_rate"] == lowest_uncertain
    ]
    deployed = report["routing"]["calibrated_at_deployed_threshold"]
    deployed_validation = next(
        row for row in sweep if row["threshold"] == report["routing"]["deployed_threshold"]
    )
    sentences.append(
        f"On the validation sweep, threshold(s) {', '.join(tied)} lead "
        f"with routing accuracy {best_accuracy} and fallback rate {lowest_uncertain}. "
        f"At the deployed {report['routing']['deployed_threshold']} threshold, "
        f"validation fallback is {deployed_validation['uncertain_rate']}, "
        f"and the test fallback rate is {deployed['uncertain_rate']}. "
        "That drop is a confidence cutoff, not a change in the Ollama class."
    )

    selected = report["routing"]["calibrated_at_selected_threshold"]
    if selected["uncertain_rate"] >= 0.25:
        sentences.append(
            f"At the validation-selected threshold, {selected['uncertain_rate']} of test rows fall back because complexity confidence is low. "
            "That is a threshold effect, not evidence that the class label changed."
        )
    sentences.append(
        "Copy the validation-selected threshold into routing/rules.json only after reading the validation sweep. "
        "Do not retune it on the test split."
    )
    return " ".join(sentences)


def _print_report(report: dict) -> None:
    print("========== TEST SET: RAW VS CALIBRATED ==========")
    print(f"Decision model: {report['decision_model']}")
    print(f"Examples: {report['count']}")
    print(
        "Validation-selected threshold: "
        f"{report['routing']['validation_selected_threshold']}"
    )

    for task, scores in report["tasks"].items():
        raw = scores["raw"]
        calibrated = scores["calibrated"]
        print(f"\n{task}")
        print(
            f"  raw        accuracy={raw['accuracy']} "
            f"f1={raw['macro_f1']} brier={raw['brier_score']}"
        )
        print(
            f"  calibrated accuracy={calibrated['accuracy']} "
            f"f1={calibrated['macro_f1']} brier={calibrated['brier_score']}"
        )
        print(f"  raw confusion={raw['confusion_matrix']['matrix']}")
        print(f"  calibrated confusion={calibrated['confusion_matrix']['matrix']}")

    routing = report["routing"]["calibrated_at_selected_threshold"]
    print(
        f"\nCalibrated routing accuracy={routing['routing_accuracy']} "
        f"uncertain_rate={routing['uncertain_rate']} "
        f"tiers={routing['selected_model_counts']}"
    )


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    evaluate()


if __name__ == "__main__":
    main()
