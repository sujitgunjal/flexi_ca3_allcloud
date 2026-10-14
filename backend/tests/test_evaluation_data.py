import csv
import json
import sys
from pathlib import Path

import pytest

from app.evaluation.dataset import load_and_validate_dataset

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
EXPECTED_COLUMNS = [
    "request_id", "category", "query", "cache_hit", "selected_model", "final_model",
    "input_tokens", "output_tokens", "total_tokens", "latency_ms", "estimated_cost",
    "context_before_tokens", "context_after_tokens", "context_tokens_saved",
    "context_reduction_percent", "quality_score",
    "quality_status", "escalated", "fallback_used", "completed", "baseline_model", "gateway_model",
    "baseline_input_tokens", "gateway_input_tokens", "baseline_output_tokens",
    "gateway_output_tokens", "baseline_total_tokens", "gateway_total_tokens",
    "baseline_cost", "gateway_cost", "baseline_latency_ms", "gateway_latency_ms",
]


def test_dataset_schema_and_category_distribution():
    records, counts = load_and_validate_dataset(REPO_ROOT / "evaluation" / "dataset.json")

    assert len(records) == 100
    assert [record["id"] for record in records] == list(range(1, 101))
    assert all(set(("id", "category", "query")) <= record.keys() for record in records)
    assert counts == {
        "simple": 30,
        "medium": 30,
        "complex": 20,
        "coding": 10,
        "long-context": 10,
    }


def test_results_csv_has_expected_headers_only():
    with (REPO_ROOT / "evaluation" / "results.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.reader(file))

    assert rows == [EXPECTED_COLUMNS]


def test_dataset_validation_rejects_duplicate_ids():
    dataset = Path(__file__).with_name("_invalid_dataset_tmp.json")
    try:
        dataset.write_text(
            json.dumps([
                {"id": 1, "category": "simple", "query": "one"},
                {"id": 1, "category": "medium", "query": "two"},
            ]),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="unique"):
            load_and_validate_dataset(dataset)
    finally:
        dataset.unlink(missing_ok=True)


def test_dataset_validation_rejects_malformed_id_and_category_types():
    dataset = Path(__file__).with_name("_invalid_dataset_tmp.json")
    cases = [
        [{"id": [], "category": "simple", "query": "query"}],
        [{"id": 1, "category": [], "query": "query"}],
    ]
    try:
        for records in cases:
            dataset.write_text(json.dumps(records), encoding="utf-8")
            with pytest.raises(ValueError):
                load_and_validate_dataset(dataset)
    finally:
        dataset.unlink(missing_ok=True)


def test_cache_simulation_counts_repeated_queries():
    from evaluation.cache_simulation import simulate_cache_metrics

    assert simulate_cache_metrics() == {
        "total_requests": 6, "cache_hits": 3, "cache_misses": 3,
        "cache_hit_rate": 0.5, "api_calls_avoided": 3,
    }
