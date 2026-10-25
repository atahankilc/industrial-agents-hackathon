"""Offline stand-in for the Anthropic client, so the Guide and the backend run without an API key.

`OfflineClient().beta.messages.create(**request)` reads the request's messages and answers like a very literal
model: keyword rules pick tools for a new user message, and the reply text is composed only from tool results,
so it passes the Guide's grounding check. It is a demo and test fixture, not a language model: anything outside
the rules gets a short help text. The response helpers (`text_block`, `tool_use`, `message`) build real SDK
types and are shared with the scripted fakes in tests/."""

import itertools
import json
import re
from types import SimpleNamespace

from anthropic.types.beta import BetaMessage, BetaTextBlock, BetaToolUseBlock, BetaUsage

MODEL = "offline-rules"
MAX_OPTIONS = 3
_ids = itertools.count(1)

CONFIRM = re.compile(r"^\s*(yes|yep|yeah|ok|okay|sure|confirm|do it|apply|go ahead|please do)\b", re.IGNORECASE)
STEP_FREE = re.compile(r"wheelchair|step[- ]free|can'?t (use|take|climb) (the )?stairs|no stairs|pram|walker",
                       re.IGNORECASE)
WHEELCHAIR = re.compile(r"\b(?:use|in|on) (?:a |my )?wheelchair\b", re.IGNORECASE)
BROKEN = re.compile(r"(?:the )?(?P<target>[\w .-]+?) (?:is|are) (?:broken|closed|out of order|out of service|"
                    r"blocked|not working)", re.IGNORECASE)
ROUTE = re.compile(r"from (?:the )?(?P<start>.+?) to (?:the )?(?P<destination>.+?)\s*[?.!]*$", re.IGNORECASE)
GO_TO = re.compile(r"(?:get|go|walk|way|directions|route|take me|bring me) to (?:the )?(?P<destination>.+?)\s*[?.!]*$", re.IGNORECASE)
WHERE = re.compile(r"(?:where (?:is|are|can i find)|find|locate) (?:the |a |an |my )?(?P<query>.+?)\s*[?.!]*$",
                   re.IGNORECASE)
I_AM_IN = re.compile(r"\bi(?:'?m| am) (?:now )?(?:in|at) (?:the )?(?P<place>.+?)"
                     r"(?=\s*(?:[,!?]|\.(?!\d)|$| and | so ))", re.IGNORECASE)  # "3.07" is no full stop
CANDIDATES = re.compile(r"[\w-]+ \(([^)]+)\)")

EDIT = re.compile(r"\b(edit|rename|redesign|re-?purpose|move (?:the |a )?wall|resize|make .+ (?:wider|bigger|smaller)|"
                  r"(?:add|put|place|remove|delete) (?:a |an |the )?(?:desk|chair|shelf|plant|item))",
                  re.IGNORECASE)
HELP = ("I'm running offline without a language model, so I understand simple phrasings: \"where is the "
        "printer\", \"from Main lobby to Meeting room 3.07\", \"I use a wheelchair\", \"Lift 1 is broken\", then "
        "\"yes\" to apply a change.")


def text_block(text: str) -> BetaTextBlock:
    return BetaTextBlock(type="text", text=text, citations=None)


def tool_use(name: str, arguments: dict) -> BetaToolUseBlock:
    return BetaToolUseBlock(type="tool_use", id=f"toolu_offline_{next(_ids)}", name=name, input=arguments)


def message(*blocks: object, stop_reason: str | None = None) -> BetaMessage:
    stop = stop_reason or ("tool_use" if any(block.type == "tool_use" for block in blocks) else "end_turn")
    return BetaMessage.model_construct(
        id=f"msg_offline_{next(_ids)}", type="message", role="assistant", model=MODEL, content=list(blocks),
        stop_reason=stop, stop_sequence=None, usage=BetaUsage(input_tokens=0, output_tokens=0),
    )


def block_field(block: object, name: str) -> object:
    return block.get(name) if isinstance(block, dict) else getattr(block, name, None)


class OfflineClient:
    def __init__(self) -> None:
        self.beta = SimpleNamespace(messages=self)
        self.messages = self

    def create(self, **request: object) -> BetaMessage:
        # Operator system messages (e.g. the voice style) are not user input: answer the turn before them.
        everything: list[dict] = request["messages"]  # type: ignore[assignment]
        messages = [item for item in everything if item["role"] != "system"]
        last = messages[-1]["content"]
        if isinstance(last, str):
            return self.on_user(last, messages)
        if any(block_field(block, "type") == "image" for block in last):  # a photo turn: answer its text
            text = " ".join(block_field(block, "text") for block in last if block_field(block, "type") == "text")
            return self.on_user(text.split("\n\n", 1)[-1], messages)
        return self.on_results(messages)

    # ---------- a new user message → tools ----------

    def on_user(self, text: str, messages: list[dict]) -> BetaMessage:
        if text.startswith("[grounding check"):
            return message(text_block("Sorry, I can only repeat what the building tools told me; ask me again."))
        if text.startswith("[profile check"):  # the Guide's safety net changed the profile: redo the route
            route = self.last_route(messages)
            return message(tool_use("find_route", route)) if route else message(text_block("Noted."))
        if text.startswith("[profile note"):
            text = text.partition("\n\n")[2]
        uses = []
        pending = self.pending_change(messages)
        if CONFIRM.match(text) and pending:
            return message(tool_use("apply_change", {"change_id": pending}))
        if WHEELCHAIR.search(text):
            uses.append(tool_use("set_profile", {"preset": "wheelchair"}))
        elif STEP_FREE.search(text):
            uses.append(tool_use("set_profile", {"step_free": True}))
        if broken := BROKEN.search(text):
            uses.append(tool_use("propose_change", {"action": "close", "targets": [broken["target"].strip()]}))
        elif EDIT.search(text):
            uses.append(tool_use("open_edit_mode", {"request": text.strip()}))
        elif route := ROUTE.search(text):
            uses.append(tool_use("find_route", {"start": route["start"], "destination": route["destination"]}))
        elif here := I_AM_IN.search(text):
            uses.append(tool_use("set_my_location", {"place": here["place"].strip()}))
            if go := GO_TO.search(text):
                uses.append(tool_use("find_route", {"start": "here", "destination": go["destination"]}))
        elif (go := GO_TO.search(text)) and (start := self.start_place(text, messages)):
            uses.append(tool_use("find_route", {"start": start, "destination": go["destination"]}))
        elif where := WHERE.search(text):
            uses.append(tool_use("locate", {"query": where["query"]}))
        return message(*uses) if uses else message(text_block(HELP))

    # ---------- tool results → text (or a follow-up tool round) ----------

    def on_results(self, messages: list[dict]) -> BetaMessage:
        uses = {block_field(block, "id"): block for block in messages[-2]["content"]
                if block_field(block, "type") == "tool_use"}
        results = [(uses[item["tool_use_id"]], json.loads(item["content"])) for item in messages[-1]["content"]]
        if any(block_field(use, "name") == "apply_change" and "error" not in result for use, result in results):
            change = next(r for u, r in results if block_field(u, "name") == "apply_change")
            route = self.last_route(messages)
            if route:
                return message(text_block(f"Done: {change['applied']}. Checking your route again."),
                               tool_use("find_route", route),
                               tool_use("compare_routes", {"change_id": self.applied_id(messages)}))
            return message(text_block(f"Done: {change['applied']}."))
        lines = [self.describe(block_field(use, "name"), result) for use, result in results]
        return message(text_block("\n".join(line for line in lines if line)))

    def describe(self, name: str, result: dict) -> str:
        if "error" in result:
            options = CANDIDATES.findall(result["error"])
            if options:
                shown = options[:MAX_OPTIONS]
                more = f" (or one of {len(options) - len(shown)} more)" if len(options) > len(shown) else ""
                return f"Which one do you mean: {', '.join(shown)}{more}?"
            return f"I couldn't do that: {result['error']}"
        if name == "set_profile":
            return f"Noted: {result['summary']}. I'll use that for every route from now on."
        if name == "find_route":
            if not result.get("reachable"):
                return f"There's no route right now ({result.get('reason')})."
            steps = result["steps"]
            numbered = "\n".join(f"{index}. {step}" for index, step in enumerate(steps[1:], 1))
            return f"{steps[0]} About {result.get('about_m', round(result['length_m']))} m, {result['profile']}:\n{numbered}"
        if name == "propose_change":
            effect = result.get("effect", {})
            line = f"I understood: {result['summary']}."
            if effect.get("before_m") is not None:
                after = (f"{round(effect['after_m'])} m" if effect.get("still_reachable")
                         else "no longer reachable")
                line += f" Your route {effect['last_route']}: {round(effect['before_m'])} m → {after}."
            return line + " Shall I apply it?"
        if name == "set_my_location":
            return f"Got it, you're in {result['location']['name']} on the {result['location']['floor']}."
        if name == "open_edit_mode":
            return "Switching to the Edit mode — the Builder takes it from here, on a copy of the building."
        if name == "compare_routes":
            line = f"{result['longer_routes_count']} routes from {result['from']} got longer"
            if result["longer_routes_count"]:
                line += f" (up to {result['max_extra_m']} m)"
            return line + f"; {result['lost_access_count']} rooms lost access."
        if name == "locate":
            hits = result.get("assets") or []
            if not hits:
                return f"I couldn't find '{result.get('query')}'."
            if len(hits) == 1:
                return f"{hits[0]['name']} is in {hits[0]['space_name']}."
            shown = ", ".join(f"{hit['space_name']}" for hit in hits[:MAX_OPTIONS])
            listed = "including " if result["total"] > MAX_OPTIONS else ""
            return f"There are {result['total']}, {listed}{shown}. Which one, or where are you now?"
        return json.dumps(result, ensure_ascii=False)[:400]

    # ---------- what the history already says ----------

    def start_place(self, text: str, messages: list[dict]) -> str | None:
        """Where a "take me to …" starts: "here" once the user's position is known, else the last route's start."""
        if "[location note, from the app] The user is in" in text or any(
                name == "set_my_location" and "error" not in result for name, _, result in self.tool_history(messages)):
            return "here"
        return self.last_route(messages, "start")

    @staticmethod
    def tool_history(messages: list[dict]) -> list[tuple[str, dict, dict]]:
        """(name, input, result) for every tool call so far, oldest first."""
        uses, history = {}, []
        for item in messages:
            if isinstance(item["content"], str):
                continue
            for block in item["content"]:
                kind = block_field(block, "type")
                if kind == "tool_use":
                    uses[block_field(block, "id")] = block
                elif kind == "tool_result":
                    use = uses[block["tool_use_id"]]
                    history.append((block_field(use, "name"), dict(block_field(use, "input")),
                                    json.loads(block["content"])))
        return history

    def last_route(self, messages: list[dict], key: str | None = None) -> object:
        routes = [arguments for name, arguments, result in self.tool_history(messages)
                  if name == "find_route" and result.get("reachable")]
        if not routes:
            return None
        return routes[-1][key] if key else routes[-1]

    def pending_change(self, messages: list[dict]) -> str | None:
        history = self.tool_history(messages)
        proposed = [result["change_id"] for name, _, result in history if name == "propose_change"
                    and "change_id" in result]
        applied = {arguments["change_id"] for name, arguments, result in history if name == "apply_change"
                   and "error" not in result}
        open_ids = [change for change in proposed if change not in applied]
        return open_ids[-1] if open_ids else None

    def applied_id(self, messages: list[dict]) -> str:
        return [arguments["change_id"] for name, arguments, result in self.tool_history(messages)
                if name == "apply_change" and "error" not in result][-1]
