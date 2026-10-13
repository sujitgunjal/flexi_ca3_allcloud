# Validation prompt experiment

The live prompt defines the three class names and shows only a simple arithmetic example. On the archived llama3.2:3b validation predictions, most complex questions were labeled simple or medium. llama3:8b previously labeled every held-out complex question as medium. Those errors follow from a missing boundary, so a rubric and four class examples may correct them. The examples are new and are not validation or test rows.

Scores use raw class labels on the validation split. The test split was not read.
The calibrator was not fit. llama3.2:3b with the current prompt is the archived baseline.

Adoption rule: complex recall must rise by at least 0.12, macro-F1 may fall by at most 0.02, and simple or medium recall may fall by at most 0.15.

## Complexity

| Model | Prompt | Accuracy | Macro-F1 | Simple recall | Medium recall | Complex recall | Invalid |
|---|---|---:|---:|---:|---:|---:|---:|
| llama3.2:3b | current | 0.5 | 0.4599 | 0.9375 | 0.25 | 0.3125 | 0 |
| llama3.2:3b | candidate | 0.5745 | 0.5385 | 0.75 | 0.1875 | 0.8 | 1 |
| llama3:8b | current | 0.5417 | 0.4972 | 0.5625 | 0.9375 | 0.125 | 0 |
| llama3:8b | candidate | 0.7083 | 0.7002 | 1.0 | 0.5625 | 0.5625 | 0 |

Confusion matrices are rows = true label, columns = simple, medium, complex.

- `llama3.2:3b` / `current`: `[[15, 0, 1], [10, 4, 2], [4, 7, 5]]`
- `llama3.2:3b` / `candidate`: `[[12, 0, 4], [5, 3, 8], [0, 3, 12]]`
- `llama3:8b` / `current`: `[[9, 7, 0], [1, 15, 0], [0, 14, 2]]`
- `llama3:8b` / `candidate`: `[[16, 0, 0], [7, 9, 0], [1, 6, 9]]`

## Other decisions

### reasoning

| Model | Prompt | Accuracy | Macro-F1 | Low recall | Medium recall | High recall |
|---|---|---:|---:|---:|---:|---:|
| llama3.2:3b | current | 0.4583 | 0.4211 | 0.5 | 0.1 | 0.8333 |
| llama3.2:3b | candidate | 0.5745 | 0.5454 | 0.7 | 0.2632 | 0.8333 |
| llama3:8b | current | 0.5208 | 0.4476 | 0.5 | 0.9 | 0.1111 |
| llama3:8b | candidate | 0.5 | 0.4966 | 1.0 | 0.4 | 0.3333 |

### context

| Model | Prompt | Accuracy | Macro-F1 | Low recall | Medium recall | High recall |
|---|---|---:|---:|---:|---:|---:|
| llama3.2:3b | current | 0.25 | 0.2507 | 0.1786 | 0.4444 | 0.2727 |
| llama3.2:3b | candidate | 0.4043 | 0.3112 | 0.5 | 0.0 | 0.5 |
| llama3:8b | current | 0.2917 | 0.2653 | 0.25 | 0.6667 | 0.0909 |
| llama3:8b | candidate | 0.5625 | 0.3266 | 0.8929 | 0.2222 | 0.0 |

## Decision

Selected llama3:8b with the candidate prompt on validation. Complex recall 0.3125 -> 0.5625, macro-F1 0.4599 -> 0.7002.
