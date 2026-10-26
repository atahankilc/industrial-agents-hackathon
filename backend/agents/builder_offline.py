"""Offline stand-in for the Builder's model, so prompt edits run without an API key (tests, demos).

Like backend/agents/offline_llm.py it reads the request's messages and answers like a very literal model. It understands
three phrasings — "rename X to Y", "make X N m wider|narrower to the north|east|south|west", "add a door between X
and Y" — looks the places up with space_info, proposes the ops with propose_edit, and composes its reply only from
tool results and the user's words (so it passes the grounding check). Anything else gets a short help text."""

import json
import re

from anthropic.types.beta import BetaMessage

from backend.agents.offline_llm import block_field, message, text_block, tool_use

RENAME = re.compile(r"\brename (?:the )?(?P<target>.+?) (?:to|as) (?P<name>.+?)\s*[.!?]*$", re.IGNORECASE)
RESIZE = re.compile(r"\bmake (?:the )?(?P<target>.+?) (?P<metres>\d+(?:[.,]\d+)?)\s*m(?:etres?|eters?)? "
                    r"(?P<way>wider|narrower|bigger|smaller|larger) (?:to|on|towards) the "
                    r"(?P<side>north|east|south|west)\b", re.IGNORECASE)
DOOR = re.compile(r"\badd (?:a )?door between (?:the )?(?P<a>.+?) and (?:the )?(?P<b>.+?)\s*[.!?]*$", re.IGNORECASE)
GROWING = {"wider", "bigger", "larger"}
NEW_DOOR_WIDTH_M = 0.9

# No digits here: the grounding check would flag example numbers that no tool result contains.
HELP = ("I'm running offline without a language model, so I understand: \"rename <room> to <new name>\", "
        "\"make <room> <N> m wider to the east\" (or narrower; north / east / south / west) and \"add a door "
        "between <room> and <room>\". Then say \"yes\" or press Apply.")


def user_text(messages: list[dict]) -> str:
    """The user's latest words (notes the Builder prepends are separated by a blank line)."""
    for item in reversed(messages):
        if item["role"] == "user" and isinstance(item["content"], str):
            return item["content"].split("\n\n")[-1]
    return ""


class BuilderOfflineClient:
    def __init__(self) -> None:
        self.beta = self
        self.messages = self

    def create(self, **request: object) -> BetaMessage:
        messages: list[dict] = request["messages"]  # type: ignore[assignment]
        last = messages[-1]["content"]
        if isinstance(last, str):
            return self.on_user(last.split("\n\n")[-1] if not last.startswith("[grounding") else last)
        return self.on_results(messages)

    def on_user(self, text: str) -> BetaMessage:
        if text.startswith("[grounding check"):
            return message(text_block("Sorry, I can only repeat what the building tools told me; ask me again."))
        if found := RENAME.search(text):
            return message(tool_use("space_info", {"space": found["target"].strip()}))
        if found := RESIZE.search(text):
            return message(tool_use("space_info", {"space": found["target"].strip()}))
        if found := DOOR.search(text):
            return message(tool_use("space_info", {"space": found["a"].strip()}),
                           tool_use("space_info", {"space": found["b"].strip()}))
        return message(text_block(HELP))

    def on_results(self, messages: list[dict]) -> BetaMessage:
        uses = {block_field(block, "id"): block for block in messages[-2]["content"]
                if block_field(block, "type") == "tool_use"}
        results = [(block_field(uses[item["tool_use_id"]], "name"), json.loads(item["content"]))
                   for item in messages[-1]["content"]]
        errors = [result["error"] for _, result in results if "error" in result]
        if errors:
            return message(text_block(f"I couldn't do that: {errors[0]}"))
        if results[0][0] == "propose_edit":
            return message(text_block(self.describe(results[0][1])))
        infos = [result for name, result in results if name == "space_info"]
        return self.propose(user_text(messages), infos)

    def propose(self, text: str, infos: list[dict]) -> BetaMessage:
        info = infos[0]
        if found := RENAME.search(text):
            name = found["name"].strip()
            return message(tool_use("propose_edit", {
                "summary": f"rename {info['name']} to {name}",
                "ops": [{"op": "set_space", "space_id": info["id"], "name": name}]}))
        if found := RESIZE.search(text):
            side, way, metres = found["side"].lower(), found["way"].lower(), found["metres"].replace(",", ".")
            edge = next((edge for edge in info["edges"] if edge["side"] == side), None)
            if edge is None:
                return message(text_block(f"{info['name']} has no wall facing {side}; which wall do you mean?"))
            offset = float(metres) if way in GROWING else -float(metres)
            return message(tool_use("propose_edit", {
                "summary": f"make {info['name']} {metres} m {way} to the {side}",
                "ops": [{"op": "move_edge", "space_id": info["id"], "edge": [edge["from"], edge["to"]],
                         "offset_m": offset}]}))
        if DOOR.search(text) and len(infos) == 2:
            first, second = infos
            neighbour = next((item for item in first["neighbours"] if item["id"] == second["id"]), None)
            if neighbour is None:
                return message(text_block(f"{first['name']} and {second['name']} share no wall, so a door can't "
                                          "join them."))
            edge = next(edge for edge in first["edges"] if edge["side"] == neighbour["side"])
            middle = [(edge["from"][0] + edge["to"][0]) / 2, (edge["from"][1] + edge["to"][1]) / 2]
            return message(tool_use("propose_edit", {
                "summary": f"add a door between {first['name']} and {second['name']}",
                "ops": [{"op": "add_opening", "space_ids": [first["id"], second["id"]], "position": middle,
                         "kind": "door", "width_m": NEW_DOOR_WIDTH_M, "step_free": True}]}))
        return message(text_block(HELP))

    @staticmethod
    def describe(result: dict) -> str:
        parts = [f"I'd {result['summary']}."]
        areas = [f"{item['name']} {item['area_before']} → {item['area_after']} m²"
                 for item in result["effect"]["changed_spaces"]]
        if areas:
            parts.append("Areas: " + "; ".join(areas) + ".")
        if result["new_problems"]:
            parts.append("It would add problems: " + " ".join(result["new_problems"]))
        parts.append("Apply it?")
        return " ".join(parts)
