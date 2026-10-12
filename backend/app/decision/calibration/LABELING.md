# Labeling criteria

The queries in `dataset.json` are labeled by hand. The local Ollama model is the system under test, so its predictions are not used as labels and are not used to break ties.

Each row has three labels. They are assigned separately.

## Complexity

Complexity is the difficulty of the task itself, once the needed information is in hand.

- `simple`: one fact, a definition, a yes-or-no check, or a single arithmetic step.
- `medium`: a short explanation, a small code or SQL snippet, a comparison of two ideas, or a known procedure of a few steps.
- `complex`: a design, a proof, a diagnosis that crosses components, or a recommendation that has to weigh failure modes.

A long question can still be simple. A short question can still be complex.

## Reasoning

Reasoning is how much new inference the answer needs. It is not the same thing as complexity.

- `low`: recall or a direct lookup. No deduction.
- `medium`: apply a known procedure, or compare two options against one stated constraint.
- `high`: derive a result, diagnose a failure, design a mechanism, or justify a choice among alternatives.

## Context

Context is how much earlier conversation the question needs. The dataset stores the question alone, so this label is about the wording.

- `low`: the question can be answered from its own text.
- `medium`: the question includes the main task, but one fact or artifact is only in an earlier turn.
- `high`: the question cannot be answered from its own text. It points at earlier messages ("the function you just wrote", "the port I asked for").

## How the labels stay independent

These combinations are included on purpose:

- complex questions that contain the whole problem (`context: low`)
- simple questions that point at earlier messages (`context: high`)
- simple questions that still need a deduction (`reasoning: high`)
- medium questions that are mostly recall (`reasoning: low`)

A complex design usually needs medium or high reasoning. Rows are not forced into `complex` + `reasoning: low` when that would be a checklist rather than a hard task. Empty cells are better than misleading ones.

## Original 45 rows

`q001`–`q045` were already in the dataset. Their complexity and reasoning labels were kept after a pass against the definitions above. Those questions do not mention an earlier turn, so their context label is `low`. A previous version marked some of them `medium` or `high` context; that mixed "needs a long answer" into the context decision.

## Review

Labels were checked against the definitions above, not against a model score. A build step rejects a row when the context label disagrees with the wording: a low-context question must not depend on an earlier turn, and a medium or high context question must. Counts, split sizes, and duplicate text are checked in `build_dataset.py`.

## Splits

The split is stored on the row.

- `calibration`: fit the isotonic calibrator only
- `validation`: choose a confidence threshold only
- `test`: final scores only

The test rows are not used to fit probabilities or to pick the threshold.
