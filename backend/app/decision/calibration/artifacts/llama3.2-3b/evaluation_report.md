# Decision evaluation

Decision model: `ollama/llama3.2:3b`.
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
Invalid model outputs excluded from scores: 2 (q129, q174).
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

Scored test rows: 47. These scores use only the test split.
The calibrator was fit on 143 calibration rows.

| Task | Raw accuracy | Calibrated accuracy | Raw macro-F1 | Calibrated macro-F1 | Raw Brier | Calibrated Brier |
|---|---:|---:|---:|---:|---:|---:|
| complexity | 0.4255 | 0.5957 | 0.3923 | 0.5926 | 0.7668 | 0.5592 |
| reasoning | 0.4681 | 0.4043 | 0.4198 | 0.4111 | 0.7793 | 0.6635 |
| context | 0.3404 | 0.4681 | 0.3443 | 0.2126 | 0.9587 | 0.765 |

Confusion matrices are rows = true label, columns = prediction, in class order.

### complexity

Class order: simple, medium, complex.

Raw: `[[13, 2, 1], [8, 3, 4], [3, 9, 4]]`

Calibrated: `[[7, 7, 2], [0, 8, 7], [0, 3, 13]]`

Reliability bins (calibrated confidence vs accuracy):

| Bin | Count | Mean confidence | Accuracy |
|---|---:|---:|---:|
| 0.0-0.2 | 0 |  |  |
| 0.2-0.4 | 0 |  |  |
| 0.4-0.6 | 33 | 0.5299 | 0.5758 |
| 0.6-0.8 | 9 | 0.7772 | 0.7778 |
| 0.8-1 | 5 | 0.8599 | 0.4 |

### reasoning

Class order: low, medium, high.

Raw: `[[6, 1, 10], [1, 2, 8], [0, 5, 14]]`

Calibrated: `[[6, 7, 4], [1, 8, 2], [0, 14, 5]]`

Reliability bins (calibrated confidence vs accuracy):

| Bin | Count | Mean confidence | Accuracy |
|---|---:|---:|---:|
| 0.0-0.2 | 0 |  |  |
| 0.2-0.4 | 0 |  |  |
| 0.4-0.6 | 32 | 0.4789 | 0.3438 |
| 0.6-0.8 | 15 | 0.6701 | 0.5333 |
| 0.8-1 | 0 |  |  |

### context

Class order: low, medium, high.

Raw: `[[5, 12, 5], [2, 5, 3], [1, 8, 6]]`

Calibrated: `[[22, 0, 0], [10, 0, 0], [15, 0, 0]]`

Reliability bins (calibrated confidence vs accuracy):

| Bin | Count | Mean confidence | Accuracy |
|---|---:|---:|---:|
| 0.0-0.2 | 0 |  |  |
| 0.2-0.4 | 0 |  |  |
| 0.4-0.6 | 0 |  |  |
| 0.6-0.8 | 47 | 0.7626 | 0.4681 |
| 0.8-1 | 0 |  |  |

## Routing

The reference tier applies `routing/policy.py` to the true labels at full confidence:
complex or high reasoning selects `strong`, simple with low reasoning selects `local`, otherwise `cheap`.
Context does not change the tier.
A low calibrated confidence uses the uncertain fallback (`cheap`).

The lowest validation threshold with complexity accuracy at least 0.75 is `0.75`.
Validation routing sweep (calibrated probabilities, validation split only):

| Threshold | Routing accuracy | Uncertain rate |
|---:|---:|---:|
| 0.4 | 0.5208 | 0.0 |
| 0.45 | 0.5208 | 0.0 |
| 0.5 | 0.5208 | 0.0 |
| 0.55 | 0.3542 | 0.6042 |
| 0.6 | 0.2708 | 0.7708 |
| 0.65 | 0.2708 | 0.7708 |
| 0.7 | 0.2708 | 0.7708 |
| 0.75 | 0.2708 | 0.8542 |
| 0.8 | 0.2917 | 0.9583 |

Validation selected threshold `0.5` by routing accuracy on the validation split only. Ties prefer fewer fallbacks, then the candidate closest to 0.55.
`routing/rules.json` was left at `0.55` so this run does not change live traffic.
The test numbers below use the validation-selected threshold.
The deployed threshold is shown only as a comparison. The test split was not used to choose either value.

| Probabilities | Threshold | Routing accuracy | Uncertain rate | Selected tiers |
|---|---:|---:|---:|---|
| raw_at_selected_threshold | 0.5 | 0.5319 | 0.0213 | {'local': 7, 'cheap': 6, 'strong': 34} |
| calibrated_at_selected_threshold | 0.5 | 0.5957 | 0.0 | {'local': 5, 'cheap': 16, 'strong': 26} |
| raw_at_deployed_threshold | 0.55 | 0.5319 | 0.0213 | {'local': 7, 'cheap': 6, 'strong': 34} |
| calibrated_at_deployed_threshold | 0.55 | 0.4468 | 0.5745 | {'local': 5, 'cheap': 29, 'strong': 13} |

Gold tier counts on the test split: {'local': 10, 'cheap': 16, 'strong': 21}.

Calibrated routing confusion at the validation-selected threshold (rows = gold tier, columns = local, cheap, strong):

`[[4, 3, 3], [1, 8, 7], [0, 5, 16]]`

## Common mistakes on the test split

### complexity

- True `simple` predicted `medium`: 7 rows.
  - `q013`: What port does HTTP use by default?
  - `q014`: What is a Git commit?
  - `q098`: What was the second item on the list you gave me?
  - Prompt boundary: Treat one-step lookups, definitions, and yes-or-no checks as simple even when the topic is technical.
- True `medium` predicted `complex`: 7 rows.
  - `q163`: What causes ocean tides?
  - `q164`: Your previous design uses one database. What fails first if write traffic doubles?
  - `q166`: Using the system of equations from my last message, solve for y and show the substitution.
  - Prompt boundary: A comparison or a small fix is medium. Reserve complex for a design, a proof, or a cross-component diagnosis.
- True `complex` predicted `medium`: 3 rows.
  - `q229`: Notifications can be sent by email, push, or SMS, and a worker may retry. Design deduplication so the user gets one alert. Include the key and how long you k...
  - `q231`: A fair coin is flipped until the first heads. Derive the expected number of flips and show each step.
  - `q232`: The ablation table above removes one component at a time. Which component would you drop, and what new result would change that choice?
  - Prompt boundary: Designs, proofs, and failure-mode recommendations are complex even when the question is self-contained.
- True `simple` predicted `complex`: 2 rows.
  - `q101`: Did the model you just described use a transformer or a decision tree?
  - `q102`: Add the status filter I mentioned to the query you just wrote, and do not change the selected columns.
  - Prompt boundary: A question that points at an earlier message can still be simple. Context is a separate decision.

### reasoning

- True `high` predicted `medium`: 14 rows.
  - `q100`: From the proof you started, is the next step to add 2 to both sides or to factor?
  - `q108`: Precision is true positives divided by predicted positives. We predicted 10 positives and 8 were correct. What is the precision?
  - `q164`: Your previous design uses one database. What fails first if write traffic doubles?
  - Prompt boundary: Proofs, diagnoses, and designs are high reasoning even when they use a familiar method.
- True `low` predicted `medium`: 7 rows.
  - `q099`: In the sketch we made, where are the images stored?
  - `q163`: What causes ocean tides?
  - `q165`: Add a one-line docstring to the function in the previous message. Do not change the code.
  - Prompt boundary: Recall and direct lookup are low reasoning. Applying a procedure is medium.
- True `low` predicted `high`: 4 rows.
  - `q014`: What is a Git commit?
  - `q104`: Repeat only the DNS record type you recommended.
  - `q110`: State the quadratic formula. Do not solve an equation.
  - Prompt boundary: Naming a fact is low reasoning. Deriving or diagnosing is high.
- True `medium` predicted `high`: 2 rows.
  - `q101`: Did the model you just described use a transformer or a decision tree?
  - `q109`: Name one difference between a region and an availability zone.
  - Prompt boundary: A constrained comparison can be medium. High reasoning needs a derivation, a diagnosis, or a design.
- True `medium` predicted `low`: 1 row.
  - `q106`: What does stateless mean for an API server, in one sentence?
  - Prompt boundary: A comparison or a known procedure is medium reasoning, not pure recall.

### context

- True `high` predicted `low`: 15 rows.
  - `q098`: What was the second item on the list you gave me?
  - `q100`: From the proof you started, is the next step to add 2 to both sides or to factor?
  - `q101`: Did the model you just described use a transformer or a decision tree?
  - Prompt boundary: Phrases such as 'you just wrote' or 'the port I asked for' are high context.
- True `medium` predicted `low`: 10 rows.
  - `q099`: In the sketch we made, where are the images stored?
  - `q165`: Add a one-line docstring to the function in the previous message. Do not change the code.
  - `q171`: The itinerary above has flights listed by day. Is there a day with two flights, and which day is it?
  - Prompt boundary: A question that still needs one fact from an earlier turn is not low context.

## Recommendations

Keep llama3.2:3b as the decision model. Do not treat the calibrator as training. On complexity, calibration lowered the Brier score from 0.7668 to 0.5592, so the probabilities are closer to the observed frequencies. On reasoning, calibration lowered the Brier score from 0.7793 to 0.6635, so the probabilities are closer to the observed frequencies. On reasoning, calibrated accuracy (0.4043) is not higher than raw accuracy (0.4681). On context, calibration lowered the Brier score from 0.9587 to 0.765, so the probabilities are closer to the observed frequencies. Every calibrated context prediction on the test split is low. Accuracy can rise because that class is common, while macro-F1 falls because the other classes are never selected. The map adjusted probabilities toward the majority class. It did not learn to read phrases such as 'you just wrote'. The most common complexity mistake is true simple predicted as medium (7 test rows). Add two or three of those boundary cases to the decision prompt as labeled examples. The most common reasoning mistake is true high predicted as medium (14 test rows). On the validation sweep, threshold(s) 0.4, 0.45, 0.5 lead with routing accuracy 0.5208 and fallback rate 0.0. At the deployed 0.55 threshold, validation fallback is 0.6042, and the test fallback rate is 0.5745. That drop is a confidence cutoff, not a change in the Ollama class. Copy the validation-selected threshold into routing/rules.json only after reading the validation sweep. Do not retune it on the test split.

## Limitations

- The test split has 48 rows and 47 of them produced a valid classification. One mistake moves accuracy by about two points.
- Labels are one reviewer's reading of the written criteria. Borderline medium/complex rows can reasonably be argued the other way.
- The decision prompt sees the question and not the conversation, so high-context questions are judged from wording alone.
- Isotonic calibration is fit per class on the calibration split. It adjusts confidence. It is not a new classifier.
- Routing accuracy depends on the threshold and on complexity and reasoning together. A better Brier score can coexist with the same selected tier.
