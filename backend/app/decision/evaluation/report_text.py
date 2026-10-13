"""Turn the test-set report into a short markdown write-up."""

from app.decision.schemas.decision import TASKS


ADVICE = {
    ("complexity", "simple", "medium"): "Treat one-step lookups, definitions, and yes-or-no checks as simple even when the topic is technical.",
    ("complexity", "simple", "complex"): "A question that points at an earlier message can still be simple. Context is a separate decision.",
    ("complexity", "medium", "simple"): "A short snippet, comparison, or multi-step procedure is medium, not a single lookup.",
    ("complexity", "medium", "complex"): "A comparison or a small fix is medium. Reserve complex for a design, a proof, or a cross-component diagnosis.",
    ("complexity", "complex", "medium"): "Designs, proofs, and failure-mode recommendations are complex even when the question is self-contained.",
    ("complexity", "complex", "simple"): "Length is not the signal. A design or derivation is complex even if some sentences look like definitions.",
    ("reasoning", "low", "medium"): "Recall and direct lookup are low reasoning. Applying a procedure is medium.",
    ("reasoning", "low", "high"): "Naming a fact is low reasoning. Deriving or diagnosing is high.",
    ("reasoning", "medium", "low"): "A comparison or a known procedure is medium reasoning, not pure recall.",
    ("reasoning", "medium", "high"): "A constrained comparison can be medium. High reasoning needs a derivation, a diagnosis, or a design.",
    ("reasoning", "high", "medium"): "Proofs, diagnoses, and designs are high reasoning even when they use a familiar method.",
    ("reasoning", "high", "low"): "A deduction is high reasoning even when the question is short.",
    ("context", "low", "medium"): "If the question contains the facts it needs, context is low.",
    ("context", "low", "high"): "Self-contained designs are low context. High context requires an earlier turn.",
    ("context", "medium", "low"): "A question that still needs one fact from an earlier turn is not low context.",
    ("context", "medium", "high"): "Medium context means the main task is in the question and only one piece is missing.",
    ("context", "high", "low"): "Phrases such as 'you just wrote' or 'the port I asked for' are high context.",
    ("context", "high", "medium"): "If the question cannot be answered without the earlier turn, context is high rather than medium.",
}


def render_markdown(report: dict) -> str:
    lines = [
        "# Decision evaluation",
        "",
        f"Decision model: `{report['decision_model']}`.",
        "The paid Jev API was not called.",
        "",
        report["note"],
        "",
        "Calibration fits a post-hoc isotonic map from raw probabilities to observed frequencies.",
        "It does not train the Ollama model, and it does not change a predicted class when the class ranking stays the same.",
        "A higher calibrated accuracy is possible only when renormalization changes an argmax.",
        "Better class accuracy needs a prompt change or a different decision model.",
        "",
        "## Dataset",
        "",
        f"Rows: {report['dataset']['rows']}.",
        f"Splits: calibration {report['dataset']['splits'].get('calibration', 0)}, "
        f"validation {report['dataset']['splits'].get('validation', 0)}, "
        f"test {report['dataset']['splits'].get('test', 0)}.",
        f"Complexity: {report['dataset']['complexity']}.",
        f"Invalid model outputs excluded from scores: {report['invalid_outputs']} ({', '.join(report['invalid_ids']) or 'none'}).",
        "Those rows made the model return all-zero probabilities for reasoning and context.",
        "The validator rejected them after one correction retry.",
        "",
        "Label criteria are in `calibration/LABELING.md`.",
        "Labels were assigned from those criteria and checked against the wording.",
        "They were not copied from this model's predictions.",
        "",
        "### Complexity by reasoning",
        "",
        _table(report["dataset"]["complexity_by_reasoning"], TASKS["reasoning"]),
        "",
        "### Complexity by context",
        "",
        _table(report["dataset"]["complexity_by_context"], TASKS["context"]),
        "",
        "## Test classification",
        "",
        f"Scored test rows: {report['count']}. These scores use only the test split.",
        f"The calibrator was fit on {report['calibration_rows']} calibration rows.",
        "",
        "| Task | Raw accuracy | Calibrated accuracy | Raw macro-F1 | Calibrated macro-F1 | Raw Brier | Calibrated Brier |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for task, scores in report["tasks"].items():
        raw = scores["raw"]
        calibrated = scores["calibrated"]
        lines.append(
            f"| {task} | {raw['accuracy']} | {calibrated['accuracy']} | "
            f"{raw['macro_f1']} | {calibrated['macro_f1']} | "
            f"{raw['brier_score']} | {calibrated['brier_score']} |"
        )

    lines.extend(["", "Confusion matrices are rows = true label, columns = prediction, in class order.", ""])
    for task, scores in report["tasks"].items():
        classes = ", ".join(scores["raw"]["confusion_matrix"]["labels"])
        lines.append(f"### {task}")
        lines.append("")
        lines.append(f"Class order: {classes}.")
        lines.append("")
        lines.append(f"Raw: `{scores['raw']['confusion_matrix']['matrix']}`")
        lines.append("")
        lines.append(f"Calibrated: `{scores['calibrated']['confusion_matrix']['matrix']}`")
        lines.append("")
        lines.append("Reliability bins (calibrated confidence vs accuracy):")
        lines.append("")
        lines.append("| Bin | Count | Mean confidence | Accuracy |")
        lines.append("|---|---:|---:|---:|")
        for bin_row in scores["calibrated"]["reliability"]:
            lines.append(
                f"| {bin_row['lower']}-{bin_row['upper']} | {bin_row['count']} | "
                f"{_blank(bin_row['mean_confidence'])} | {_blank(bin_row['accuracy'])} |"
            )
        lines.append("")

    routing = report["routing"]
    lines.extend(
        [
            "## Routing",
            "",
            "The reference tier applies `routing/policy.py` to the true labels at full confidence:",
            "complex or high reasoning selects `strong`, simple with low reasoning selects `local`, otherwise `cheap`.",
            "Context does not change the tier.",
            "A low calibrated confidence uses the uncertain fallback (`cheap`).",
            "",
            f"The lowest validation threshold with complexity accuracy at least 0.75 is `{report['suggested_confidence_threshold']}`.",
            "Validation routing sweep (calibrated probabilities, validation split only):",
            "",
            "| Threshold | Routing accuracy | Uncertain rate |",
            "|---:|---:|---:|",
        ]
    )
    lines.extend(
        f"| {row['threshold']} | {row['routing_accuracy']} | {row['uncertain_rate']} |"
        for row in routing["validation_sweep"]
    )
    lines.extend(
        [
            "",
            f"Validation selected threshold `{routing['validation_selected_threshold']}` "
            "by routing accuracy on the validation split only. "
            "Ties prefer fewer fallbacks, then the candidate closest to 0.55.",
            f"`routing/rules.json` was left at `{routing['deployed_threshold']}` "
            "so this run does not change live traffic.",
            "The test numbers below use the validation-selected threshold.",
            "The deployed threshold is shown only as a comparison. The test split was not used to choose either value.",
            "",
            "| Probabilities | Threshold | Routing accuracy | Uncertain rate | Selected tiers |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for name in (
        "raw_at_selected_threshold",
        "calibrated_at_selected_threshold",
        "raw_at_deployed_threshold",
        "calibrated_at_deployed_threshold",
    ):
        row = routing[name]
        lines.append(
            f"| {name} | {row['threshold']} | {row['routing_accuracy']} | "
            f"{row['uncertain_rate']} | {row['selected_model_counts']} |"
        )

    lines.extend(
        [
            "",
            f"Gold tier counts on the test split: {routing['gold_model_counts']}.",
            "",
            "Calibrated routing confusion at the validation-selected threshold "
            "(rows = gold tier, columns = local, cheap, strong):",
            "",
            f"`{routing['calibrated_at_selected_threshold']['confusion_matrix']['matrix']}`",
            "",
            "## Common mistakes on the test split",
            "",
        ]
    )
    for task, block in report["errors"].items():
        lines.append(f"### {task}")
        lines.append("")
        if not block["pairs"]:
            lines.append("No misclassifications in this task.")
            lines.append("")
            continue
        for pair in block["pairs"][:5]:
            noun = "row" if pair["count"] == 1 else "rows"
            lines.append(
                f"- True `{pair['true']}` predicted `{pair['predicted']}`: {pair['count']} {noun}."
            )
            for example in pair["examples"]:
                lines.append(f"  - `{example['id']}`: {example['query']}")
            advice = ADVICE.get((task, pair["true"], pair["predicted"]))
            if advice:
                lines.append(f"  - Prompt boundary: {advice}")
        lines.append("")

    lines.extend(
        [
            "## Recommendations",
            "",
            report["recommendation_summary"],
            "",
            "## Limitations",
            "",
            f"- The test split has {report['dataset']['splits'].get('test', 0)} rows and {report['count']} of them produced a valid classification. One mistake moves accuracy by about two points.",
            "- Labels are one reviewer's reading of the written criteria. Borderline medium/complex rows can reasonably be argued the other way.",
            "- The decision prompt sees the question and not the conversation, so high-context questions are judged from wording alone.",
            "- Isotonic calibration is fit per class on the calibration split. It adjusts confidence. It is not a new classifier.",
            "- Routing accuracy depends on the threshold and on complexity and reasoning together. A better Brier score can coexist with the same selected tier.",
            "",
        ]
    )
    return "\n".join(lines)


def _table(counts: dict, columns: tuple[str, ...]) -> str:
    header = "| Complexity | " + " | ".join(columns) + " |"
    separator = "|---|" + "|".join("---:" for _ in columns) + "|"
    body = []
    for complexity in TASKS["complexity"]:
        row = counts[complexity]
        cells = " | ".join(str(row.get(column, 0)) for column in columns)
        body.append(f"| {complexity} | {cells} |")
    return "\n".join([header, separator, *body])


def _blank(value) -> str:
    if value is None:
        return ""
    return str(value)
