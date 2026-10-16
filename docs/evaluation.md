# Evaluation workflow

The Evaluation page is wired to the existing decision-model evaluation
implementation in `backend/app/decision/evaluation/runner.py`.

The evaluator scores saved raw predictions against the fixed calibration
dataset's **test** split. Its persisted report compares raw and calibrated
classification metrics and reports routing metrics. It does not generate new
model predictions, call a model provider, or change the deployed routing
threshold. The report also identifies the model, split size, invalid outputs,
calibration state, and test scores.

Start the backend and open `/evaluation/results` to retrieve the last saved
report. If no report is available yet, `/evaluation/run` can generate one from
`backend/app/decision/calibration/artifacts/raw_predictions.json`. That file is
created by the separate calibration trainer. If it is missing, run the trainer
as documented in [the decision-layer guide](../backend/app/decision/README.md)
before starting an evaluation. A run rewrites the JSON, Markdown, and
reliability SVG report artifacts under the configured artifact directory.

This decision-model evaluation is separate from the request-level quality
checks stored with gateway request records, and also separate from the
`evaluation/dataset.json` gateway workload validator. The Evaluation page does
not claim request-level quality observations or workload-template rows as
decision test scores.