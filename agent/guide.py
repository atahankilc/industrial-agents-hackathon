"""The Building Guide: a Claude tool-use loop over the deterministic tool layer (agent/tools.py).

  guide = Guide(BuildingSession.load(Path("data/train/proc-campus-train-000")))
  turn = guide.reply("I use a wheelchair. How do I get from the main lobby to meeting room 3.07?")
  turn.text, turn.tool_calls, turn.events

One Guide per conversation. It owns the message history (append-only, so the cached prefix and any thinking
blocks stay valid) and routes every tool_use block to `BuildingSession.call`. The building overview sits in a
cached system block after the fixed instructions; per-turn state (profile, closures) comes from tools.

Behaviour contract: docs/architecture/ai-agents.md#building-guide--behaviour-contract. Three parts are enforced
in code rather than left to the prompt:
- propose → confirm → apply: `apply_change` for a change proposed in the same user turn is refused, so the user
  always sees the summary before the plan changes;
- D-003 grounding: every number and id in a reply must appear in a tool result, the overview or the user's own
  words. A reply that fails gets one repair round; whatever is still ungrounded is reported in
  `GuideTurn.ungrounded`;
- profile safety net: a deterministic cue detector (`profile_cues`) reads every user message. If it finds a
  mobility cue ("I use a wheelchair", "I won't take lifts", "my trolley is 80 cm", "I'm out of the cast now")
  that the profile doesn't satisfy after the model's turn, the Guide calls set_profile itself, appends one
  confirmation line and, if the turn already routed, asks the model once to redo the answer under the new
  profile (docs/product/routing-profiles.md#todo-preference-extraction).

Without ANTHROPIC_API_KEY, `make_client()` returns the offline rule-based client (agent/offline_llm.py)."""

import json
import os
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

import anthropic

from agent.rewriter import TranscriptRewriter
from agent.speech import speakable
from agent.tools import PRESETS, PROFILE_FIELDS, TOOL_DEFINITIONS, BuildingSession, RoutingProfile

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
- Remember what you learn. When the user mentions a mobility constraint for themselves or the person they \
guide (wheelchair, pram, trolley width, no lifts, or that a constraint no longer applies), call set_profile \
once, with a preset where one fits, and confirm it in one line, naming any assumed value ("I assumed doors of \
at least 0.8 m; tell me if yours is wider"); later routes use it without asking again. Remember where the user \
is once they've said it.
- For directions: first one line echoing what you understood (from → to, constraints, closures), then \
numbered steps a person can follow, with landmarks, explicit floor changes and rounded metres.
- Changes go propose_change → show the user the summary and its effect → apply_change only after the user \
confirms in a later message. propose_change already reports who loses access and how much longer routes get; \
use a change_id only after a tool has returned it. After applying, re-run the affected route and say what changed.
- Use show_on_map to highlight what you're talking about when it helps. Routes and highlights appear on the \
user's map automatically, so don't offer to show them.
- Be brief: this is also spoken aloud. No headings, no tables."""

# Voice turns (ElevenLabs via /v1/chat/completions) get this operator instruction; agent/speech.py then makes the
# text speakable deterministically. Sent as a mid-conversation system message where the model supports it (keeps
# the cached prefix), otherwise as a note in the user turn.
VOICE_STYLE = ("[voice channel] This reply will be spoken aloud. Use plain spoken sentences: no markdown, lists, "
               "symbols or ids, and at most about three short sentences. For directions, give the first two or "
               "three steps with landmarks and rounded metres, then offer to continue. Facts still come only from "
               "tools.")
SYSTEM_MESSAGE_MODELS = ("claude-opus-5", "claude-opus-4-8", "claude-fable-5", "claude-mythos-5", "claude-sonnet-5-5",
                         "claude-haiku-5-5")
CHANNELS = ("text", "voice")

# A number, also when glued to a unit ("120m", "45m²"); not "3D" or "2nd" (from agent/guide_v1/grounding.py).
UNIT = r"(?:m²|m2|km|cm|mm|min|m|s|%|x)"
NUMBER = re.compile(rf"(?<![\w.])\d+(?:[.,]\d+)?(?={UNIT}?(?!\w))")
TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
IDENTIFIER = re.compile(r"\b[A-Za-z0-9]+(?:-[A-Za-z0-9]+){2,}\b")
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)

# ---------- profile safety net: deterministic mobility cues ----------
# Deliberately conservative: a cue must be a statement about the user or the person they guide ("I use a
# wheelchair", "my mother uses a wheelchair"), not a facility name or question ("the wheelchair lift", "is there
# a wheelchair-accessible toilet?"). Negated cues ("I don't use a wheelchair") are ignored. Anything subtler is
# left to the model.
NEGATION = re.compile(r"\b(?:not|no|never|without|nicht|kein\w*)\b|n't\b")
FACILITY = r"(?![\s-]*(?:lifts?|toilets?|wc|bathrooms?|restrooms?|access\w*|ramps?|friendly|spaces?|parking|park|" \
    r"storage|rooms?|users?))"
WHEELCHAIR = re.compile(
    r"\b(?:use[sd]?|using|in|on|push(?:es|ing)?|with|need[s]?|my|her|his|their|our)\s+"
    r"(?:a\s+|an\s+|my\s+|her\s+|his\s+|their\s+|the\s+)?(?:electric\s+|manual\s+|power\s+)?wheel\s?chair"
    + FACILITY + r"|\b(?:i'm|i am|im|is|she's|he's|we're|are)\s+(?:a\s+)?wheel\s?chair\s+users?\b"
    r"|\b(?:im|sitze im|bin im|fahre)\s+rollstuhl\b|\brollstuhlfahrer(?:in)?\b")
PRAM = re.compile(r"\b(?:pram|stroller|buggy|pushchair|baby carriage|kinderwagen)s?\b" + FACILITY)
SCOOTER = re.compile(r"\bmobility scooter\b|\b(?:my|a|on|in)\s+(?:electric\s+)?scooter\b")
TROLLEY = re.compile(
    r"\b(?:push(?:ing)?|pull(?:ing)?|mov(?:e|ing)|wheel(?:ing)?|with|have|got|my|our)\s+"
    r"(?:a\s+|an\s+|the\s+|my\s+|our\s+)?(?:\w+\s+)?(?:trolley|trolly|cart|pallet(?:\s+jack)?|hospital bed|"
    r"hand\s?truck|dolly|rollwagen)s?\b")
VEHICLE = re.compile(r"\b(?:wheel\s?chair|chair|rollstuhl|scooter|pram|stroller|buggy|pushchair|trolley|trolly|cart|"
                     r"pallet|bed|dolly|hand\s?truck)s?\b")
WIDTH_WORD = re.compile(r"\b(?:wide|width|narrow|across|breit)\b")
WIDTH = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*(mm|cm|m|metres?|meters?)\b")
NO_STAIRS = re.compile(
    r"\b(?:can't|cannot|can not|unable to|won't|don't|do not|shouldn't|mustn't|not able to)\s+"
    r"(?:use|take|climb|do|manage|walk up|go up)\s+(?:the\s+|any\s+)?(?:stairs|steps|staircases?)\b"
    r"|\bno stairs\b(?!\s+(?:here|in|on|to|between|at)\b)|\bavoid(?:ing)?\s+(?:the\s+|any\s+)?(?:stairs|steps)\b"
    r"|\bneed\s+(?:a\s+)?step[- ]free\b|\bkeine treppen\b")
NO_LIFTS = re.compile(
    r"\b(?:i|we|she|he|they)\s+(?:can't|cannot|won't|will not|don't|do not|never|would rather not|"
    r"prefer not to|am not going to)\s+(?:take|use|ride|get in(?:to)?|go in)\s+(?:the\s+|a\s+|any\s+)?"
    r"(?:lifts?|elevators?)\b|\bavoid(?:ing)?\s+(?:lifts|elevators)\b|\bno lifts\b|\bclaustrophobic\b"
    r"|\bkeine?n? (?:aufzug|aufzüge|fahrstuhl)\b")
CLOSURE_TALK = re.compile(r"\b(?:broken|closed|out of order|out of service|not working|blocked)\b")
RESET = re.compile(
    r"\b(?:not|no longer)\s+(?:in|using|on)\s+(?:the|my|a)\s+(?:wheel\s?)?chair\b|\bout of (?:the|my)\s+"
    r"(?:cast|wheel\s?chair|chair)\b|\b(?:off|done with) (?:the|my) crutches\b|\b(?:reset|clear|forget)\s+"
    r"(?:my\s+|the\s+)?(?:routing\s+)?(?:profile|constraints|preferences|settings)\b|\bi can (?:walk|use the stairs|"
    r"take the stairs|climb stairs)(?: normally)? (?:again|now)\b|\bnicht mehr im rollstuhl\b")
NEGATED_CUES = ("wheelchair", "pram", "scooter", "trolley")
PROFILE_TOOLS = {"find_route", "tour", "reachable_rooms", "compare_routes", "propose_change"}


SENTENCE_END = r"[.;!?](?=\s|$)"  # not the dot in "0.7 m" or "3.07"


def sentences(text: str) -> list[str]:
    return [part for part in re.split(SENTENCE_END, text.lower().replace("’", "'")) if part.strip()]


def clauses(sentence: str) -> list[str]:
    return [part for part in re.split(r",|\bbut\b", sentence) if part.strip()]


def negated(clause: str, start: int) -> bool:
    """A negation word among the three words before a cue ("I don't use a wheelchair")."""
    return bool(NEGATION.search(" ".join(clause[:start].split()[-3:])))


def cue_width(sentence: str) -> float | None:
    """A width for the user's vehicle: in a sentence that says wide/width/narrow, or within 30 characters after
    the vehicle word ("my trolley is 80 cm wide", "my chair is narrow, 0.7 m"), between 0.4 and 4 m."""
    if WIDTH_WORD.search(sentence):
        candidates = [WIDTH.search(sentence)]
    else:
        candidates = [WIDTH.search(sentence[vehicle.end():vehicle.end() + 30].partition(",")[0])
                      for vehicle in VEHICLE.finditer(sentence)]
    for match in filter(None, candidates):
        value = float(match[1].replace(",", ".")) / {"mm": 1000, "cm": 100}.get(match[2], 1)
        if 0.4 <= value <= 4.0:
            return round(value, 3)
    return None


def profile_cues(text: str) -> dict | None:
    """Mobility cues in one user message → {"cues": [...], "arguments": set_profile arguments}, or None.

    Stricter cues win over a reset in the same message; a width only counts in a sentence that names a vehicle
    (chair, pram, trolley ...) — the clause may end at a comma, so the sentence is checked too."""
    cues: list[str] = []
    arguments: dict = {}
    parts = [(sentence, clause) for sentence in sentences(text) for clause in clauses(sentence)]
    for sentence, clause in parts:
        for name, pattern in (("wheelchair", WHEELCHAIR), ("pram", PRAM), ("scooter", SCOOTER),
                              ("trolley", TROLLEY), ("no_stairs", NO_STAIRS), ("no_lifts", NO_LIFTS),
                              ("reset", RESET)):
            for match in pattern.finditer(clause):
                if (name in NEGATED_CUES or match[0] == "claustrophobic") and negated(clause, match.start()):
                    continue
                if name == "no_lifts" and CLOSURE_TALK.search(sentence):
                    continue  # "I can't take the lift, it's broken" is a closure, not a preference
                if name not in cues:
                    cues.append(name)
    widths = [width for sentence in sentences(text) if VEHICLE.search(sentence)
              for width in [cue_width(sentence)] if width is not None]
    if widths:
        cues.append("width")
        arguments["min_door_width_m"] = widths[0]
    for preset in ("wheelchair", "pram", "trolley"):  # strictest named preset first
        if preset in cues:
            arguments["preset"] = preset
            break
    if "scooter" in cues or "no_stairs" in cues:
        arguments["step_free"] = True  # no scooter width in the data docs: step-free only, the model asks
    if "no_lifts" in cues:
        if "preset" in arguments:
            arguments["avoid_lifts"] = True
        else:
            arguments["preset"] = "no_lifts"
    if "reset" in cues and not set(cues) - {"reset", "no_lifts", "width"}:
        arguments["preset"] = "default"  # "out of the cast, but I won't take lifts" keeps the lift cue
        if "no_lifts" in cues:
            arguments["avoid_lifts"] = True
    return {"cues": cues, "arguments": arguments} if arguments else None


def profile_satisfies(profile: RoutingProfile, arguments: dict) -> bool:
    """Whether the profile already honours what set_profile(**arguments) would set. A preset's assumed value
    (wheelchair door width) is satisfied by any value the model or user chose."""
    preset = arguments.get("preset")
    wanted, assumed = {}, []
    if preset is not None:
        spec = PRESETS[preset]
        wanted = dict(PRESETS["default"]["values"]) if preset == "default" else dict(spec["values"])
        assumed = spec.get("assumed", [])
    wanted.update({name: arguments[name] for name in PROFILE_FIELDS if name in arguments})
    for name, value in wanted.items():
        current = getattr(profile, name)
        if name in assumed and name not in arguments:
            if current is None:
                return False
        elif name == "min_door_width_m" and value is not None and current is not None:
            if abs(current - value) > 1e-9:
                return False
        elif current != value:
            return False
    return True


def confirmation_line(result: dict) -> str:
    if result.get("preset") == "default" and not any(result["profile"][name] for name in PROFILE_FIELDS):
        return "(Noted: no mobility constraints any more; routes may use stairs and lifts again.)"
    line = f"(Noted: {result['summary']}. I'll use that for every route."
    if "min_door_width_m" in result.get("assumed", []) and "min_door_width_m" in result.get("changed", {}):
        line += " Tell me if your doors need to be wider or can be narrower."
    if "min_door_width_m" in result.get("needs", []):
        line += " How wide is it? Then I'll only use doors wide enough."
    return line + ")"


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
    124.24), or when it is the length of a list in a JSON tool result ("I found 2 options"). Numbered-list markers
    and clock times are ignored; digits inside ids are checked as part of the id."""
    missing = [token for token in dict.fromkeys(IDENTIFIER.findall(text)) if token not in corpus]
    scrubbed = TIME.sub(" ", LIST_MARKER.sub(" ", IDENTIFIER.sub(" ", text)))
    known = [float(token.replace(",", ".")) for token in NUMBER.findall(IDENTIFIER.sub(" ", corpus))]
    known += list_lengths(corpus)
    for token in dict.fromkeys(NUMBER.findall(scrubbed)):
        value = float(token.replace(",", "."))
        decimals = len(token.replace(",", ".").partition(".")[2])
        if not any(half_up(number, decimals) == value for number in known):
            missing.append(token)
    return missing


def half_up(number: float, decimals: int) -> float:
    """round() rounds halves to even (42.5 → 42); people say 43."""
    return float(Decimal(repr(number)).quantize(Decimal(1).scaleb(-decimals), ROUND_HALF_UP))


def list_lengths(corpus: str) -> list[float]:
    """Lengths of the lists of records or names inside the corpus lines that are JSON (tool results)."""
    lengths: list[float] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            if value and all(isinstance(item, (dict, str)) for item in value):
                lengths.append(float(len(value)))
            for item in value:
                walk(item)

    for line in corpus.splitlines():
        if line.startswith(("{", "[")):
            try:
                walk(json.loads(line))
            except ValueError:
                continue
    return lengths


@dataclass
class GuideTurn:
    text: str
    tool_calls: list[dict] = field(default_factory=list)  # {"name", "input", "result"}
    events: list[dict] = field(default_factory=list)  # UI events emitted during this turn
    ungrounded: list[str] = field(default_factory=list)
    stop_reason: str | None = None
    spoken: str | None = None  # voice turns: the reply made speakable (agent/speech.py)
    auto_profile: dict | None = None  # {"cues", "arguments", "result"} when the safety net set the profile
    rewritten: str | None = None  # voice turns: the transcript normalised to the building's names (D-013)


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
        self.profile_note: str | None = None  # tells the model next turn what the safety net set
        # Voice transcripts are normalised first (D-013), only when talking to the real API.
        self.rewriter: TranscriptRewriter | None = (
            TranscriptRewriter(session.building) if isinstance(self.client, anthropic.Anthropic)
            and os.environ.get("GUIDE_REWRITER", "on").lower() != "off" else None)

    def reply(self, text: str, channel: str = "text") -> GuideTurn:
        """One user turn. channel="voice" asks for a spoken style and fills `GuideTurn.spoken`."""
        if channel not in CHANNELS:
            raise ValueError(f"channel must be one of {CHANNELS}")
        self.turn += 1
        self.corpus.append(text)
        rewritten = self.rewriter.rewrite(text) if channel == "voice" and self.rewriter is not None else text
        said = text
        if rewritten != text:  # the model sees both: a nuance the rewrite dropped stays visible
            self.corpus.append(rewritten)
            said = f"{rewritten}\n\n[speech transcript as heard: {text}]"
        note, self.profile_note = self.profile_note, None
        content = f"{note}\n\n{said}" if note else said
        system_role = self.model.startswith(SYSTEM_MESSAGE_MODELS)
        if channel == "voice" and not system_role:
            content = f"{VOICE_STYLE}\n\n{content}"
        self.messages.append({"role": "user", "content": content})
        if channel == "voice" and system_role:
            self.messages.append({"role": "system", "content": VOICE_STYLE})
        first_event = len(self.session.events)
        turn = self.run()
        auto = self.profile_safety_net(text)
        if auto is not None:
            routed = any(call["name"] in PROFILE_TOOLS for call in turn.tool_calls)
            if routed and turn.stop_reason == "end_turn":
                self.messages.append({"role": "user", "content": (
                    f"[profile check, not from the user] From the user's words I set their routing profile to: "
                    f"{auto['result']['summary']}. Redo any route or reachability in your reply under this profile "
                    "and give the user your full reply again.")})
                redone = self.run()
                redone.tool_calls = turn.tool_calls + redone.tool_calls
                turn = redone
            else:
                self.profile_note = (f"[profile note, not from the user] After your last reply I set the user's "
                                     f"routing profile to: {auto['result']['summary']}.")
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
        if auto is not None:
            turn.auto_profile = auto
            turn.tool_calls.append({"name": "set_profile", "input": auto["arguments"], "result": auto["result"],
                                    "auto": True})
            turn.text = f"{turn.text}\n\n{confirmation_line(auto['result'])}".strip()
        turn.ungrounded = ungrounded(turn.text, "\n".join(self.corpus))
        turn.events = self.session.events[first_event:]
        turn.rewritten = rewritten if rewritten != text else None
        if channel == "voice":
            turn.spoken = speakable(turn.text)
        return turn

    def profile_safety_net(self, text: str) -> dict | None:
        """Apply a mobility cue from the user's message that the model's turn left unhonoured."""
        found = profile_cues(text)
        if found is None or profile_satisfies(self.session.profile, found["arguments"]):
            return None
        arguments = dict(found["arguments"])
        preset = arguments.get("preset")
        current = self.session.profile.min_door_width_m
        if preset in PRESETS and "min_door_width_m" in PRESETS[preset].get("assumed", []) \
                and current is not None and "min_door_width_m" not in arguments:
            arguments["min_door_width_m"] = current  # keep a width the model already chose
        result = self.session.call("set_profile", arguments)
        if "error" in result:
            return None
        self.corpus.append(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return {"cues": found["cues"], "arguments": arguments, "result": result}

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
