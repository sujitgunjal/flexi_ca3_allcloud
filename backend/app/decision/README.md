# Local decision layer

The permanent decision engine is the **local Ollama model** `llama3:8b`, using the candidate classification prompt. It is a Jev-inspired classifier: it returns structured decisions, not an answer to the user. It does not use or require the paid TypeSafe Jev API.

TypeSafe's Jev model, described in [Introducing System One Models & Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev), is a proprietary system that emits typed decisions with probabilities. This project copies that *role* only. `OllamaDecisionProvider` is the default. `JevDecisionProvider` is an optional adapter and stays inactive unless `DECISION_PROVIDER=jev` and both `JEV_API_KEY` and `JEV_API_BASE` are set.

## Flow

```text
query
  -> local Ollama decision model
  -> raw probabilities
  -> JSON and probability validation
  -> post-hoc isotonic calibration
  -> calibrated confidence
  -> uncertainty check
  -> routing policy
  -> downstream LLM answer (POST /chat only)
```

`POST /decisions` stops before the downstream answer. `POST /chat` continues through the selected model.

## Modules

| Piece | Where | Role |
|---|---|---|
| Decision provider | `providers/ollama_provider.py` | Default local classifier |
| Optional Jev provider | `providers/jev_provider.py` | Unused unless explicitly configured |
| Validation | `validation/probability_validator.py` | Parses JSON, checks probabilities, normalizes |
| Calibration | `calibration/calibrator.py` | One-vs-rest isotonic regression, separate from the prompt |
| Trainer | `calibration/trainer.py` | Runs Ollama on the dataset and saves the calibrator |
| Dataset | `calibration/dataset.json` | 240 hand-labeled queries |
| Fitted calibrator | `calibration/artifacts/llama3-8b-candidate/calibrator.json` | Loaded on each decision. Fitted on llama3:8b calibration rows |
| Raw predictions | `calibration/artifacts/raw_predictions.json` | Saved by the trainer |
| Routing | `routing/rules.json` and `routing/policy.py` | Thresholds and model choice |
| Evaluation | `evaluation/runner.py` | Test-split accuracy, macro-F1, confusion matrix, Brier score, reliability diagram, routing accuracy |
| API | `app/api/decisions.py` | `POST /decisions` |

## Dataset and splits

`calibration/dataset.json` holds 240 manually labeled queries from programming, mathematics, AI/ML, databases, cloud, networking, DevOps, general knowledge, and system design. Each row has ground truth for `complexity`, `reasoning`, and `context`. There are 80 simple, 80 medium, and 80 complex queries. The labeling rules are in `calibration/LABELING.md`. Labels were written to those rules and were not taken from Ollama.

`python -m app.decision.calibration.build_dataset` keeps the original `q001`–`q045` rows and writes `q046`–`q240` from `calibration/additional_queries.py`.

The three labels are not tied together. The file includes complex questions that stand alone, simple questions that refer to an earlier message, and simple questions that still need a deduction.

The split is stored on each row so it does not change between runs:

- 144 calibration rows fit the isotonic models
- 48 validation rows select the confidence threshold
- 48 test rows are never used to fit the calibrator or to pick the threshold

## How calibration is trained and loaded

From the `backend` folder:

```powershell
..\.venv\Scripts\python.exe -m app.decision.calibration.trainer
```

The trainer calls only the local Ollama model. It writes `calibration/artifacts/raw_predictions.json` after every row, so a stopped run can resume. It fits isotonic regression on the calibration split only and writes the calibrator path in `paths.py`. The live file is the llama3:8b calibrator.

Inference loads that file from disk. Until the file exists, decisions still run, raw and calibrated values match, and `calibration_applied` is `false`.

Raw confidence is the highest raw class probability. Calibrated confidence is the highest probability after isotonic regression and renormalization. Those fields stay separate in every response.

## Confidence threshold

`routing/rules.json` sets `confidence_threshold` to `0.45`, the threshold selected for llama3:8b on the validation split. If calibrated complexity confidence is below that value, the route is uncertain and uses `uncertain_fallback` (`cheap` by default).

The evaluation report prints two validation-only suggestions. `suggested_confidence_threshold` is the lowest candidate at which validation complexity accuracy is at least 0.75. The routing section also picks the threshold with the best validation routing accuracy. Copy a number into `rules.json` only after reading that sweep. The runner does not edit `rules.json`, and it does not look at the test split while choosing. `DECISION_CONFIDENCE_THRESHOLD` overrides the file.

## Routing

| Calibrated decision | Model tier |
|---|---|
| simple and low reasoning | `local` |
| medium | `cheap` |
| complex or high reasoning | `strong` |
| calibrated confidence below the threshold | `cheap` fallback |

Change tiers in `routing/rules.json`. The decision model does not contain these rules.

## Evaluation

```powershell
..\.venv\Scripts\python.exe -m app.decision.evaluation.runner
```

This scores only the test split. It reports accuracy, macro-F1, confusion matrices, multiclass Brier score, and reliability for raw and calibrated probabilities. It also reports routing accuracy, selected tiers, and the uncertain-fallback rate. Outputs are `calibration/artifacts/evaluation_report.json`, `evaluation_report.md`, and `reliability.svg`.

A lower Brier score means the probabilities are closer to the empirical outcome. Calibration does not train the Ollama model. It is not expected to change the predicted class unless renormalization changes which class is largest. Class accuracy moves when the prompt or the decision model changes.
