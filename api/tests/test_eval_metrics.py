from __future__ import annotations

import pytest
from eval.metrics import (
    needs_review_stats,
    overall_mae,
    pearson,
    per_criterion_metrics,
    rankdata,
    rubric_adherence,
    score_metrics,
    spearman,
    total_score_mae,
)


def test_score_metrics_hand_computed() -> None:
    metrics = score_metrics([(5.0, 5.0), (3.0, 4.0)])
    assert metrics["n"] == 2
    assert metrics["exact_match_rate"] == 0.5
    assert metrics["within_1_rate"] == 1.0
    assert metrics["mae"] == 0.5


def test_score_metrics_empty() -> None:
    metrics = score_metrics([])
    assert metrics["exact_match_rate"] == 0.0
    assert metrics["mae"] == 0.0


def test_per_criterion_and_overall_mae() -> None:
    predictions = [
        {"Thesis": 5, "Evidence": 8},
        {"Thesis": 3, "Evidence": 4},
    ]
    golds = [
        {"Thesis": 4, "Evidence": 8},
        {"Thesis": 3, "Evidence": 6},
    ]
    metrics = per_criterion_metrics(predictions, golds, ["Thesis", "Evidence"])
    assert metrics["Thesis"]["exact_match_rate"] == 0.5
    assert metrics["Thesis"]["within_1_rate"] == 1.0
    assert metrics["Thesis"]["mae"] == 0.5
    assert metrics["Evidence"]["exact_match_rate"] == 0.5
    assert metrics["Evidence"]["within_1_rate"] == 0.5
    assert metrics["Evidence"]["mae"] == 1.0
    assert overall_mae(predictions, golds, ["Thesis", "Evidence"]) == 0.75


def test_pearson_perfect_and_inverse() -> None:
    assert pearson([1, 2, 3], [2, 4, 6]) == 1.0
    assert pearson([1, 2, 3], [6, 4, 2]) == -1.0
    assert pearson([1, 1, 1], [1, 2, 3]) == 0.0


def test_spearman_handles_ties() -> None:
    assert rankdata([1, 2, 2, 3]) == [1.0, 2.5, 2.5, 4.0]
    value = spearman([1, 2, 2, 3], [1, 3, 2, 4])
    assert value == pytest.approx(0.9487, abs=0.0001)
    assert spearman([1, 1, 2, 2], [3, 3, 5, 5]) == 1.0
    assert spearman([1, 2, 3], [3, 2, 1]) == -1.0


def test_total_score_mae() -> None:
    assert total_score_mae([21, 12, 5], [23, 10, 5]) == pytest.approx(1.3333)
    assert total_score_mae([], []) == 0.0


def test_rubric_adherence() -> None:
    assert rubric_adherence([1, 1, 2, 3]) == 0.5
    assert rubric_adherence([]) == 0.0
    assert rubric_adherence([1, 1]) == 1.0


def test_needs_review_stats_hand_computed() -> None:
    stats = needs_review_stats(
        flags=[True, True, False, True],
        total_errors=[0.5, 3.0, 9.0, 0.0],
    )
    assert stats["flagged"] == 3.0
    assert stats["flagged_rate"] == 0.75
    assert stats["flagged_off_by_more_than_1"] == 1.0
    assert stats["flagged_precision"] == pytest.approx(0.3333, abs=1e-4)

    empty = needs_review_stats([], [])
    assert empty["flagged"] == 0.0
    assert empty["flagged_precision"] == 0.0
