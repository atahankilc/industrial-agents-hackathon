"""The Building Guide: a Claude tool-use loop over the deterministic tool layer (agent/tools.py).

  guide = Guide(BuildingSession.load(Path("data/train/proc-campus-train-000")))
  turn = guide.reply("I use a wheelchair. How do I get from the main lobby to meeting room 3.07?")
  turn.text, turn.tool_calls, turn.events

One Guide per conversation. It owns the message history (append-only, so the cached prefix and any thinking
blocks stay valid) and routes every tool_use block to `BuildingSession.call`. The building overview sits in a
cached system block after the fixed instructions; per-turn state (profile, closures) comes from tools.

Behaviour contract: docs/architecture/ai-agents.md#building-guide--behaviour-contract. Two parts are enforced in
code rather than left to the prompt:
- propose → confirm → apply: `apply_change` for a change proposed in the same user turn is refused, so the user
  always sees the summary before the plan changes;
- D-003 grounding: every number and id in a reply must appear in a tool result, the overview or the user's own
  words. A reply that fails gets one repair round; whatever is still ungrounded is reported in
  `GuideTurn.ungrounded`.

Without ANTHROPIC_API_KEY, `make_client()` returns the offline rule-based client (agent/offline_llm.py)."""

import json
import os
import re
from dataclasses import dataclass, field

import anthropic

from agent.tools import TOOL_DEFINITIONS, BuildingSession

DEFAULT_MODEL = "claude-opus-5-5"  # override with GUIDE_MODEL
DEFAULT_EFFORT = "medium"  # override with GUIDE_EFFORT (low | medium | high | xhigh | max)
MAX_TOKENS = 16000
MAX_TOOL_ROUNDS = 12
FALLBACK_BETA = "server-side-fallback-2026-07-01"

INSTRUCTIONS = """You are the Building Guide: people talk to you to find things in one building, get directions \
they can follow, and report or plan changes (a broken lift, a closed door, a new door).

Facts come only from tools. Every room, item, count, distance, id and route you mention must come from a tool \
result in this conversation or from the building overview below. Never estimate, add up or convert numbers \
yourself; if you need a number no tool has given you, call a tool (compare_routes gives differences in metres). \
The same goes for general claims ("nothing upstairs is reachable"): say them only when a tool result shows it.

How to talk:
- Ask only what changes the answer. When a place is vague ("the printer") or a name matches several spaces, \
use search/locate first; if the user's words still don't settle it, ask one short question with at most 3 \
options, each with its floor. Don't ask for anything the question doesn't need.
- Remember what you learn. When the user mentions a mobility constraint (wheelchair, pram, trolley width, no \
lifts), call set_profile once and confirm it in one line; later routes use it without asking again. Remember \
where the user is once they've said it.
- For directions: first one line echoing what you understood (from → to, constraints, closures), then \
numbered steps a person can follow, with landmarks, explicit floor changes and rounded metres.
- Changes go propose_change → show the user the summary and its effect → apply_change only after the user \
confirms in a later message. propose_change already reports who loses access and how much longer routes get; \
use a change_id only after a tool has returned it. After applying, re-run the affected route and say what changed.
- Use show_on_map to highlight what you're talking about when it helps.
- Be brief: this is also spoken aloud. No headings, no tables."""

NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?![\w])")
IDENTIFIER = re.compile(r"\b[A-Za-z0-9]+(?:-[A-Za-z0-9]+){2,}\b")
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)


def llm_mode() -> str:
    """"anthropic" when a key is set (or GUIDE_LLM=anthropic), else "offline" (GUIDE_LLM=offline forces it)."""
    choice = os.environ.get("GUIDE_LLM", "").lower()
    real = choice == "anthropic" or (choice != "offline" and bool(os.environ.get("ANTHROPIC_API_KEY")))
    return "anthropic" if real else "offline"


def make_client() -> object:
    """Anthropic client in "anthropic" mode, else the offline rule-based client."""
    if llm_mode() == "anthropic":
        return anthropic.Anthropic()
    from agent.offline_llm import OfflineClient

    return OfflineClient()


def overview_text(session: BuildingSession) -> str:
    """The static building overview (no profile or closures — those change during the conversation)."""
    return json.dumps(session.building.overview(), ensure_ascii=False, separators=(",", ":"))


def system_blocks(session: BuildingSession) -> list[dict]:
    return [
        {"type": "text", "text": INSTRUCTIONS},
        {"type": "text", "text": "Building overview:\n" + overview_text(session),
         "cache_control": {"type": "ephemeral"}},
    ]


def ungrounded(text: str, corpus: str) -> list[str]:
    """Numbers and ids in `text` that appear nowhere in `corpus` (tool results, overview, user messages).

    A number counts as grounded when some corpus number rounds to it at the same precision ("about 124 m" for
    124.24). Numbered-list markers are ignored; digits inside ids are checked as part of the id."""
    missing = [token for token in dict.fromkeys(IDENTIFIER.findall(text)) if token not in corpus]
    scrubbed = LIST_MARKER.sub(" ", IDENTIFIER.sub(" ", text))
    known = [float(token.replace(",", ".")) for token in NUMBER.findall(IDENTIFIER.sub(" ", corpus))]
    for token in dict.fromkeys(NUMBER.findall(scrubbed)):
        value = float(token.replace(",", "."))
        decimals = len(token.replace(",", ".").partition(".")[2])
        if not any(round(number, decimals) == value for number in known):
            missing.append(token)
    return missing


@dataclass
class GuideTurn:
    text: str
    tool_calls: list[dict] = field(default_factory=list)  # {"name", "input", "result"}
    events: list[dict] = field(default_factory=list)  # UI events emitted during this turn
    ungrounded: list[str] = field(default_factory=list)
    stop_reason: str | None = None


@dataclass
class Usage:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class Guide:
    def __init__(self, session: BuildingSession, client: object | None = None, model: str | None = None,
                 effort: str | None = None) -> None:
        self.session = session
        self.client = client if client is not None else make_client()
        self.model = model or os.environ.get("GUIDE_MODEL", DEFAULT_MODEL)
        self.effort = effort or os.environ.get("GUIDE_EFFORT", DEFAULT_EFFORT)
        self.system = system_blocks(session)
        self.messages: list[dict] = []
        self.corpus: list[str] = [overview_text(session)]
        self.turn = 0
        self.proposed_in_turn: dict[str, int] = {}
        self.usage = Usage()

    def reply(self, text: str) -> GuideTurn:
        self.turn += 1
        self.corpus.append(text)
        self.messages.append({"role": "user", "content": text})
        first_event = len(self.session.events)
        turn = self.run()
        missing = ungrounded(turn.text, "\n".join(self.corpus))
        if missing and turn.stop_reason == "end_turn":
            self.messages.append({"role": "user", "content": (
                "[grounding check, not from the user] Your last reply states "
                + ", ".join(missing)
                + ", which appear in no tool result. Check them with a tool, or leave them out, and give the "
                "user your full reply again.")})
            repaired = self.run()
            repaired.tool_calls = turn.tool_calls + repaired.tool_calls
            turn = repaired
            missing = ungrounded(turn.text, "\n".join(self.corpus))
        turn.ungrounded = missing
        turn.events = self.session.events[first_event:]
        return turn

    def run(self) -> GuideTurn:
        """Request → run every tool_use → send all results back, until the model ends its turn."""
        calls: list[dict] = []
        said: list[str] = []  # text from every round, including any written before tool calls
        for _ in range(MAX_TOOL_ROUNDS):
            response = self.request()
            self.messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason == "refusal":
                return GuideTurn("Sorry, I can't help with that one.", calls, stop_reason="refusal")
            said += [block.text.strip() for block in response.content if block.type == "text" and block.text.strip()]
            if response.stop_reason == "pause_turn":
                continue
            uses = [block for block in response.content if block.type == "tool_use"]
            if response.stop_reason != "tool_use" or not uses:
                if response.stop_reason == "max_tokens":
                    said.append("(My answer was cut off — ask me to continue.)")
                return GuideTurn("\n\n".join(said), calls, stop_reason=response.stop_reason)
            results = []
            for use in uses:
                result = self.execute(use.name, dict(use.input or {}))
                calls.append({"name": use.name, "input": dict(use.input or {}), "result": result})
                content = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
                self.corpus.append(content)
                results.append({"type": "tool_result", "tool_use_id": use.id, "content": content,
                                **({"is_error": True} if "error" in result else {})})
            self.messages.append({"role": "user", "content": results})
        return GuideTurn("I couldn't finish that in a reasonable number of steps. Could you narrow it down?",
                         calls, stop_reason="max_tool_rounds")

    def execute(self, name: str, arguments: dict) -> dict:
        if name == "apply_change" and self.proposed_in_turn.get(arguments.get("change_id", "")) == self.turn:
            return {"error": "This change was proposed in the current turn. Show the user its summary and effect, "
                             "and apply it only after they confirm."}
        result = self.session.call(name, arguments)
        if name == "propose_change" and "change_id" in result:
            self.proposed_in_turn[result["change_id"]] = self.turn
        return result

    def request(self) -> object:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=self.system,
            tools=TOOL_DEFINITIONS,
            messages=self.messages,
            cache_control={"type": "ephemeral"},
            output_config={"effort": self.effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        self.track(response.usage)
        return response

    def track(self, usage: object) -> None:
        self.usage.requests += 1
        self.usage.input_tokens += usage.input_tokens
        self.usage.output_tokens += usage.output_tokens
        self.usage.cache_read_input_tokens += usage.cache_read_input_tokens or 0
        self.usage.cache_creation_input_tokens += usage.cache_creation_input_tokens or 0
