# llama3:8b held-out evaluation

Complexity Agent provider: `ollama/llama3:8b`.
Verified before scoring. The paid Jev API was not called.

This run classifies the existing 48-row test split only.
It does not refit the calibrator, change the dataset, or replace the llama3.2:3b artifact files.
The loaded calibrator is the existing artifact. It was fitted on llama3.2:3b calibration rows and was not refit on llama3:8b.

Valid test outputs: 48 of 48.
Invalid outputs: 0 (none).

## Latency

Mean 14.2201s, median 14.0593s, p95 14.9682s, total 682.5672s.
The llama3.2:3b run did not record latency, so there is no latency comparison.

## Complexity on shared valid test rows

| | Accuracy | Macro precision | Macro recall | Macro-F1 | Brier |
|---|---:|---:|---:|---:|---:|
| llama3:8b raw | 0.4468 | 0.387 | 0.4542 | 0.3822 | 0.7915 |
| llama3.2:3b raw | 0.4255 | 0.4001 | 0.4208 | 0.3923 | 0.7668 |
| 8b raw through 3b calibrator | 0.4894 | 0.6111 | 0.4847 | 0.4263 | 0.5998 |

llama3:8b is mixed against llama3.2:3b on held-out complexity: one of accuracy or macro-F1 is higher and the other is not. Shared valid test rows: 47. Accuracy 0.4255 -> 0.4468 (+0.0213). Macro-F1 0.3923 -> 0.3822 (-0.0101). This comparison uses raw class labels. The existing calibrator was fitted for llama3.2:3b and is reported separately.

## All three decisions

Raw `llama3:8b` versus raw `llama3.2:3b` on the same valid test ids.

### complexity

| | Accuracy | Macro precision | Macro recall | Macro-F1 | Brier |
|---|---:|---:|---:|---:|---:|
| llama3:8b raw | 0.4468 | 0.387 | 0.4542 | 0.3822 | 0.7915 |
| llama3.2:3b raw | 0.4255 | 0.4001 | 0.4208 | 0.3923 | 0.7668 |
| 8b raw through 3b calibrator | 0.4894 | 0.6111 | 0.4847 | 0.4263 | 0.5998 |

Class order: simple, medium, complex.

llama3:8b raw confusion: `[[9, 7, 0], [2, 12, 1], [0, 16, 0]]`

llama3.2:3b raw confusion: `[[13, 2, 1], [8, 3, 4], [3, 9, 4]]`

Existing 3b calibrator applied to 8b probabilities, confusion: `[[3, 8, 5], [0, 4, 11], [0, 0, 16]]`

### reasoning

| | Accuracy | Macro precision | Macro recall | Macro-F1 | Brier |
|---|---:|---:|---:|---:|---:|
| llama3:8b raw | 0.383 | 0.6364 | 0.4344 | 0.3686 | 0.7187 |
| llama3.2:3b raw | 0.4681 | 0.5149 | 0.4238 | 0.4198 | 0.7793 |
| 8b raw through 3b calibrator | 0.3617 | 0.634 | 0.4168 | 0.3357 | 0.7602 |

Class order: low, medium, high.

llama3:8b raw confusion: `[[8, 9, 0], [3, 8, 0], [1, 16, 2]]`

llama3.2:3b raw confusion: `[[6, 1, 10], [1, 2, 8], [0, 5, 14]]`

Existing 3b calibrator applied to 8b probabilities, confusion: `[[8, 9, 0], [3, 8, 0], [1, 17, 1]]`

### context

| | Accuracy | Macro precision | Macro recall | Macro-F1 | Brier |
|---|---:|---:|---:|---:|---:|
| llama3:8b raw | 0.3617 | 0.4697 | 0.4101 | 0.3201 | 0.9243 |
| llama3.2:3b raw | 0.3404 | 0.4179 | 0.3758 | 0.3443 | 0.9587 |
| 8b raw through 3b calibrator | 0.4681 | 0.156 | 0.3333 | 0.2126 | 0.758 |

Class order: low, medium, high.

llama3:8b raw confusion: `[[8, 14, 0], [1, 8, 1], [3, 11, 1]]`

llama3.2:3b raw confusion: `[[5, 12, 5], [2, 5, 3], [1, 8, 6]]`

Existing 3b calibrator applied to 8b probabilities, confusion: `[[22, 0, 0], [10, 0, 0], [15, 0, 0]]`

## Per-class precision and recall

These are the raw llama3:8b scores on the shared valid test rows.

### complexity

| Label | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| simple | 0.8182 | 0.5625 | 0.6667 | 16 |
| medium | 0.3429 | 0.8 | 0.48 | 15 |
| complex | 0.0 | 0.0 | 0.0 | 16 |

### reasoning

| Label | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| low | 0.6667 | 0.4706 | 0.5517 | 17 |
| medium | 0.2424 | 0.7273 | 0.3636 | 11 |
| high | 1.0 | 0.1053 | 0.1905 | 19 |

### context

| Label | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| low | 0.6667 | 0.3636 | 0.4706 | 22 |
| medium | 0.2424 | 0.8 | 0.3721 | 10 |
| high | 0.5 | 0.0667 | 0.1177 | 15 |
