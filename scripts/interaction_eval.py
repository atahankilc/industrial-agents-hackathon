"""Interaction eval: a simulated tricky user talks to the Building Guide, then an LLM judge scores the conversation
with the organisers' Interaction rubric (archive/hackathon/docs/challenge/brief.md#judging). Calls the Claude API, costs money
(~$0.1–0.3 per scenario).

  uv run --env-file .env python scripts/interaction_eval.py                       # every tests/interaction_scenarios/*.json
  uv run --env-file .env python scripts/interaction_eval.py tests/interaction_scenarios/first_day_coffee.json
  uv run --env-file .env python scripts/interaction_eval.py --repeat 3 --model claude-sonnet-5-5 --effort low

A scenario names the building, the channel (text | voice), who the user is, what they want, and what they know but
only say when asked or when it comes up. The simulated user (--user-model) plays that person until the goal is
reached, they give up, or max_turns. The judge (--judge-model) gets the scenario, the transcript (with the Guide's
tool calls and ungrounded values) and scores 1–5: asks_only_needed, shows_understanding, followable_directions,
remembers_context, plus goal_reached and the issues it saw. Voice scenarios show the judge what was spoken.

Scores are a second opinion, not ground truth: route correctness is checked by scripts/eval_guide.py. Prints one row
per run and the averages; the full transcripts and verdicts go to agent_output/interaction_eval/ (git-ignored)."""

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.agents.guide import Guide, GuideTurn, Usage, make_client  # noqa: E402
from backend.agents.tools import BuildingSession  # noqa: E402
from scripts.live_guide import cost  # noqa: E402

SCENARIOS = ROOT / "tests" / "interaction_scenarios"
SCENARIO_KEYS = {"building", "channel", "persona", "goal", "knows", "max_turns"}
DEFAULT_MODEL = "claude-opus-5-5"  # simulated user and judge; override with --user-model / --judge-model
MAX_TOKENS = 16000
CRITERIA = ("asks_only_needed", "shows_understanding", "followable_directions", "remembers_context")

USER_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "done": {"type": "boolean"},
        "goal_reached": {"type": "boolean"},
    },
    "required": ["message", "done", "goal_reached"],
    "additionalProperties": False,
}
SCORE = {
    "type": "object",
    "properties": {"score": {"type": "integer", "enum": [1, 2, 3, 4, 5]}, "evidence": {"type": "string"}},
    "required": ["score", "evidence"],
    "additionalProperties": False,
}
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        **{name: SCORE for name in CRITERIA},
        "goal_reached": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
    },
    "required": [*CRITERIA, "goal_reached", "issues"],
    "additionalProperties": False,
}

USER_RULES = """You play a person who is talking to a building guide app (an AI assistant that knows one \
building). Stay in character: write only what this person would say or type to the app, in their voice and \
language, short and natural, like a real user (not like a tester). Don't help the guide: share a fact from \
"what you know" only when the guide asks for it or when a real person would naturally mention it. Never invent \
room names or facts about the building; if the guide offers options, pick the one that fits your goal.

Each time, reply with JSON: `message` = your next message to the guide (empty when done), `done` = true when \
your goal is reached, the guide clearly can't help, or you'd give up, `goal_reached` = true only if the guide \
gave you what your goal needs (e.g. directions you could follow to the right place)."""

JUDGE_RULES = """You judge a conversation between a user and a building guide app for a hackathon. The organisers \
score "Interaction" with a short scripted conversation with tricky users and this rubric: asks only what it \
needs, shows what it understood, directions a person can follow. Voice counts.

Score each criterion 1–5 (5 = a demanding human judge would have nothing to fix, 3 = works but clear flaws, \
1 = fails it) with one or two sentences of evidence quoting the transcript:
- asks_only_needed: asks only questions whose answer changes the result, one at a time; never asks for what the \
user already said; doesn't pad replies with offers or needless confirmations.
- shows_understanding: echoes what it understood (start, destination, constraints, closures) before acting on it; \
confirms a profile or a change in one line; shows a change before applying it.
- followable_directions: steps a person can follow on the spot (landmarks, explicit floor changes, rounded \
distances; for voice: a few short spoken sentences, no ids or symbols). If the conversation needed no \
directions, score how clear and usable the answers were.
- remembers_context: keeps what the user said earlier (location, mobility needs, choices) and uses it without \
asking again.
Also: `goal_reached` = did the user get what their goal needs; `issues` = concrete problems (wrong-looking facts, \
ungrounded values, contradictions, stiff or robotic phrasing), empty if none.

The guide's facts come from building tools you see as TOOLS lines (long results are cut, marked "…(cut)"; don't \
flag a value as unsupported when the cut may hide it). Trust their results, but flag replies that contradict them \
or state values marked UNGROUNDED. Judge only the guide, not the user."""


def load_scenario(path: Path) -> dict:
    scenario = json.loads(Path(path).read_text())
    unknown = set(scenario) - SCENARIO_KEYS
    if unknown:
        raise ValueError(f"{path}: unknown scenario keys {sorted(unknown)}")
    missing = {"building", "persona", "goal"} - set(scenario)
    if missing:
        raise ValueError(f"{path}: missing scenario keys {sorted(missing)}")
    if scenario.setdefault("channel", "text") not in ("text", "voice"):
        raise ValueError(f"{path}: channel must be text or voice")
    scenario.setdefault("knows", [])
    scenario.setdefault("max_turns", 6)
    return scenario


def add_usage(total: Usage, usage: object) -> None:
    total.requests += 1
    total.input_tokens += usage.input_tokens
    total.output_tokens += usage.output_tokens
    total.cache_read_input_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
    total.cache_creation_input_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0


def structured(client: object, model: str, effort: str, system: list[dict], messages: list[dict], schema: dict,
               usage: Usage) -> dict:
    """One structured-output request; raises RuntimeError on a refusal, a cut-off or unparsable JSON."""
    response = client.messages.create(
        model=model, max_tokens=MAX_TOKENS, system=system, messages=messages,
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    add_usage(usage, response.usage)
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"{model} stopped with {response.stop_reason}")
    text = next((block.text for block in response.content if block.type == "text"), "")
    try:
        return json.loads(text)
    except ValueError as error:
        raise RuntimeError(f"{model} returned no JSON: {text[:200]}") from error


def scenario_text(scenario: dict) -> str:
    knows = "\n".join(f"- {fact}" for fact in scenario["knows"]) or "- nothing beyond your goal"
    return (f"Who you are: {scenario['persona']}\nYour goal: {scenario['goal']}\n"
            f"What you know (say it only when asked or when it naturally comes up):\n{knows}")


class SimulatedUser:
    """The person from the scenario, played by Claude. Roles are flipped: the guide's replies are its user turns."""

    def __init__(self, scenario: dict, client: object, model: str, effort: str = "low") -> None:
        self.client, self.model, self.effort = client, model, effort
        self.system = [{"type": "text", "text": USER_RULES},
                       {"type": "text", "text": scenario_text(scenario)}]
        self.voice = scenario["channel"] == "voice"
        self.messages: list[dict] = [{"role": "user", "content": (
            "[The guide app is open" + (" and listening; you speak to it" if self.voice else "")
            + ". Send your first message.]")}]
        self.usage = Usage()

    def next(self) -> dict:
        reply = structured(self.client, self.model, self.effort, self.system, self.messages, USER_SCHEMA, self.usage)
        self.messages.append({"role": "assistant", "content": json.dumps(reply, ensure_ascii=False)})
        return reply

    def hear(self, guide_text: str) -> None:
        self.messages.append({"role": "user", "content": guide_text})


TOOL_RESULT_CHARS = 1500  # enough for route steps and search hits; the judge must see what the Guide saw
DROPPED_KEYS = {"space_path", "element_path"}  # ids only; the steps say the same in words


def tool_line(call: dict) -> str:
    result = {key: value for key, value in call["result"].items() if key not in DROPPED_KEYS}
    text = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    if len(text) > TOOL_RESULT_CHARS:
        text = text[:TOOL_RESULT_CHARS] + "…(cut)"
    return f"{call['name']}({json.dumps(call['input'], ensure_ascii=False)}) → {text}"


def transcript_text(turns: list[dict]) -> str:
    lines = []
    for number, turn in enumerate(turns, 1):
        lines.append(f"[{number}] USER: {turn['user']}")
        if turn["tools"]:
            lines.append("TOOLS: " + " | ".join(turn["tools"]))
        lines.append(f"GUIDE{' (spoken)' if turn['spoken'] else ''}: {turn['spoken'] or turn['reply']}")
        if turn["ungrounded"]:
            lines.append(f"UNGROUNDED: {turn['ungrounded']}")
    return "\n".join(lines)


def judge(scenario: dict, turns: list[dict], client: object, model: str, effort: str, usage: Usage) -> dict:
    content = (f"Scenario (channel: {scenario['channel']}):\n{scenario_text(scenario)}\n\n"
               f"Transcript:\n{transcript_text(turns)}")
    return structured(client, model, effort, [{"type": "text", "text": JUDGE_RULES}],
                      [{"role": "user", "content": content}], JUDGE_SCHEMA, usage)


@dataclass
class Run:
    scenario: str
    turns: list[dict] = field(default_factory=list)
    user_goal_reached: bool = False
    verdict: dict | None = None
    error: str | None = None
    seconds: float = 0.0
    guide_cost: float = 0.0
    eval_cost: float = 0.0

    def scores(self) -> dict[str, int]:
        return {name: self.verdict[name]["score"] for name in CRITERIA} if self.verdict else {}


def run_scenario(path: Path, guide_client: object, eval_client: object, args: argparse.Namespace) -> Run:
    scenario = load_scenario(path)
    run = Run(path.stem)
    guide = Guide(BuildingSession.load(ROOT / scenario["building"]), client=guide_client, model=args.model,
                  effort=args.effort)
    user = SimulatedUser(scenario, eval_client, args.user_model)
    judge_usage = Usage()
    started = time.perf_counter()
    try:
        for _ in range(scenario["max_turns"]):
            said = user.next()
            run.user_goal_reached = said["goal_reached"]
            if said["done"] or not said["message"].strip():
                break
            turn: GuideTurn = guide.reply(said["message"], channel=scenario["channel"])
            run.turns.append({"user": said["message"], "reply": turn.text, "spoken": turn.spoken,
                              "tools": [tool_line(call) for call in turn.tool_calls], "ungrounded": turn.ungrounded})
            user.hear(turn.spoken or turn.text)
        run.verdict = judge(scenario, run.turns, eval_client, args.judge_model, args.judge_effort, judge_usage)
    except (RuntimeError, anthropic.APIError) as error:
        run.error = f"{type(error).__name__}: {error}"
    run.seconds = time.perf_counter() - started
    run.guide_cost = cost(guide.usage, guide.model)
    run.eval_cost = cost(user.usage, args.user_model) + cost(judge_usage, args.judge_model)
    return run


def summary_line(run: Run) -> str:
    if run.error:
        return f"{run.scenario:<24} ERROR {run.error}"
    scores = " ".join(f"{name.split('_')[0][:5]}={value}" for name, value in run.scores().items())
    goal = f"goal user={'Y' if run.user_goal_reached else 'N'} judge={'Y' if run.verdict['goal_reached'] else 'N'}"
    return (f"{run.scenario:<24} {scores}  {goal}  {len(run.turns)} turns  {run.seconds:.0f}s  "
            f"guide ${run.guide_cost:.3f} + eval ${run.eval_cost:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulated tricky users + LLM judge for the Guide (live API).")
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--repeat", type=int, default=1, help="runs per scenario (the simulated user varies)")
    parser.add_argument("--model", default=None, help="Guide model (default GUIDE_MODEL / backend.agents.guide)")
    parser.add_argument("--effort", default=None, help="Guide effort (default GUIDE_EFFORT / backend.agents.guide)")
    parser.add_argument("--user-model", default=DEFAULT_MODEL)
    parser.add_argument("--judge-model", default=DEFAULT_MODEL)
    parser.add_argument("--judge-effort", default="medium")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    files = args.files or sorted(SCENARIOS.glob("*.json"))
    guide_client, eval_client = make_client(), anthropic.Anthropic()
    runs = []
    for path in files:
        for _ in range(args.repeat):
            run = run_scenario(path, guide_client, eval_client, args)
            runs.append(run)
            print(summary_line(run))
            for issue in (run.verdict or {}).get("issues", []):
                print(f"    - {issue}")
    scored = [run for run in runs if run.verdict]
    if scored:
        averages = {name: statistics.mean(run.scores()[name] for run in scored) for name in CRITERIA}
        goals = sum(run.verdict["goal_reached"] for run in scored)
        print("\nAVERAGE " + " ".join(f"{name}={value:.2f}" for name, value in averages.items())
              + f"  goal {goals}/{len(scored)}  errors {len(runs) - len(scored)}  cost guide "
              f"${sum(r.guide_cost for r in runs):.2f} + eval ${sum(r.eval_cost for r in runs):.2f}")
    out = args.out or ROOT / "agent_output" / "interaction_eval" / f"{int(time.time())}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"args": {k: str(v) for k, v in vars(args).items()},
                               "runs": [asdict(run) for run in runs]}, ensure_ascii=False, indent=1))
    print(f"saved {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    sys.exit(0 if len(scored) == len(runs) else 1)


if __name__ == "__main__":
    main()
