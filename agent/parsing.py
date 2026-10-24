"""Configurable question understanding: regex templates, the LLM parser, or both.

  PARSER_MODE=hybrid      regex first; LLM only when no template matches or a slot does not resolve (default)
  PARSER_MODE=regex       deterministic only; unknown wording raises ParseError
  PARSER_MODE=llm         LLM only
  PARSER_MODE=crosscheck  run both; keep the regex result when both succeed, record whether they agree

Decision and rationale: memory-bank/decisions.md (D-007)."""

import os
from typing import Literal

from core.building_map import BuildingMap
from core.question_parser import ParsedQuestion, ParseError, parse_question

Mode = Literal["regex", "llm", "hybrid", "crosscheck"]
MODES: tuple[Mode, ...] = ("regex", "llm", "hybrid", "crosscheck")
DEFAULT_MODE: Mode = "hybrid"


def configured_mode() -> Mode:
    mode = os.environ.get("PARSER_MODE", DEFAULT_MODE)
    if mode not in MODES:
        raise ValueError(f"PARSER_MODE must be one of {MODES}, not '{mode}'")
    return mode


class QuestionUnderstanding:
    def __init__(self, mode: Mode | None = None, llm_parser=None) -> None:
        self.mode = mode or configured_mode()
        self._llm_parser = llm_parser

    @property
    def llm(self):
        if self._llm_parser is None:
            from agent.llm_parser import LlmQuestionParser

            self._llm_parser = LlmQuestionParser()
        return self._llm_parser

    def parse(self, text: str, building_map: BuildingMap) -> ParsedQuestion:
        if self.mode == "llm":
            return self.llm.parse(text, building_map)
        try:
            parsed = parse_question(text, building_map)
            parsed.notes["parser"] = "regex"
        except ParseError:
            if self.mode == "regex":
                raise
            return self.llm.parse(text, building_map)
        if self.mode == "crosscheck":
            parsed.notes["crosscheck"] = self.compare(parsed, text, building_map)
        return parsed

    def compare(self, regex_result: ParsedQuestion, text: str, building_map: BuildingMap) -> str:
        try:
            llm_result = self.llm.parse(text, building_map)
        except ParseError as error:
            return f"llm failed: {error}"
        if (llm_result.kind, llm_result.params) == (regex_result.kind, regex_result.params):
            return "agree"
        return f"disagree: llm={llm_result.kind} {llm_result.params}"
