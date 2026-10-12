# Selected model final evaluation

The candidate prompt and llama3:8b were selected on the validation split. The calibrator was then fit on this model's calibration rows only. The threshold was selected on validation. The test split was scored once. The live llama3.2:3b prompt was not replaced, because that prompt cut simple recall on validation.

Calibration rows used: 144.
Validation rows used for the threshold: 48.
Test rows scored: 48.
Invalid ids: none.
Validation-selected threshold: 0.45.
routing/rules.json was not changed.

## Complexity on the test split

| | Accuracy | Macro precision | Macro recall | Macro-F1 | Complex recall | Brier |
|---|---:|---:|---:|---:|---:|---:|
| llama3.2:3b current, raw | 0.4255 | 0.4001 | 0.4208 | 0.3923 | 0.25 | 0.7668 |
| llama3:8b candidate, raw | 0.5625 | 0.5761 | 0.5625 | 0.5374 | 0.5625 | 0.7435 |
| llama3:8b candidate, calibrated | 0.7083 | 0.7185 | 0.7083 | 0.7122 | 0.8125 | 0.4487 |

Confusion rows are true simple, medium, complex.

Baseline raw: `[[13, 2, 1], [8, 3, 4], [3, 9, 4]]`

8b candidate raw: `[[15, 1, 0], [12, 3, 1], [0, 7, 9]]`

8b candidate calibrated: `[[11, 5, 0], [4, 10, 2], [0, 3, 13]]`

## Reasoning and context

### reasoning

| | Accuracy | Macro-F1 | Brier |
|---|---:|---:|---:|
| 3b current raw | 0.4681 | 0.4198 | 0.7793 |
| 8b candidate raw | 0.6042 | 0.5342 | 0.6337 |
| 8b candidate calibrated | 0.6042 | 0.5342 | 0.5129 |

8b candidate raw confusion: `[[18, 0, 0], [8, 2, 1], [1, 9, 9]]`

### context

| | Accuracy | Macro-F1 | Brier |
|---|---:|---:|---:|
| 3b current raw | 0.3404 | 0.3443 | 0.9587 |
| 8b candidate raw | 0.5417 | 0.3762 | 0.8264 |
| 8b candidate calibrated | 0.5417 | 0.3647 | 0.6456 |

8b candidate raw confusion: `[[21, 0, 1], [8, 0, 2], [8, 3, 5]]`

## Routing

At the validation-selected threshold 0.45, routing accuracy is 0.75 and the uncertain rate is 0.0.
Selected tiers: {'local': 15, 'cheap': 18, 'strong': 15}.

## Conclusion

On the untouched test split, llama3:8b with the candidate prompt improves complexity accuracy, macro-F1, and complex recall over the llama3.2:3b baseline. Accuracy 0.4255 -> 0.5625. Macro-F1 0.3923 -> 0.5374. Complex recall 0.25 -> 0.5625.
