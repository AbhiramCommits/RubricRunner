"""Grade a single submission from the command line.

Usage:
    python -m scripts.grade_one --submission-id 1 --prompt-version v2_criterion_anchored
"""

from __future__ import annotations

import argparse
import json

from app.db import SessionLocal
from app.grading.grader import grade_result_payload, grade_submission
from app.grading.providers import build_provider
from app.services import load_submission


def main() -> None:
    parser = argparse.ArgumentParser(description="Grade one submission")
    parser.add_argument("--submission-id", type=int, required=True)
    parser.add_argument("--prompt-version", default="v2_criterion_anchored")
    parser.add_argument("--provider", default=None, help="mock | anthropic | openai")
    args = parser.parse_args()

    with SessionLocal() as session:
        submission = load_submission(session, args.submission_id)
        if submission is None:
            raise SystemExit(f"Submission {args.submission_id} not found")
        assignment = submission.assignment
        provider = build_provider(args.provider)
        version = grade_submission(
            session=session,
            submission=submission,
            assignment=assignment,
            prompt_version=args.prompt_version,
            provider=provider,
        )
        payload = grade_result_payload(version)
        payload["student"] = submission.student.name
        payload["assignment"] = assignment.title
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
