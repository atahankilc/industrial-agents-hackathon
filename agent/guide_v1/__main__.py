"""Terminal REPL for the Guide: `uv run --env-file .env python -m agent.guide_v1 <building_dir> [--show-tools]`.

Prints each reply, optionally the tool calls behind it, and the turn's token use with an estimated cost. Any error
(API or otherwise) is printed and the conversation continues (the failed turn is rolled back by Guide.turn)."""

import argparse
import json
from collections.abc import Iterable, Iterator
from pathlib import Path

from agent.guide_v1.guide import Guide
from agent.llm_parser import LlmUsage

# USD per million tokens for the default model: input, output, cache read, cache write.
PRICES = {"input": 4.0, "output": 20.0, "cache_read": 0.20, "cache_write": 5.0}


def cost(usage: LlmUsage) -> float:
    return (usage.input_tokens * PRICES["input"] + usage.output_tokens * PRICES["output"]
            + usage.cache_read_input_tokens * PRICES["cache_read"]
            + usage.cache_creation_input_tokens * PRICES["cache_write"]) / 1e6


def usage_line(turn: LlmUsage, total: LlmUsage) -> str:
    return (f"[tokens in/out {turn.input_tokens}/{turn.output_tokens}, cache read {turn.cache_read_input_tokens}, "
            f"cache write {turn.cache_creation_input_tokens} | ~${cost(turn):.4f} this turn, "
            f"~${cost(total):.4f} total]")


def repl(guide: Guide, lines: Iterable[str], show_tools: bool = False) -> None:
    for line in lines:
        if not line.strip():
            continue
        try:
            result = guide.turn(line)
        except Exception as error:
            print(f"error: {error}")
            continue
        if show_tools:
            for call in result.tool_calls:
                print(f"  · {call['name']}({json.dumps(call['input'], ensure_ascii=False)}) → {call['status']}: "
                      f"{call['summary']}")
        print(result.text)
        print(usage_line(result.usage, guide.usage))


def prompt_lines() -> Iterator[str]:
    while True:
        try:
            line = input("> ")
        except EOFError:
            return
        if line.strip().lower() in ("exit", "quit"):
            return
        yield line


def main() -> None:
    parser = argparse.ArgumentParser(description="Talk to a building.")
    parser.add_argument("building_dir", type=Path)
    parser.add_argument("--show-tools", action="store_true", help="print every tool call and its status")
    args = parser.parse_args()
    repl(Guide(args.building_dir), prompt_lines(), show_tools=args.show_tools)


if __name__ == "__main__":
    main()
