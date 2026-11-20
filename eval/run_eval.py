"""Offline eval harness.

Grades the hand-labeled gold set with the deterministic MockProvider through the
same prompt registry and validation path used in production, then writes metrics.

Usage (from the repo root, after `make seed`):
    PYTHONPATH=api python eval/run_eval.py --prompt-versions v1_basic,v2_criterion_anchored
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "api"))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.grading.grader import run_grading  # noqa: E402
from app.grading.providers import MockProvider  # noqa: E402
from app.models import Assignment, Submission  # noqa: E402
from eval.metrics import (  # noqa: E402
    needs_review_stats,
    overall_mae,
    pearson,
    per_criterion_metrics,
    rubric_adherence,
    spearman,
    total_score_mae,
)

GOLD_PATH = ROOT / "eval" / "data" / "gold_scores.json"
RESULTS_DIR = ROOT / "eval" / "results"


@dataclass
class CriterionSpec:
    name: str
    description: str
    max_points: float


@dataclass
class AssignmentSnapshot:
    title: str
    prompt_text: str
    max_points: float
    criteria: list[CriterionSpec] = field(default_factory=list)
    submissions: dict[str, str] = field(default_factory=dict)


def load_gold() -> dict[str, object]:
    return json.loads(GOLD_PATH.read_text())


def load_assignment() -> AssignmentSnapshot:
    gold = load_gold()
    title = str(gold["assignment"])
    with SessionLocal() as session:
        assignment = session.scalars(
            select(Assignment).where(Assignment.title == title).order_by(Assignment.id.desc())
        ).first()
        if assignment is None:
            raise SystemExit(
                f'Assignment "{title}" not found. Run `make seed` before the eval harness.'
            )
        submissions = session.scalars(
            select(Submission).where(Submission.assignment_id == assignment.id)
        ).all()
        snapshot = AssignmentSnapshot(
            title=assignment.title,
            prompt_text=assignment.prompt_text,
            max_points=assignment.max_points,
            criteria=[
                CriterionSpec(
                    name=criterion.name,
                    description=criterion.description,
                    max_points=criterion.max_points,
                )
                for criterion in assignment.criteria
            ],
            submissions={
                submission.student.external_id: submission.text for submission in submissions
            },
        )
    return snapshot


def evaluate_version(
    version: str, assignment: AssignmentSnapshot, gold: dict[str, object]
) -> dict[str, object]:
    criteria_names = [criterion.name for criterion in assignment.criteria]
    gold_scores = gold["scores"]
    assert isinstance(gold_scores, dict)

    provider = MockProvider()
    predictions: list[dict[str, float]] = []
    golds: list[dict[str, float]] = []
    predicted_totals: list[float] = []
    gold_totals: list[float] = []
    attempts: list[int] = []
    flags: list[bool] = []
    total_errors: list[float] = []
    rows: list[dict[str, object]] = []

    for external_id, gold_row in sorted(gold_scores.items()):
        text = assignment.submissions.get(external_id)
        if text is None:
            raise SystemExit(f"Gold submission {external_id} is missing; re-run `make seed`.")
        try:
            outcome = run_grading(
                provider=provider,
                assignment_title=assignment.title,
                prompt_text=assignment.prompt_text,
                submission_text=text,
                criteria=assignment.criteria,
                prompt_version=version,
            )
        except Exception:  # a failed output still counts against rubric adherence
            attempts.append(0)
            continue

        predicted = {item.criterion_name: float(item.points) for item in outcome.result.criteria}
        gold_row_float = {name: float(value) for name, value in gold_row.items()}
        predictions.append(predicted)
        golds.append(gold_row_float)
        predicted_total = sum(predicted.get(name, 0.0) for name in criteria_names)
        gold_total = sum(gold_row_float.values())
        predicted_totals.append(predicted_total)
        gold_totals.append(gold_total)
        attempts.append(outcome.attempts)

        low_confidence = any(item.confidence < 0.65 for item in outcome.result.criteria)
        boundary = assignment.max_points * 0.6
        flagged = low_confidence or abs(predicted_total - boundary) <= 1.0 or outcome.needed_retry
        flags.append(flagged)
        total_errors.append(abs(predicted_total - gold_total))
        rows.append(
            {
                "external_id": external_id,
                "predicted": predicted,
                "gold": gold_row_float,
                "predicted_total": predicted_total,
                "gold_total": gold_total,
                "needs_review": flagged,
                "attempts": outcome.attempts,
            }
        )

    per_criterion = per_criterion_metrics(predictions, golds, criteria_names)
    review = needs_review_stats(flags, total_errors)
    return {
        "prompt_version": version,
        "provider": provider.name,
        "model": provider.model,
        "n": len(predictions),
        "criteria": per_criterion,
        "overall_mae": overall_mae(predictions, golds, criteria_names),
        "total_score_mae": total_score_mae(predicted_totals, gold_totals),
        "pearson_total": pearson(predicted_totals, gold_totals),
        "spearman_total": spearman(predicted_totals, gold_totals),
        "rubric_adherence_rate": rubric_adherence(attempts),
        **review,
        "rows": rows,
    }


def render_summary_markdown(results: list[dict[str, object]]) -> str:
    criteria: list[str] = []
    if results:
        first = results[0]["criteria"]
        assert isinstance(first, dict)
        criteria = list(first.keys())

    def table(title: str, metric: str) -> str:
        header = "| Prompt | " + " | ".join(criteria) + " |"
        divider = "|---|" + "---|" * len(criteria)
        rows = []
        for result in results:
            metrics = result["criteria"]
            assert isinstance(metrics, dict)
            cells = []
            for criterion in criteria:
                entry = metrics[criterion]
                assert isinstance(entry, dict)
                value = float(entry[metric])
                cells.append(f"{value:.2f}" if metric == "mae" else f"{value:.0%}")
            rows.append(f"| `{result['prompt_version']}` | " + " | ".join(cells) + " |")
        return f"### {title}\n\n{header}\n{divider}\n" + "\n".join(rows) + "\n"

    aggregate_header = (
        "| Prompt | n | Overall MAE | Total-score MAE | Pearson | Spearman | "
        "Rubric adherence | Needs-review rate | Flagged & off >1 |"
    )
    aggregate_divider = "|---|---|---|---|---|---|---|---|---|"
    aggregate_rows = []
    for result in results:
        aggregate_rows.append(
            "| `{}` | {} | {:.2f} | {:.2f} | {:.3f} | {:.3f} | {:.0%} | {:.0%} | {:.0%} |".format(
                result["prompt_version"],
                result["n"],
                float(result["overall_mae"]),
                float(result["total_score_mae"]),
                float(result["pearson_total"]),
                float(result["spearman_total"]),
                float(result["rubric_adherence_rate"]),
                float(result["flagged_rate"]),
                float(result["flagged_precision"]),
            )
        )

    parts = [
        "# RubricRunner eval summary",
        "",
        "Generated by `eval/run_eval.py` with the deterministic MockProvider against the 12 "
        "hand-labeled submissions. The same prompt registry and GradeResult validator are used "
        "as in production.",
        "",
        table("Per-criterion exact-match agreement", "exact_match_rate"),
        table("Per-criterion within-1-point agreement", "within_1_rate"),
        table("Per-criterion MAE", "mae"),
        "### Aggregate metrics",
        "",
        aggregate_header,
        aggregate_divider,
        *aggregate_rows,
        "",
        "`Flagged & off >1` = among submissions the confidence gate flagged for review, the "
        "share whose predicted total was more than 1 point from the human total.",
        "",
    ]
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline RubricRunner eval")
    parser.add_argument(
        "--prompt-versions",
        default="v1_basic,v2_criterion_anchored",
        help="Comma-separated prompt versions from the production registry",
    )
    args = parser.parse_args()
    versions = [item.strip() for item in args.prompt_versions.split(",") if item.strip()]

    gold = load_gold()
    assignment = load_assignment()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, object]] = []
    for version in versions:
        result = evaluate_version(version, assignment, gold)
        results.append(result)
        (RESULTS_DIR / f"{version}.json").write_text(json.dumps(result, indent=2) + "\n")
        print(
            f"{version}: n={result['n']} overall_mae={result['overall_mae']:.2f} "
            f"total_mae={result['total_score_mae']:.2f} "
            f"spearman={result['spearman_total']:.3f} "
            f"adherence={result['rubric_adherence_rate']:.0%} "
            f"needs_review={result['flagged_rate']:.0%}"
        )

    summary = render_summary_markdown(results)
    (RESULTS_DIR / "summary.md").write_text(summary)
    print(f"Wrote {RESULTS_DIR / 'summary.md'}")
    print(summary)


if __name__ == "__main__":
    main()
