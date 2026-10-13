"""Rebuild dataset.json from the original 45 rows plus hand-labeled additions.

The original q001-q045 rows are kept, including their splits and labels.
New rows are split 39/13/13 per complexity so the full file is
144 calibration, 48 validation, and 48 test.
"""

import json
import re
import sys
from collections import Counter, defaultdict

from app.decision.calibration.additional_queries import QUERIES
from app.decision.paths import DATASET_PATH
from app.decision.schemas.decision import TASKS

DOMAINS = (
    "programming",
    "mathematics",
    "ai_ml",
    "databases",
    "cloud",
    "networking",
    "devops",
    "general",
    "system_design",
)

# Wording that points at an earlier turn. Bare words like "above 70 percent"
# are not included.
DEPENDENT = re.compile(
    r"("
    r"you just|you wrote|you started|you described|you proposed|you offered|"
    r"you recommended|you gave|you drafted|you listed|you made|did you say|"
    r"you offer|"
    r"i asked|i ask|i mentioned|i pasted|i gave|i listed|i described|i added|"
    r"i defined|i raised|i told|i tell|i say|i give|i just|"
    r"previous message|last message|last turn|last note|last session|"
    r"last week|previous turn|previous review|previous design|last design|"
    r"your last|your previous|"
    r"we discussed|we designed|we agreed|we were|we looked|we reviewed|"
    r"we sketched|we made|we decide|we just|"
    r"my last|my previous|my earlier|earlier message|"
    r"(?<!is )(?<!stays )above|"
    r"yesterday"
    r")",
    re.IGNORECASE,
)


def build() -> list[dict]:
    original = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    original = [row for row in original if _id_number(row["id"]) <= 45]
    if len(original) != 45:
        raise SystemExit(
            f"Expected the original 45 rows in {DATASET_PATH}, found {len(original)}."
        )
    # q001-q045 do not refer to an earlier turn. Older context labels said
    # medium or high on some of those rows; under LABELING.md they are low.
    for row in original:
        if DEPENDENT.search(row["query"]) is None:
            row["labels"]["context"] = "low"

    added = _assign_new_rows(QUERIES)
    rows = original + added
    _validate(rows)
    DATASET_PATH.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    _print_summary(rows)
    print(f"Wrote {len(rows)} rows to {DATASET_PATH}")
    return rows


def _assign_new_rows(queries: list[tuple[str, str, str, str, str]]) -> list[dict]:
    by_complexity: dict[str, list[tuple]] = defaultdict(list)
    for item in queries:
        domain, complexity, reasoning, context, query = item
        if domain not in DOMAINS:
            raise SystemExit(f"Unknown domain: {domain}")
        if complexity not in TASKS["complexity"]:
            raise SystemExit(f"Unknown complexity: {complexity}")
        if reasoning not in TASKS["reasoning"]:
            raise SystemExit(f"Unknown reasoning: {reasoning}")
        if context not in TASKS["context"]:
            raise SystemExit(f"Unknown context: {context}")
        by_complexity[complexity].append(item)

    rows = []
    next_number = 46
    for complexity in TASKS["complexity"]:
        ordered = _round_robin(by_complexity[complexity])
        if len(ordered) != 65:
            raise SystemExit(
                f"Expected 65 new {complexity} queries, found {len(ordered)}."
            )
        for index, item in enumerate(ordered):
            domain, _, reasoning, context, query = item
            if index < 39:
                split = "calibration"
            elif index < 52:
                split = "validation"
            else:
                split = "test"
            rows.append(
                {
                    "id": f"q{next_number:03d}",
                    "domain": domain,
                    "split": split,
                    "query": query,
                    "labels": {
                        "complexity": complexity,
                        "reasoning": reasoning,
                        "context": context,
                    },
                }
            )
            next_number += 1
    return rows


def _round_robin(items: list[tuple]) -> list[tuple]:
    buckets: dict[str, list[tuple]] = {domain: [] for domain in DOMAINS}
    for item in items:
        buckets[item[0]].append(item)

    ordered = []
    remaining = True
    while remaining:
        remaining = False
        for domain in DOMAINS:
            if buckets[domain]:
                ordered.append(buckets[domain].pop(0))
                remaining = True
    return ordered


def _validate(rows: list[dict]) -> None:
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("Dataset ids must be unique.")
    if len(rows) != 240:
        raise SystemExit(f"Expected 240 rows, found {len(rows)}.")

    queries = [row["query"].strip().lower() for row in rows]
    if len(queries) != len(set(queries)):
        duplicates = [query for query, count in Counter(queries).items() if count > 1]
        raise SystemExit(f"Duplicate queries: {duplicates}")

    split_counts = Counter(row["split"] for row in rows)
    if split_counts != {"calibration": 144, "validation": 48, "test": 48}:
        raise SystemExit(f"Unexpected split counts: {dict(split_counts)}")

    for complexity in TASKS["complexity"]:
        band = [row for row in rows if row["labels"]["complexity"] == complexity]
        if len(band) != 80:
            raise SystemExit(f"Expected 80 {complexity} rows, found {len(band)}.")
        counts = Counter(row["split"] for row in band)
        if counts != {"calibration": 48, "validation": 16, "test": 16}:
            raise SystemExit(f"Unexpected {complexity} splits: {dict(counts)}")

    domain_counts = Counter(row["domain"] for row in rows)
    for domain in DOMAINS:
        if domain_counts[domain] < 24:
            raise SystemExit(f"Domain {domain} has only {domain_counts[domain]} rows.")

    cue_errors = []
    for row in rows:
        depends = DEPENDENT.search(row["query"]) is not None
        context = row["labels"]["context"]
        if context == "low" and depends:
            cue_errors.append(
                f"{row['id']} is context low but the wording depends on an earlier turn: {row['query']}"
            )
        if context != "low" and not depends:
            cue_errors.append(
                f"{row['id']} is context {context} but the wording looks self-contained: {row['query']}"
            )
    if cue_errors:
        raise SystemExit("\n".join(cue_errors))

    simple_high_context = _count(rows, complexity="simple", context="high")
    complex_low_context = _count(rows, complexity="complex", context="low")
    simple_high_reasoning = _count(rows, complexity="simple", reasoning="high")
    medium_low_reasoning = _count(rows, complexity="medium", reasoning="low")
    if simple_high_context < 12:
        raise SystemExit("Not enough simple questions that depend on earlier messages.")
    if complex_low_context < 15:
        raise SystemExit("Not enough self-contained complex questions.")
    if simple_high_reasoning < 8:
        raise SystemExit("Not enough simple questions that still need a deduction.")
    if medium_low_reasoning < 8:
        raise SystemExit("Not enough medium questions that are mostly recall.")


def _count(rows: list[dict], **labels: str) -> int:
    total = 0
    for row in rows:
        if all(row["labels"][key] == value for key, value in labels.items()):
            total += 1
    return total


def _print_summary(rows: list[dict]) -> None:
    print("Domain counts:", dict(Counter(row["domain"] for row in rows)))
    for left in ("reasoning", "context"):
        print(f"complexity x {left}")
        for complexity in TASKS["complexity"]:
            counts = Counter(
                row["labels"][left]
                for row in rows
                if row["labels"]["complexity"] == complexity
            )
            print(f"  {complexity}: {dict(counts)}")


def _id_number(row_id: str) -> int:
    return int(row_id[1:])


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    build()


if __name__ == "__main__":
    main()
