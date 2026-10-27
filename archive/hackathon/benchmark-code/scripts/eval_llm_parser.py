"""Live accuracy of the parser modes on dev questions (calls the Claude API).

  uv run --env-file .env python scripts/eval_llm_parser.py --per-kind 3
  uv run --env-file .env python scripts/eval_llm_parser.py --per-kind 3 --paraphrase   # reworded questions

--paraphrase first asks Claude to reword each question (same names and numbers, different sentence), which
simulates Sunday questions phrased unlike the templates. Accuracy = kind + every `inputs` slot resolved right."""

import argparse
import random
import sys
from collections import Counter
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.llm_parser import MODEL, LlmQuestionParser  # noqa: E402
from agent.parsing import QuestionUnderstanding  # noqa: E402
from core.question_parser import ParseError  # noqa: E402
from tests.test_question_parser import building, labelled_questions  # noqa: E402

SEED = 7
PARAPHRASE_PROMPT = """Reword this question so that it asks exactly the same thing in a different sentence, as a
person might say it. Keep every room name, floor name, number and lift/stair name exactly as written. Keep the
final "Finish with a line ..." instruction unchanged. Reply with the reworded question only.

{question}"""


def sample(per_kind: int) -> list[tuple[Path, dict]]:
    by_kind: dict[str, list] = {}
    for item in labelled_questions():
        if "/dev/" in str(item[0]):
            by_kind.setdefault(item[1]["kind"], []).append(item)
    rng = random.Random(SEED)
    return [item for kind in sorted(by_kind) for item in rng.sample(by_kind[kind], min(per_kind, len(by_kind[kind])))]


def paraphrase(client: anthropic.Anthropic, text: str) -> str:
    reply = client.messages.create(
        model=MODEL, max_tokens=4000, output_config={"effort": "low"},
        messages=[{"role": "user", "content": PARAPHRASE_PROMPT.format(question=text)}],
    )
    return next(block.text for block in reply.content if block.type == "text").strip()


def correct(parsed, question: dict) -> bool:
    expected = question["inputs"]
    return parsed.kind == question["kind"] and all(
        expected[key] in parsed.alternatives.get(key, [parsed.params.get(key)]) for key in expected
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-kind", type=int, default=3)
    parser.add_argument("--paraphrase", action="store_true")
    parser.add_argument("--modes", nargs="+", default=["regex", "llm", "hybrid"])
    arguments = parser.parse_args()
    client = anthropic.Anthropic()
    llm = LlmQuestionParser(client)
    results: Counter[tuple[str, str, bool]] = Counter()
    for directory, question in sample(arguments.per_kind):
        text = paraphrase(client, question["question"]) if arguments.paraphrase else question["question"]
        for mode in arguments.modes:
            try:
                ok = correct(QuestionUnderstanding(mode, llm).parse(text, building(directory)), question)
            except ParseError:
                ok = False
            results[(mode, question["kind"], ok)] += 1
        print(f"{question['id']:34s} {question['kind']:26s} {text[:90]}")
    print(f"\n{'kind':26s} " + " ".join(f"{mode:>9s}" for mode in arguments.modes))
    for kind in sorted({kind for _, kind, _ in results}):
        cells = [f"{results[(m, kind, True)]}/{results[(m, kind, True)] + results[(m, kind, False)]}" for m in arguments.modes]
        print(f"{kind:26s} " + " ".join(f"{cell:>9s}" for cell in cells))
    print(f"\nLLM parser tokens: {llm.usage}")


if __name__ == "__main__":
    main()
