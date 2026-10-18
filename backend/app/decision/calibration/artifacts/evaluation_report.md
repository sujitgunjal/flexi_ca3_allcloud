# Decision evaluation

Decision model: `ollama/llama3:8b`.
The paid Jev API was not called.

Classification and routing scores use only the final test split. The isotonic calibrator was fit on the calibration split. The confidence threshold was selected on the validation split. Neither step looked at the test labels.

Calibration fits a post-hoc isotonic map from raw probabilities to observed frequencies.
It does not train the Ollama model, and it does not change a predicted class when the class ranking stays the same.
A higher calibrated accuracy is possible only when renormalization changes an argmax.
Better class accuracy needs a prompt change or a different decision model.

## Dataset

Rows: 240.
Splits: calibration 144, validation 48, test 48.
Complexity: {'simple': 80, 'medium': 80, 'complex': 80}.
Invalid model outputs excluded from scores: 0 (none).
Those rows made the model return all-zero probabilities for reasoning and context.
The validator rejected them after one correction retry.

Label criteria are in `calibration/LABELING.md`.
Labels were assigned from those criteria and checked against the wording.
They were not copied from this model's predictions.

### Complexity by reasoning

| Complexity | low | medium | high |
|---|---:|---:|---:|
| simple | 52 | 17 | 11 |
| medium | 18 | 43 | 19 |
| complex | 0 | 24 | 56 |

### Complexity by context

| Complexity | low | medium | high |
|---|---:|---:|---:|
| simple | 54 | 8 | 18 |
| medium | 53 | 8 | 19 |
| complex | 53 | 9 | 18 |

## Test classification

Scored test rows: 9. These scores use only the test split.
The calibrator was fit on 27 calibration rows.

| Task | Raw accuracy | Calibrated accuracy | Raw macro-F1 | Calibrated macro-F1 | Raw Brier | Calibrated Brier |
|---|---:|---:|---:|---:|---:|---:|
| complexity | 0.6667 | 0.6667 | 0.5556 | 0.5556 | 0.5178 | 0.4147 |
| reasoning | 0.5556 | 0.8889 | 0.4667 | 0.8857 | 0.4872 | 0.4955 |
| context | 0.5556 | 0.5556 | 0.5222 | 0.4667 | 0.6933 | 0.6953 |

Confusion matrices are rows = true label, columns = prediction, in class order.

### complexity

Class order: simple, medium, complex.

Raw: `[[3, 0, 0], [3, 0, 0], [0, 0, 3]]`

Calibrated: `[[0, 3, 0], [0, 3, 0], [0, 0, 3]]`

Reliability bins (calibrated confidence vs accuracy):

| Bin | Count | Mean confidence | Accuracy |
|---|---:|---:|---:|
| 0.0-0.2 | 0 |  |  |
| 0.2-0.4 | 0 |  |  |
| 0.4-0.6 | 8 | 0.5799 | 0.625 |
| 0.6-0.8 | 0 |  |  |
| 0.8-1 | 1 | 0.9375 | 1.0 |

### reasoning

Class order: low, medium, high.

Raw: `[[2, 0, 1], [0, 0, 3], [0, 0, 3]]`

Calibrated: `[[2, 0, 1], [0, 3, 0], [0, 0, 3]]`

Reliability bins (calibrated confidence vs accuracy):

| Bin | Count | Mean confidence | Accuracy |
|---|---:|---:|---:|
| 0.0-0.2 | 0 |  |  |
| 0.2-0.4 | 0 |  |  |
| 0.4-0.6 | 5 | 0.518 | 1.0 |
| 0.6-0.8 | 2 | 0.6255 | 1.0 |
| 0.8-1 | 2 | 0.8191 | 0.5 |

### context

Class order: low, medium, high.

Raw: `[[1, 1, 1], [0, 3, 0], [0, 2, 1]]`

Calibrated: `[[2, 0, 1], [0, 0, 3], [0, 0, 3]]`

Reliability bins (calibrated confidence vs accuracy):

| Bin | Count | Mean confidence | Accuracy |
|---|---:|---:|---:|
| 0.0-0.2 | 0 |  |  |
| 0.2-0.4 | 0 |  |  |
| 0.4-0.6 | 6 | 0.483 | 0.5 |
| 0.6-0.8 | 2 | 0.6466 | 0.5 |
| 0.8-1 | 1 | 0.8534 | 1.0 |

## Routing

The reference tier applies `routing/policy.py` to the true labels at full confidence:
complex or high reasoning selects `strong`, simple with low reasoning selects `local`, otherwise `cheap`.
Context does not change the tier.
A low calibrated confidence uses the uncertain fallback (`cheap`).

The lowest validation threshold with complexity accuracy at least 0.75 is `0.55`.
Validation routing sweep (calibrated probabilities, validation split only):

| Threshold | Routing accuracy | Uncertain rate |
|---:|---:|---:|
| 0.4 | 0.5556 | 0.0 |
| 0.45 | 0.5556 | 0.0 |
| 0.5 | 0.5556 | 0.0 |
| 0.55 | 0.4444 | 0.1111 |
| 0.6 | 0.4444 | 0.8889 |
| 0.65 | 0.3333 | 1.0 |
| 0.7 | 0.3333 | 1.0 |
| 0.75 | 0.3333 | 1.0 |
| 0.8 | 0.3333 | 1.0 |

Validation selected threshold `0.5` by routing accuracy on the validation split only. Ties prefer fewer fallbacks, then the candidate closest to 0.55.
`routing/rules.json` was left at `0.45` so this run does not change live traffic.
The test numbers below use the validation-selected threshold.
The deployed threshold is shown only as a comparison. The test split was not used to choose either value.

| Probabilities | Threshold | Routing accuracy | Uncertain rate | Selected tiers |
|---|---:|---:|---:|---|
| raw_at_selected_threshold | 0.5 | 0.5556 | 0.0 | {'local': 2, 'cheap': 0, 'strong': 7} |
| calibrated_at_selected_threshold | 0.5 | 0.6667 | 0.0 | {'local': 0, 'cheap': 5, 'strong': 4} |
| raw_at_deployed_threshold | 0.45 | 0.5556 | 0.0 | {'local': 2, 'cheap': 0, 'strong': 7} |
| calibrated_at_deployed_threshold | 0.45 | 0.6667 | 0.0 | {'local': 0, 'cheap': 5, 'strong': 4} |

Gold tier counts on the test split: {'local': 3, 'cheap': 3, 'strong': 3}.

Calibrated routing confusion at the validation-selected threshold (rows = gold tier, columns = local, cheap, strong):

`[[0, 2, 1], [0, 3, 0], [0, 0, 3]]`

## Common mistakes on the test split

### complexity

- True `simple` predicted `medium`: 3 rows.
  - `q013`: What port does HTTP use by default?
  - `q014`: What is a Git commit?
  - `q015`: How many bits are in a byte?
  - Prompt boundary: Treat one-step lookups, definitions, and yes-or-no checks as simple even when the topic is technical.

### reasoning

- True `low` predicted `high`: 1 row.
  - `q014`: What is a Git commit?
  - Prompt boundary: Naming a fact is low reasoning. Deriving or diagnosing is high.

### context

- True `medium` predicted `high`: 3 rows.
  - `q028`: Explain the difference between an inner join and a left join.
  - `q029`: How does a TCP three-way handshake work?
  - `q030`: What is the difference between CI and CD?
  - Prompt boundary: Medium context means the main task is in the question and only one piece is missing.
- True `low` predicted `high`: 1 row.
  - `q014`: What is a Git commit?
  - Prompt boundary: Self-contained designs are low context. High context requires an earlier turn.

## Recommendations

Keep llama3.2:3b as the decision model. Do not treat the calibrator as training. On complexity, calibration lowered the Brier score from 0.5178 to 0.4147, so the probabilities are closer to the observed frequencies. On complexity, calibrated accuracy (0.6667) is not higher than raw accuracy (0.6667). On reasoning, calibration raised the Brier score from 0.4872 to 0.4955. The class ranking should be fixed in the prompt or the model before trusting the map. On context, calibration raised the Brier score from 0.6933 to 0.6953. The class ranking should be fixed in the prompt or the model before trusting the map. On context, calibrated accuracy (0.5556) is not higher than raw accuracy (0.5556). The most common complexity mistake is true simple predicted as medium (3 test rows). Add two or three of those boundary cases to the decision prompt as labeled examples. The most common reasoning mistake is true low predicted as high (1 test rows). On the validation sweep, threshold(s) 0.4, 0.45, 0.5 lead with routing accuracy 0.5556 and fallback rate 0.0. At the deployed 0.45 threshold, validation fallback is 0.0, and the test fallback rate is 0.0. That drop is a confidence cutoff, not a change in the Ollama class. Copy the validation-selected threshold into routing/rules.json only after reading the validation sweep. Do not retune it on the test split.

## Limitations

- The test split has 48 rows and 9 of them produced a valid classification. One mistake moves accuracy by about two points.
- Labels are one reviewer's reading of the written criteria. Borderline medium/complex rows can reasonably be argued the other way.
- The decision prompt sees the question and not the conversation, so high-context questions are judged from wording alone.
- Isotonic calibration is fit per class on the calibration split. It adjusts confidence. It is not a new classifier.
- Routing accuracy depends on the threshold and on complexity and reasoning together. A better Brier score can coexist with the same selected tier.
