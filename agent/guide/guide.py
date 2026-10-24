"""The Guide loop: one conversational turn = Claude calling tools until it can answer, then a grounding check.

Claude decides which tools to call and how to phrase the answer; tools (agent/guide/tools.py) supply every fact.
Before a reply leaves the loop, every number in it must appear in some tool result of this conversation (or the
building overview). An ungrounded reply gets one repair request; if it is still ungrounded, a refusal or cut-off
happens, or the tool budget runs out, the reply is replaced by the tools' own code-written summaries.

stop_reason handling: `tool_use` runs the tools; `refusal` / `max_tokens` fall back to summaries (any tool calls
in that response get `is_error` results, so the next turn's history is valid); `pause_turn` re-sends the
conversation unchanged (counts as one round); anything else is a final answer. A tool that raises becomes an
`error` tool result, so every tool_use is answered. Any other exception (API or bug) rolls the conversation, tool
history and session back to the start of the turn and is re-raised, so the Guide stays usable."""

import copy
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from agent.guide.grounding import fallback_text, grounded_tokens, ungrounded
from agent.guide.prompt import overview_text, system_blocks
from agent.guide.tools import TOOLS, Session, run_tool
from agent.llm_parser import FALLBACK_BETA, LlmUsage
from core.building_map import BuildingMap

MODEL = os.environ.get("GUIDE_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("GUIDE_EFFORT", "medium")
MAX_TOKENS = 16000
MAX_TOOL_ROUNDS = 8
NOT_RUN = "Not run: the response was cut off."
REPAIR = "These values are not in any tool result: {bad}. Rewrite using only tool results."


@dataclass
class TurnResult:
    text: str
    asked: bool
    space_ids: list[str]
    asset_ids: list[str]
    connector_ids: list[str]
    routes: list[dict]
    options: list[dict]
    tool_calls: list[dict]
    usage: LlmUsage
    grounded: bool


@dataclass
class TurnState:
    calls: list[dict] = field(default_factory=list)
    results: list[dict] = field(default_factory=list)
    usage: LlmUsage = field(default_factory=LlmUsage)


def add_usage(total: LlmUsage, usage: object) -> None:
    total.input_tokens += usage.input_tokens
    total.output_tokens += usage.output_tokens
    total.cache_read_input_tokens += usage.cache_read_input_tokens or 0
    total.cache_creation_input_tokens += usage.cache_creation_input_tokens or 0


def asks(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return bool(lines) and lines[-1].endswith("?")


class Guide:
    def __init__(self, building_dir: Path, client: anthropic.Anthropic | None = None) -> None:
        self.bmap = BuildingMap.load(Path(building_dir))
        self.client = client or anthropic.Anthropic()
        self.session = Session()
        self.messages: list = []
        self.usage = LlmUsage()
        self.system = system_blocks(self.bmap)
        self.overview = overview_text(self.bmap)
        self.tool_results: list[dict] = []  # every tool result of the conversation: the grounded set for follow-ups

    def turn(self, text: str) -> TurnResult:
        state = TurnState()
        if not text.strip():
            return self.result("", state, grounded=True)
        checkpoint = (len(self.messages), len(self.tool_results), copy.deepcopy(self.session))
        self.messages.append({"role": "user", "content": text})
        try:
            reply, grounded = self.run_loop(state)
            return self.result(reply, state, grounded)
        except Exception:
            del self.messages[checkpoint[0]:], self.tool_results[checkpoint[1]:]
            self.session = checkpoint[2]
            raise

    def run_loop(self, state: TurnState) -> tuple[str, bool]:
        repaired = False
        for _ in range(MAX_TOOL_ROUNDS):
            response = self.request()
            add_usage(state.usage, response.usage)
            add_usage(self.usage, response.usage)
            self.messages.append({"role": "assistant", "content": response.content})
            tool_uses = [block for block in response.content if block.type == "tool_use"]
            if response.stop_reason in ("refusal", "max_tokens"):
                self.close_tool_uses(tool_uses)
                return fallback_text(state.results), False
            if response.stop_reason == "pause_turn":
                continue
            if tool_uses:
                self.messages.append({"role": "user", "content": [self.run(block, state) for block in tool_uses]})
                continue
            reply = "\n".join(block.text for block in response.content if block.type == "text").strip()
            if not reply:
                return fallback_text(state.results), False
            bad = ungrounded(reply, grounded_tokens([*self.tool_results, self.overview]))
            if not bad:
                return reply, True
            if repaired:
                return fallback_text(state.results), False
            self.messages.append({"role": "user", "content": REPAIR.format(bad=", ".join(bad))})
            repaired = True
        return fallback_text(state.results), False

    def request(self):
        return self.client.beta.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=self.system,
            tools=TOOLS,
            messages=self.messages,
            output_config={"effort": EFFORT},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )

    def close_tool_uses(self, tool_uses: list) -> None:
        """Answer tool calls we will not run, so the history stays valid. Append-only: earlier messages (and their
        thinking blocks) must reach the API unchanged."""
        if tool_uses:
            self.messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": block.id, "content": NOT_RUN, "is_error": True}
                for block in tool_uses]})

    def run(self, block, state: TurnState) -> dict:
        try:
            result = run_tool(self.bmap, self.session, block.name, block.input)
            content = json.dumps(result)
        except Exception as error:  # a bug in a tool or the core must not leave this tool_use unanswered
            result = {"status": "error", "summary": f"Could not run {block.name}: {error}"}
            content = json.dumps(result)
        state.calls.append({"name": block.name, "input": block.input, "status": result["status"],
                            "summary": result.get("summary", "")})
        state.results.append(result)
        self.tool_results.append(result)
        return {"type": "tool_result", "tool_use_id": block.id, "content": content,
                "is_error": result["status"] == "error"}

    # ---------- what the turn touched (for the UI) ----------

    def result(self, text: str, state: TurnState, grounded: bool) -> TurnResult:
        ids: dict[str, list[str]] = {"space": [], "asset": [], "connector": []}
        routes, options = [], []
        for call, result in zip(state.calls, state.results, strict=True):
            if result["status"] == "ambiguous":
                options = result["options"]
            if result["status"] != "ok":
                continue
            self.collect(result, ids)
            if call["name"] == "locate":
                self.collect_located(result, ids)
            if call["name"] == "route" and isinstance(result.get("result"), dict):
                routes.append(result["result"])
        return TurnResult(text=text, asked=asks(text), space_ids=ids["space"], asset_ids=ids["asset"],
                          connector_ids=ids["connector"], routes=routes, options=options, tool_calls=state.calls,
                          usage=state.usage, grounded=grounded)

    def add_id(self, value: object, ids: dict[str, list[str]]) -> None:
        if not isinstance(value, str):
            return
        for kind, table in (("space", self.bmap.spaces), ("asset", self.bmap.assets),
                            ("connector", self.bmap.connectors)):
            if value in table and value not in ids[kind]:
                ids[kind].append(value)

    def collect(self, value: object, ids: dict[str, list[str]]) -> None:
        """Ids of `describe`d dicts, route space paths and the lifts/stairs in route element paths."""
        if isinstance(value, dict):
            self.add_id(value.get("id"), ids)
            for key in ("space_path", "element_path"):
                for element in value.get(key) or []:
                    self.add_id(element, ids)
            for item in value.values():
                self.collect(item, ids)
        elif isinstance(value, list):
            for item in value:
                self.collect(item, ids)

    def collect_located(self, result: dict, ids: dict[str, list[str]]) -> None:
        """locate lists asset names per room; map them back to asset ids."""
        for room in result["rooms"]:
            names = set(room["assets"])
            for asset in self.bmap.assets.values():
                if asset["space_id"] == room["id"] and asset["name"] in names:
                    self.add_id(asset["id"], ids)
