"""Pure metric functions for the offline eval harness.

Kept dependency-free so the numbers are easy to check by hand in tests.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def score_metrics(pairs: Sequence[tuple[float, float]]) -> dict[str, float]:
    """Exact-match rate, within-1 rate, and MAE for (prediction, gold) pairs."""
    if not pairs:
        return {"n": 0.0, "exact_match_rate": 0.0, "within_1_rate": 0.0, "mae": 0.0}
    n = len(pairs)
    exact = sum(1 for prediction, gold in pairs if abs(prediction - gold) < 1e-9)
    within = sum(1 for prediction, gold in pairs if abs(prediction - gold) <= 1 + 1e-9)
    total_error = sum(abs(prediction - gold) for prediction, gold in pairs)
    return {
        "n": float(n),
        "exact_match_rate": round(exact / n, 4),
        "within_1_rate": round(within / n, 4),
        "mae": round(total_error / n, 4),
    }


def per_criterion_metrics(
    predictions: Sequence[dict[str, float]],
    golds: Sequence[dict[str, float]],
    criteria: Sequence[str],
) -> dict[str, dict[str, float]]:
    metrics: dict[str, dict[str, float]] = {}
    for criterion in criteria:
        pairs = [
            (prediction[criterion], gold[criterion])
            for prediction, gold in zip(predictions, golds, strict=True)
            if criterion in prediction and criterion in gold
        ]
        metrics[criterion] = score_metrics(pairs)
    return metrics


def overall_mae(
    predictions: Sequence[dict[str, float]],
    golds: Sequence[dict[str, float]],
    criteria: Sequence[str],
) -> float:
    errors: list[float] = []
    for prediction, gold in zip(predictions, golds, strict=True):
        for criterion in criteria:
            if criterion in prediction and criterion in gold:
                errors.append(abs(prediction[criterion] - gold[criterion]))
    return round(sum(errors) / len(errors), 4) if errors else 0.0


def total_score_mae(predicted_totals: Sequence[float], gold_totals: Sequence[float]) -> float:
    if not predicted_totals:
        return 0.0
    return round(
        sum(abs(prediction - gold) for prediction, gold in zip(predicted_totals, gold_totals, strict=True))
        / len(predicted_totals),
        4,
    )


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    variance_x = sum((x - mean_x) ** 2 for x in xs)
    variance_y = sum((y - mean_y) ** 2 for y in ys)
    denominator = (variance_x * variance_y) ** 0.5
    if denominator == 0:
        return 0.0
    return round(covariance / denominator, 4)


def rankdata(values: Sequence[float]) -> list[float]:
    """Average ranks (1-based), with ties sharing the mean rank."""
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index
        while end + 1 < len(order) and values[order[end + 1]] == values[order[index]]:
            end += 1
        average = (index + end) / 2.0 + 1.0
        for position in range(index, end + 1):
            ranks[order[position]] = average
        index = end + 1
    return ranks


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    return pearson(rankdata(xs), rankdata(ys))


def rubric_adherence(attempts: Iterable[int]) -> float:
    """Share of outputs that validated on the first attempt."""
    values = list(attempts)
    if not values:
        return 0.0
    return round(sum(1 for value in values if value == 1) / len(values), 4)


def needs_review_stats(
    flags: Sequence[bool], total_errors: Sequence[float], threshold: float = 1.0
) -> dict[str, float]:
    """Gate rate plus how often a flagged item was genuinely off by > threshold."""
    if not flags:
        return {
            "flagged": 0.0,
            "flagged_rate": 0.0,
            "flagged_off_by_more_than_1": 0.0,
            "flagged_precision": 0.0,
        }
    flagged = sum(1 for flag in flags if flag)
    flagged_off = sum(
        1
        for flag, error in zip(flags, total_errors, strict=True)
        if flag and error > threshold
    )
    return {
        "flagged": float(flagged),
        "flagged_rate": round(flagged / len(flags), 4),
        "flagged_off_by_more_than_1": float(flagged_off),
        "flagged_precision": round(flagged_off / flagged, 4) if flagged else 0.0,
    }
