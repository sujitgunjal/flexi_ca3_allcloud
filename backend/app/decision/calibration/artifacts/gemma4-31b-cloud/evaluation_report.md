# gemma4:31b-cloud decision evaluation

gemma4:31b-cloud was scored with the existing candidate prompt and labeled dataset. The calibrator was fit on this model's calibration rows only. The threshold was selected on this model's validation rows only. The test split was scored once. Llama predictions and calibrators were not reused.

Calibration rows used: 144.
Validation rows used for the threshold: 48.
Test rows scored: 48.
Invalid ids: none.
Validation-selected threshold: 0.5.

## Latency and tokens

Mean 3264.25 ms, median 2955.11 ms, p95 4487.97 ms.
Prompt tokens 251277, output tokens 25440.
Ollama does not return a dollar cost for gemma4:31b-cloud. Token counts are prompt_eval_count and eval_count when the provider sent them.

## Complexity on the test split

| | Accuracy | Macro precision | Macro recall | Macro-F1 | Complex recall | Brier |
|---|---:|---:|---:|---:|---:|---:|
| gemma raw | 0.6667 | 0.7 | 0.6667 | 0.6584 | 0.6875 | 0.5176 |
| gemma calibrated | 0.7292 | 0.763 | 0.7292 | 0.6846 | 1.0 | 0.3884 |

## Conclusion

On the untouched test split, calibrated gemma4:31b-cloud accuracy is 0.7292 against calibrated llama3:8b 0.7083. Macro-F1 0.7122 -> 0.6846. Complex recall 0.8125 -> 1.0.
