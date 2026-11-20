"""LLM provider abstraction.

The provider protocol is deliberately small: one blocking completion call. The
deterministic MockProvider is the oracle for tests, CI and the eval harness;
AnthropicProvider and OpenAIProvider are thin adapters over the official SDKs.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Protocol

from app.config import get_settings


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str) -> str: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        import anthropic

        settings = get_settings()
        key = api_key if api_key is not None else settings.anthropic_api_key
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set; set LLM_PROVIDER=mock for offline use"
            )
        self.model = model or settings.anthropic_model
        self._client = anthropic.Anthropic(api_key=key)

    def complete(self, system: str, user: str) -> str:
        message = self._client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [block.text for block in message.content if block.type == "text"]
        return "".join(parts)


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        from openai import OpenAI

        settings = get_settings()
        key = api_key if api_key is not None else settings.openai_api_key
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set; set LLM_PROVIDER=mock for offline use")
        self.model = model or settings.openai_model
        self._client = OpenAI(api_key=key)

    def complete(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Deterministic offline grader
# ---------------------------------------------------------------------------

EVIDENCE_MARKERS = [
    "according to",
    "%",
    "percent",
    "study",
    "studies",
    "research",
    "report",
    "data",
    "survey",
    "for example",
    "for instance",
    "evidence",
    "found that",
    "published in",
    "journal",
    "university",
    "environmental protection agency",
    "world health organization",
    "institute",
    "association",
    "foundation",
    "agency",
    "epa",
]

TRANSITION_MARKERS = [
    "however",
    "therefore",
    "first",
    "second",
    "third",
    "finally",
    "in conclusion",
    "moreover",
    "additionally",
    "on the other hand",
    "in addition",
    "overall",
    "for example",
    "for instance",
    "another reason",
    "critics",
    "skeptics",
    "opponents",
    "in short",
]

COUNTER_MARKERS = [
    "however",
    "critics",
    "skeptics",
    "opponents",
    "some people",
    "although",
    "on the other hand",
    "even though",
    "but ",
]

CONCLUSION_MARKERS = [
    "in conclusion",
    "overall",
    "in short",
    "to conclude",
    "for these reasons",
    "ultimately",
]

THESIS_MARKERS = [
    "should",
    "must",
    "ought",
    "believe",
    "argue",
    "support",
    "ban",
    "i think",
    "in my opinion",
    "this essay",
]

TYPO_MARKERS = [
    " alot ",
    " definately ",
    " recieve ",
    " teh ",
    " thier ",
    " becuase ",
    " untill ",
    " wich ",
    " dont ",
    " cant ",
    " im ",
    " thats ",
    " its a ",
    " people is ",
    " there is no cars",
    " there are no cars",
]

STOPWORDS = {
    "about",
    "after",
    "also",
    "because",
    "been",
    "before",
    "being",
    "between",
    "could",
    "does",
    "each",
    "from",
    "have",
    "into",
    "more",
    "most",
    "other",
    "over",
    "should",
    "some",
    "such",
    "than",
    "that",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "under",
    "very",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "your",
    "clear",
    "essay",
    "rubric",
    "points",
    "support",
    "supports",
    "explanation",
    "relevant",
    "logical",
    "sentences",
    "readable",
}

TYPE_WORDS: dict[str, list[str]] = {
    "thesis": ["thesis", "position", "argument", "claim", "preview"],
    "evidence": [
        "evidence",
        "statistics",
        "sources",
        "examples",
        "data",
        "cited",
        "support",
        "study",
    ],
    "organization": [
        "structure",
        "introduction",
        "paragraph",
        "transitions",
        "conclusion",
        "counterargument",
        "logical",
    ],
    "mechanics": [
        "grammar",
        "spelling",
        "punctuation",
        "clarity",
        "readable",
        "sentence",
        "varied",
    ],
}


def _sentences(text: str) -> list[str]:
    segments = re.split(r"(?<=[.!?])\s+", text.strip())
    return [segment.strip() for segment in segments if segment.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


def _coverage(text: str, description: str, criterion_type: str) -> float:
    """Share of distinctive rubric-description words that appear in the essay."""
    if not description:
        return 0.0
    description_words = {
        word
        for word in _words(description)
        if len(word) > 4 and word not in STOPWORDS
    }
    description_words |= set(TYPE_WORDS.get(criterion_type, []))
    if not description_words:
        return 0.0
    essay_words = set(_words(text))
    return len(description_words & essay_words) / len(description_words)


def _criterion_type(name: str) -> str:
    lowered = name.lower()
    for key in ("thesis", "evidence", "organization", "mechanics"):
        if key in lowered:
            return key
    return "generic"


def _marker_count(text: str, markers: list[str]) -> int:
    lowered = text.lower()
    return sum(lowered.count(marker) for marker in markers)


def _is_thesis_like(first_sentence: str) -> bool:
    lowered = first_sentence.lower()
    if len(_words(first_sentence)) < 8:
        return False
    return any(marker in lowered for marker in THESIS_MARKERS)


def extract_rubric_from_prompt(prompt: str) -> list[dict[str, Any]]:
    match = re.search(r"RUBRIC_JSON:\s*(.*?)\s*END_RUBRIC_JSON", prompt, re.DOTALL)
    if match:
        parsed = json.loads(match.group(1))
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    return []


def extract_submission_from_prompt(prompt: str) -> str:
    match = re.search(r'SUBMISSION:\s*"""(.*?)"""\s*END_SUBMISSION', prompt, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r'SUBMISSION:\s*"""(.*?)"""', prompt, re.DOTALL)
    return match.group(1).strip() if match else prompt


class MockProvider:
    """Offline, deterministic heuristic grader.

    Reads only the submission text and the rubric block from the rendered prompt
    (never gold labels). Scores come from measurable text features so that the
    same submission and prompt always produce the same output.
    """

    name = "mock"
    model = "heuristic-v1"

    def complete(self, system: str, user: str) -> str:
        submission = extract_submission_from_prompt(user)
        rubric = extract_rubric_from_prompt(user)
        criteria: list[dict[str, Any]] = []
        for item in rubric:
            name = str(item.get("name", "Criterion"))
            max_points = float(item.get("max_points", 5) or 5)
            description = str(item.get("description", "") or "")
            points, confidence, justification = self._score_criterion(
                submission, name, max_points, description
            )
            criteria.append(
                {
                    "criterion_name": name,
                    "points": points,
                    "confidence": confidence,
                    "justification": justification,
                }
            )
        summary = self._summary(submission, criteria)
        return json.dumps(
            {"criteria": criteria, "summary_comment": summary},
            ensure_ascii=False,
        )

    # -- feature scoring ---------------------------------------------------
    def _score_criterion(
        self, text: str, name: str, max_points: float, description: str
    ) -> tuple[float, float, str]:
        words = _words(text)
        sentences = _sentences(text)
        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        n_words = len(words)
        intro = " ".join(sentences[:3])
        criterion_type = _criterion_type(name)
        lowered_description = description.lower()
        coverage = _coverage(text, description, criterion_type)
        length_factor = min(1.0, n_words / 200)
        short_penalty = 1.0
        if n_words < 40:
            short_penalty = 0.5
        elif n_words < 80:
            short_penalty = 0.72
        elif n_words < 150:
            short_penalty = 0.9

        if criterion_type == "thesis":
            thesis_like = 1.0 if any(
                _is_thesis_like(sentence) for sentence in sentences[:3]
            ) else 0.0
            preview_signal = 0.0
            if "preview" in lowered_description or "reason" in lowered_description:
                lowered_intro = intro.lower()
                preview_signal = 1.0 if (
                    "because" in lowered_intro
                    or "would" in lowered_intro
                    or "three reasons" in lowered_intro
                    or ("first" in lowered_intro and "second" in lowered_intro)
                ) else 0.0
            fraction = (
                0.65 * thesis_like
                + 0.15 * preview_signal
                + 0.1 * coverage
                + 0.1 * length_factor
            )
            detail = (
                "The opening states a debatable position that previews the essay's reasons."
                if thesis_like and preview_signal
                else "The opening states a debatable position."
                if thesis_like
                else "The opening does not make a clear, arguable claim."
            )
        elif criterion_type == "evidence":
            markers = _marker_count(text, EVIDENCE_MARKERS)
            marker_factor = min(1.0, 0.4 + markers * 0.1) if markers else 0.0
            numeric = len(re.findall(r"\d", text))
            citation_signal = min(1.0, (numeric + markers) / 8.0)
            description_signal = 0.0
            if any(
                token in lowered_description
                for token in ("statistic", "source", "cite", "cited", "data", "research")
            ):
                description_signal = citation_signal
            fraction = (
                0.65 * marker_factor + 0.15 * coverage + 0.2 * description_signal
            )
            detail = (
                f"Uses {markers} evidence marker(s) and {numeric} numeric detail(s); "
                f"rubric-language coverage is {coverage:.0%}."
            )
        elif criterion_type == "organization":
            transitions = _marker_count(text, TRANSITION_MARKERS)
            transition_factor = min(1.0, transitions / 6.0)
            paragraph_depth = 0.0
            for paragraph in paragraphs:
                depth = len(_sentences(paragraph))
                paragraph_depth += min(1.0, depth / 3.0)
            paragraph_factor = min(1.0, paragraph_depth / 4.0)
            counter_signal = 0.0
            conclusion_signal = 0.0
            if "counter" in lowered_description or "opposing" in lowered_description:
                counter_signal = 1.0 if _marker_count(text, COUNTER_MARKERS) else 0.0
            if "conclusion" in lowered_description:
                conclusion_signal = 1.0 if _marker_count(text, CONCLUSION_MARKERS) else 0.0
            description_signal = (counter_signal + conclusion_signal) / 2.0
            fraction = (
                0.35 * transition_factor
                + 0.3 * paragraph_factor
                + 0.15 * length_factor
                + 0.2 * description_signal
            )
            detail = (
                f"Contains {len(paragraphs)} paragraph(s) with {paragraph_depth:.1f} "
                f"depth units, {transitions} structural transition(s), "
                f"counterargument={bool(counter_signal)}, "
                f"conclusion={bool(conclusion_signal)}."
            )
        elif criterion_type == "mechanics":
            starts_upper = (
                sum(1 for sentence in sentences if sentence[:1].isupper()) / len(sentences)
                if sentences
                else 0.0
            )
            terminal = (
                sum(1 for sentence in sentences if sentence[-1:] in ".!?") / len(sentences)
                if sentences
                else 0.0
            )
            avg_len = n_words / len(sentences) if sentences else float(n_words)
            avg_len_score = 1.0 if 10 <= avg_len <= 26 else max(0.2, 1 - abs(avg_len - 18) / 30)
            lengths = [len(_words(sentence)) for sentence in sentences] or [n_words]
            mean_len = sum(lengths) / len(lengths)
            variance = sum((length - mean_len) ** 2 for length in lengths) / len(lengths)
            stdev = math.sqrt(variance)
            variety_signal = min(1.0, (stdev / mean_len) / 0.45) if mean_len else 0.0
            if "varied" not in lowered_description:
                variety_signal = 0.0
            typo_hits = sum(1 for marker in TYPO_MARKERS if marker in f" {text.lower()} ")
            typo_factor = 1.0 - min(1.0, typo_hits / 4.0)
            comma_factor = 1.0 if "," in text else 0.7
            fraction = (
                0.3 * starts_upper
                + 0.2 * terminal
                + 0.25 * avg_len_score
                + 0.1 * typo_factor
                + 0.05 * comma_factor
                + 0.1 * variety_signal
            )
            detail = (
                f"Mechanics proxy: {starts_upper:.0%} of sentences capitalized, average "
                f"sentence {avg_len:.1f} words, {typo_hits} typo signal(s)."
            )
        else:
            fraction = 0.4 * length_factor + 0.6 * coverage
            detail = f"Generic rubric coverage {coverage:.0%}."

        fraction = max(0.0, min(1.0, fraction * short_penalty))
        raw_points = fraction * max_points
        points = float(round(raw_points))
        if fraction > 0.15 and points == 0:
            points = 1.0
        points = min(points, max_points)

        # Confidence is high when the continuous score sits far from a half-point
        # bucket boundary and the essay is long enough to judge.
        distance = abs((raw_points % 1.0) - 0.5) / 0.5  # 1 at integers, 0 at .5
        confidence = 0.6 + 0.35 * distance
        if short_penalty < 1:
            confidence *= short_penalty
        if n_words < 120:
            confidence = min(confidence, 0.64 + 0.2 * (n_words / 120))
        confidence = round(max(0.05, min(0.97, confidence)), 2)

        justification = f"{detail.rstrip('.')}. Awarded {points:g}/{max_points:g}."
        return points, confidence, justification

    def _summary(self, text: str, criteria: list[dict[str, Any]]) -> str:
        total = sum(float(item["points"]) for item in criteria)
        low = [str(item["criterion_name"]) for item in criteria if float(item["confidence"]) < 0.65]
        sentences = _sentences(text)
        opening = sentences[0][:120] if sentences else "the submission"
        note = f"Total {total:g} points."
        if low:
            note += " Confidence is lower on: " + ", ".join(low) + "."
        return (
            f'AI review of the essay opening ("{opening}…"): {note} '
            "The teacher should verify the criterion scores before publishing."
        )


def build_provider(name: str | None = None) -> LLMProvider:
    settings = get_settings()
    choice = (name or settings.llm_provider or "mock").lower()
    if choice == "mock":
        return MockProvider()
    if choice == "anthropic":
        return AnthropicProvider()
    if choice == "openai":
        return OpenAIProvider()
    raise ValueError(f"Unknown LLM_PROVIDER: {choice}")


def normalise_confidence(value: float) -> float:
    """Clamp helper shared by the grader and eval harness."""
    return max(0.0, min(1.0, math.floor(value * 100) / 100))
