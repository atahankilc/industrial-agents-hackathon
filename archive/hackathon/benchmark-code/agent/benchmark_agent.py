"""Benchmark pipeline: question text → parse → deterministic solver → reply ending in the `Answer:` line.

  uv run python -m benchmark.evaluate data/dev --agent agent.benchmark_agent:answer
  uv run python -m agent.run_benchmark data/test data/test/questions.csv agent_output/test_answers.json \
      --csv team_submission.csv   # see archive/hackathon/SUBMISSION/BENCHMARK.md

No LLM writes any number or id we are scored on (D-003). Parsing is regex-first; PARSER_MODE (D-007) decides
whether an LLM may help understand wording the templates don't cover. When a name in the question matches
several spaces (repeated OSM names, Q-006) the solver runs for every candidate; the answer is kept when they
agree, otherwise the first candidate wins and the reply says so."""

import itertools
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from agent.parsing import QuestionUnderstanding
from core.building_map import BuildingMap
from core.formatter import answer_line, format_reply
from core.question_parser import ParsedQuestion
from core.solvers import SolverResult, solve


@dataclass
class BenchmarkAnswer:
    reply: str
    kind: str | None
    params: dict = field(default_factory=dict)
    result: SolverResult | None = None
    error: str | None = None
    note: str | None = None

    def as_record(self) -> dict:
        """JSON-serialisable form for answers files and logs (structured evidence included)."""
        return {
            "kind": self.kind,
            "params": self.params,
            "answer": None if self.result is None else self.result.value,
            "unit": None if self.result is None else self.result.unit,
            "area_m2": None if self.result is None else self.result.area_m2,
            "evidence": None if self.result is None else self.result.evidence,
            "reply": self.reply,
            "error": self.error,
            "note": self.note,
        }


@cache
def load_building(directory: Path) -> BuildingMap:
    return BuildingMap.load(directory)


_understanding: QuestionUnderstanding | None = None


def understanding() -> QuestionUnderstanding:
    global _understanding
    if _understanding is None:
        _understanding = QuestionUnderstanding()
    return _understanding


def candidate_params(parsed: ParsedQuestion) -> list[dict]:
    """The parsed params, plus one variant per combination of alternative space ids (first = parser's pick)."""
    slots = list(parsed.alternatives)
    if not slots:
        return [parsed.params]
    variants = []
    for combination in itertools.product(*(parsed.alternatives[slot] for slot in slots)):
        variants.append({**parsed.params, **dict(zip(slots, combination, strict=True))})
    first = [variant for variant in variants if variant == parsed.params]
    return first + [variant for variant in variants if variant != parsed.params]


def solve_parsed(building: BuildingMap, parsed: ParsedQuestion) -> BenchmarkAnswer:
    results: list[SolverResult] = []
    errors: list[str] = []
    for params in candidate_params(parsed):
        try:
            results.append(solve(building, parsed.kind, params))
        except Exception as error:  # noqa: BLE001 — one failing candidate must not sink the others
            errors.append(f"{type(error).__name__}: {error}")
    if not results:
        return BenchmarkAnswer(
            reply="I could not work this out from the building data.\nAnswer: unknown",
            kind=parsed.kind,
            params=parsed.params,
            error="; ".join(errors),
        )
    chosen = results[0]
    note = None
    if len(results) > 1:
        lines = {answer_line(building, result) for result in results}
        note = "ambiguous name; candidates agree" if len(lines) == 1 else "ambiguous name; candidates disagree"
    reply = format_reply(building, chosen)
    if note == "ambiguous name; candidates disagree":
        reply = "Several rooms share that name; I used the first match.\n" + reply
    return BenchmarkAnswer(reply=reply, kind=parsed.kind, params=parsed.params, result=chosen, note=note)


def answer_question(building_directory: Path, question_text: str) -> BenchmarkAnswer:
    building = load_building(Path(building_directory))
    try:
        parsed = understanding().parse(question_text, building)
    except Exception as error:  # noqa: BLE001 — ParseError, or the LLM fallback being unavailable
        return BenchmarkAnswer(
            reply="I could not understand this question.\nAnswer: unknown",
            kind=None,
            error=f"{type(error).__name__}: {error}",
        )
    return solve_parsed(building, parsed)


def answer(building_directory: Path, question_text: str) -> str:
    """Entry point for `benchmark.evaluate --agent agent.benchmark_agent:answer`."""
    return answer_question(building_directory, question_text).reply
