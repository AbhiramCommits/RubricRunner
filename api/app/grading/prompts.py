"""Registry of named grading prompt versions.

Prompts are pure functions of the assignment, rubric, and submission text. The
same registry is used by the production grader and the offline eval harness.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


class CriterionLike(Protocol):
    name: str
    description: str
    max_points: float


ANCHOR_LIBRARY: dict[str, list[tuple[float, str]]] = {
    "thesis": [
        (0.0, "No position, or only a topic summary"),
        (0.6, "A position is stated but vague, or no reasons are previewed"),
        (1.0, "Clear, arguable thesis that previews the reasons for the position"),
    ],
    "evidence": [
        (0.0, "Claims are asserted with no evidence"),
        (0.5, "One or two examples or statistics, lightly explained"),
        (0.8, "Several specific examples or named sources, mostly explained"),
        (1.0, "Consistent, well-explained evidence with citations or statistics"),
    ],
    "organization": [
        (0.0, "No discernible structure"),
        (0.5, "Introduction and body paragraphs, but few transitions"),
        (1.0, "Clear introduction, body, counterargument, and conclusion with transitions"),
    ],
    "mechanics": [
        (0.0, "Frequent errors impede reading"),
        (0.6, "Some errors, but the prose is readable"),
        (1.0, "Clean grammar, spelling, and punctuation with varied sentences"),
    ],
}

DEFAULT_ANCHORS = [
    (0.0, "Does not meet the criterion"),
    (0.5, "Partially meets the criterion"),
    (1.0, "Fully meets the criterion"),
]


def _criterion_type(name: str) -> str:
    lowered = name.lower()
    for key in ("thesis", "evidence", "organization", "mechanics"):
        if key in lowered:
            return key
    return "generic"


def _anchors(name: str, max_points: float) -> list[dict[str, Any]]:
    library = ANCHOR_LIBRARY.get(_criterion_type(name), DEFAULT_ANCHORS)
    return [
        {"points": round(fraction * max_points, 1), "description": description}
        for fraction, description in library
    ]


@dataclass(frozen=True)
class PromptTemplate:
    version: str
    system: str
    user_template: str
    description: str

    def render(
        self,
        assignment_title: str,
        prompt_text: str,
        submission_text: str,
        criteria: Sequence[CriterionLike],
        anchored: bool,
    ) -> str:
        rubric_items: list[dict[str, Any]] = []
        for criterion in criteria:
            item: dict[str, Any] = {
                "name": criterion.name,
                "max_points": criterion.max_points,
            }
            if anchored:
                item["description"] = criterion.description
                item["anchors"] = _anchors(criterion.name, criterion.max_points)
            rubric_items.append(item)
        return (
            self.user_template.replace("__ASSIGNMENT_TITLE__", assignment_title)
            .replace("__PROMPT_TEXT__", prompt_text)
            .replace("__SUBMISSION_TEXT__", submission_text)
            .replace("__RUBRIC_JSON__", json.dumps(rubric_items, indent=2, ensure_ascii=False))
        )


_RESPONSE_CONTRACT = """
Return exactly one JSON object, with no markdown fences and no commentary:
{"criteria": [{"criterion_name": "string", "points": number, "confidence": number,
"justification": "string"}], "summary_comment": "string"}

Rules:
- Use every rubric criterion name exactly once; do not invent criteria.
- points must be between 0 and that criterion's max_points.
- confidence is a number from 0 to 1 expressing your certainty in that score.
- summary_comment is 2-4 sentences of feedback addressed to the student.
"""

V1_SYSTEM = (
    "You are an experienced writing instructor grading a student essay against a rubric. "
    "Be consistent and fair. Return only valid JSON."
)

V2_SYSTEM = (
    "You are a rigorous writing instructor calibrating each score against explicit rubric "
    "anchors. For every criterion, quote or closely paraphrase a phrase from the submission "
    "that justifies the score you awarded. Do not award points the submission has not earned. "
    "Return only valid JSON."
)

V1_USER = (
    "ASSIGNMENT: __ASSIGNMENT_TITLE__\n"
    "ASSIGNMENT PROMPT:\n__PROMPT_TEXT__\n\n"
    'SUBMISSION:\n"""\n__SUBMISSION_TEXT__\n"""\nEND_SUBMISSION\n\n'
    "RUBRIC_JSON:\n__RUBRIC_JSON__\nEND_RUBRIC_JSON\n"
    + _RESPONSE_CONTRACT
)

V2_USER = (
    "ASSIGNMENT: __ASSIGNMENT_TITLE__\n"
    "ASSIGNMENT PROMPT:\n__PROMPT_TEXT__\n\n"
    'SUBMISSION:\n"""\n__SUBMISSION_TEXT__\n"""\nEND_SUBMISSION\n\n'
    "RUBRIC_JSON:\n__RUBRIC_JSON__\nEND_RUBRIC_JSON\n\n"
    "For each criterion:\n"
    "1. Compare the submission to every anchor level and choose the closest one.\n"
    "2. Quote a short phrase from the submission in the justification.\n"
    "3. Lower confidence when the submission is short or sits between anchors.\n"
    + _RESPONSE_CONTRACT
)

REGISTRY: dict[str, PromptTemplate] = {
    "v1_basic": PromptTemplate(
        version="v1_basic",
        system=V1_SYSTEM,
        user_template=V1_USER,
        description="Basic rubric prompt: criterion names, max points, JSON contract.",
    ),
    "v2_criterion_anchored": PromptTemplate(
        version="v2_criterion_anchored",
        system=V2_SYSTEM,
        user_template=V2_USER,
        description=(
            "Criterion-anchored prompt: inlines each criterion description and point anchors, "
            "requires per-criterion justification quoting the submission."
        ),
    ),
}

ANCHORED_VERSIONS = {"v2_criterion_anchored"}


def get_prompt(version: str) -> PromptTemplate:
    try:
        return REGISTRY[version]
    except KeyError as exc:
        raise ValueError(
            f"Unknown prompt version {version!r}; available: {', '.join(REGISTRY)}"
        ) from exc

