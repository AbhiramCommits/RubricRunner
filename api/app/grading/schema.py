from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, Field


class RubricLike(Protocol):
    name: str
    max_points: float


class CriterionGrade(BaseModel):
    criterion_name: str = Field(min_length=1)
    points: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    justification: str = ""


class GradeResult(BaseModel):
    criteria: list[CriterionGrade] = Field(min_length=1)
    summary_comment: str = Field(min_length=1)

    def validate_against(self, rubric: Sequence[RubricLike]) -> None:
        """Reject unknown names, duplicates, missing criteria, and out-of-range points."""
        expected: dict[str, float] = {
            criterion.name: float(criterion.max_points) for criterion in rubric
        }
        if not expected:
            raise ValueError("Rubric has no criteria")

        seen: set[str] = set()
        for item in self.criteria:
            if item.criterion_name not in expected:
                raise ValueError(
                    f"Unknown criterion {item.criterion_name!r}; expected one of "
                    f"{sorted(expected)}"
                )
            if item.criterion_name in seen:
                raise ValueError(f"Duplicate criterion {item.criterion_name!r}")
            seen.add(item.criterion_name)
            max_points = expected[item.criterion_name]
            if item.points > max_points:
                raise ValueError(
                    f"points {item.points} for {item.criterion_name!r} exceed max {max_points}"
                )

        missing = sorted(set(expected) - seen)
        if missing:
            raise ValueError(f"Missing criteria: {missing}")
