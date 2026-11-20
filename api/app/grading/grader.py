"""Grading orchestration: render prompt, call provider, validate, persist a version."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.grading.prompts import CriterionLike, get_prompt
from app.grading.providers import LLMProvider
from app.grading.schema import GradeResult
from app.models import Assignment, CriterionScore, FeedbackVersion, Submission

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
CONFIDENCE_THRESHOLD = 0.65
PASS_THRESHOLD_RATIO = 0.6
BOUNDARY_MARGIN = 1.0

REPAIR_INSTRUCTION = (
    "\n\nREPAIR REQUIRED: your previous response was rejected by the schema validator.\n"
    "Error: {error}\n"
    "Return ONLY the JSON object described above. Include every rubric criterion exactly "
    "once, using the exact criterion names, integer or half-point scores within range, "
    "a confidence between 0 and 1, and a non-empty summary_comment. No markdown fences."
)


class GradingError(RuntimeError):
    """Raised when a submission cannot be graded after all retries."""


@dataclass
class GradeOutcome:
    result: GradeResult
    attempts: int
    needed_retry: bool
    raw_text: str


def extract_json(text: str) -> dict[str, Any]:
    """Strip optional code fences and decode the first JSON object."""
    candidate = text.strip()
    if candidate.startswith("```"):
        first_newline = candidate.find("\n")
        candidate = candidate[first_newline + 1 :] if first_newline != -1 else candidate[3:]
        if candidate.rstrip().endswith("```"):
            candidate = candidate.rstrip()[:-3]
    start = candidate.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model output")
    try:
        decoded, _ = json.JSONDecoder().raw_decode(candidate[start:])
    except JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON: {exc.msg}") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Model output JSON is not an object")
    return decoded


def parse_grade_result(raw_text: str, rubric: Sequence[CriterionLike]) -> GradeResult:
    payload = extract_json(raw_text)
    result = GradeResult.model_validate(payload)
    result.validate_against(rubric)
    return result


def run_grading(
    provider: LLMProvider,
    assignment_title: str,
    prompt_text: str,
    submission_text: str,
    criteria: Sequence[CriterionLike],
    prompt_version: str,
) -> GradeOutcome:
    """Pure grading path (no database writes) used by production and eval."""
    template = get_prompt(prompt_version)
    anchored = prompt_version.endswith("criterion_anchored")
    base_prompt = template.render(
        assignment_title=assignment_title,
        prompt_text=prompt_text,
        submission_text=submission_text,
        criteria=criteria,
        anchored=anchored,
    )

    needed_retry = False
    last_error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        prompt = base_prompt if attempt == 1 else base_prompt + REPAIR_INSTRUCTION.format(
            error=last_error[:600]
        )
        raw_text = provider.complete(template.system, prompt)
        try:
            result = parse_grade_result(raw_text, criteria)
        except (ValidationError, ValueError) as exc:
            last_error = str(exc)
            needed_retry = True
            logger.warning(
                "grading attempt %d/%d rejected for prompt %s: %s",
                attempt,
                MAX_ATTEMPTS,
                prompt_version,
                last_error[:200],
            )
            continue
        return GradeOutcome(
            result=result,
            attempts=attempt,
            needed_retry=needed_retry,
            raw_text=raw_text,
        )

    raise GradingError(
        f"Provider failed to return a valid grade after {MAX_ATTEMPTS} attempts: {last_error}"
    )


def review_reasons(
    result: GradeResult, total_points: float, max_points: float, needed_retry: bool
) -> list[str]:
    reasons: list[str] = []
    low = [
        item.criterion_name
        for item in result.criteria
        if item.confidence < CONFIDENCE_THRESHOLD
    ]
    if low:
        reasons.append(f"low confidence on {', '.join(low)}")
    boundary = max_points * PASS_THRESHOLD_RATIO
    if abs(total_points - boundary) <= BOUNDARY_MARGIN:
        reasons.append(
            f"total {total_points:g} is within {BOUNDARY_MARGIN:g} point(s) of the "
            f"{boundary:g}-point pass boundary"
        )
    if needed_retry:
        reasons.append("model output needed a schema repair retry")
    return reasons


def grade_submission(
    session: Session,
    submission: Submission,
    assignment: Assignment,
    prompt_version: str,
    provider: LLMProvider,
    grading_run_id: int | None = None,
) -> FeedbackVersion:
    criteria = assignment.criteria
    if not criteria:
        raise GradingError(f"Assignment {assignment.id} has no rubric criteria")

    outcome = run_grading(
        provider=provider,
        assignment_title=assignment.title,
        prompt_text=assignment.prompt_text,
        submission_text=submission.text,
        criteria=criteria,
        prompt_version=prompt_version,
    )
    by_name = {criterion.name: criterion for criterion in criteria}
    total_points = sum(item.points for item in outcome.result.criteria)
    reasons = review_reasons(
        outcome.result,
        total_points=total_points,
        max_points=assignment.max_points,
        needed_retry=outcome.needed_retry,
    )

    version = FeedbackVersion(
        submission_id=submission.id,
        grading_run_id=grading_run_id,
        source="ai",
        parent_version_id=None,
        summary_comment=outcome.result.summary_comment,
        total_points=total_points,
        needs_review=bool(reasons),
        raw_model_output={
            "provider": getattr(provider, "name", "unknown"),
            "model": getattr(provider, "model", "unknown"),
            "prompt_version": prompt_version,
            "attempts": outcome.attempts,
            "raw_text": outcome.raw_text,
            "parsed": outcome.result.model_dump(),
            "needs_review_reasons": reasons,
        },
        prompt_version=prompt_version,
        created_by=getattr(provider, "name", "ai"),
    )
    version.scores = [
        CriterionScore(
            criterion_id=by_name[item.criterion_name].id,
            points=item.points,
            confidence=item.confidence,
            justification=item.justification,
        )
        for item in outcome.result.criteria
    ]
    session.add(version)
    session.commit()
    session.refresh(version, attribute_names=["scores", "submission"])
    return version


def grade_result_payload(version: FeedbackVersion) -> dict[str, Any]:
    return {
        "feedback_version_id": version.id,
        "submission_id": version.submission_id,
        "prompt_version": version.prompt_version,
        "provider": (version.raw_model_output or {}).get("provider"),
        "model": (version.raw_model_output or {}).get("model"),
        "total_points": version.total_points,
        "needs_review": version.needs_review,
        "needs_review_reasons": (version.raw_model_output or {}).get("needs_review_reasons", []),
        "summary_comment": version.summary_comment,
        "criteria": [
            {
                "criterion": score.criterion.name,
                "points": score.points,
                "confidence": score.confidence,
                "justification": score.justification,
            }
            for score in version.scores
        ],
    }
