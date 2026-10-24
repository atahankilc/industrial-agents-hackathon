"""agent/builder.py: the Builder's tool loop (propose, never apply), "yes" → apply, grounding, and its offline client."""

import json

import pytest

import backend.app as backend_app
from agent.builder import Builder
from agent.builder_offline import BuilderOfflineClient
from agent.builder_tools import BuilderTools
from agent.offline_llm import message, text_block, tool_use
from backend.drafts import DraftStore
from core.edits import EditError

BASE = "train/proc-campus-train-000"


class ScriptedClient:
    """Returns the given responses in order and records every request."""

    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []
        self.beta = self
        self.messages = self

    def create(self, **request) -> object:
        self.requests.append(json.loads(json.dumps(request["messages"], default=lambda block: block.model_dump()
                                                   if hasattr(block, "model_dump") else str(block))))
        return self.responses.pop(0)


@pytest.fixture
def store(tmp_path) -> DraftStore:
    return DraftStore(tmp_path, dict(backend_app.store.catalogue))


@pytest.fixture
def draft(store):
    return store.create(BASE)


def a_room(store: DraftStore, draft) -> dict:
    return next(space for space in store.building(draft)["spaces"] if space["type"] == "room" and space.get("ref"))


def office_with_side_neighbour(store: DraftStore, draft) -> tuple[dict, str]:
    tools = BuilderTools(store, draft)
    for space in store.building(draft)["spaces"]:
        if space["room_type"] == "office" and len(space["polygon"]) == 4:
            info = tools.call("space_info", {"space": space["id"]})
            sides = [n["side"] for n in info["neighbours"] if n["side"] in ("east", "west") and n["shared_m"] >= 2]
            if sides:
                return space, sides[0]
    raise AssertionError("no office with a side neighbour")


def rename_script(room: dict, then: str = "I'd rename it to Quiet room. Shall I apply it?") -> list:
    return [message(tool_use("space_info", {"space": room["id"]})),
            message(tool_use("propose_edit", {"summary": f"rename {room['name']} to Quiet room",
                                              "ops": [{"op": "set_space", "space_id": room["id"], "name": "Quiet room"}]})),
            message(text_block(then))]


def test_turn_with_proposal_does_not_change_draft(store, draft):
    room = a_room(store, draft)
    builder = Builder(store, draft, client=ScriptedClient(rename_script(room)))
    turn = builder.reply("rename it")
    assert turn.proposal is not None and turn.proposal.ops[0]["op"] == "set_space"
    assert turn.applied is None and draft.steps == []
    assert [call["name"] for call in turn.tool_calls] == ["space_info", "propose_edit"]


def test_yes_applies_single_pending_proposal(store, draft):
    room = a_room(store, draft)
    client = ScriptedClient(rename_script(room))
    builder = Builder(store, draft, client=client)
    turn = builder.reply("rename it")
    requests = len(client.requests)
    yes = builder.reply("yes")
    assert yes.applied == turn.proposal.summary
    assert len(draft.steps) == 1 and len(client.requests) == requests  # no model call for a plain yes
    assert next(s for s in store.building(draft)["spaces"] if s["id"] == room["id"])["name"] == "Quiet room"


def test_yes_without_pending_goes_to_model(store, draft):
    client = ScriptedClient([message(text_block("There's nothing to apply yet — what would you like to change?"))])
    turn = Builder(store, draft, client=client).reply("yes")
    assert turn.applied is None and len(client.requests) == 1


def test_apply_stale_proposal_raises(store, draft):
    room = a_room(store, draft)
    builder = Builder(store, draft, client=ScriptedClient(rename_script(room)))
    turn = builder.reply("rename it")
    store.apply(draft, [{"op": "set_space", "space_id": room["id"], "name": "Changed by hand"}])
    with pytest.raises(EditError, match="changed since"):
        builder.apply(turn.proposal.id)
    assert len(draft.steps) == 1


def test_apply_by_button_tells_the_model_next_turn(store, draft):
    room = a_room(store, draft)
    client = ScriptedClient(rename_script(room) + [message(text_block("Noted."))])
    builder = Builder(store, draft, client=client)
    turn = builder.reply("rename it")
    builder.apply(turn.proposal.id)
    builder.reply("thanks")
    last_user = client.requests[-1][-1]["content"]
    assert "applied" in str(last_user) and turn.proposal.summary in str(last_user)


def test_repeated_bad_proposals_stop(store, draft):
    bad = {"summary": "x", "ops": [{"op": "set_space", "space_id": "nope", "name": "y"}]}
    client = ScriptedClient([message(tool_use("propose_edit", bad)) for _ in range(3)]
                            + [message(text_block("I couldn't make that change."))])
    turn = Builder(store, draft, client=client).reply("do something odd")
    errors = [call["result"].get("error", "") for call in turn.tool_calls]
    assert "stop proposing" in errors[2] and "nope" in errors[0]
    assert turn.proposal is None


def test_new_problems_reach_the_tool_result(store, draft):
    tools = BuilderTools(store, draft)
    room = a_room(store, draft)
    info = tools.call("space_info", {"space": room["id"]})
    ops = [{"op": "delete_opening", "opening_id": opening["id"]} for opening in info["openings"]]
    client = ScriptedClient([message(tool_use("propose_edit", {"summary": "wall it off", "ops": ops})),
                             message(text_block("That would cut the room off. Apply anyway?"))])
    turn = Builder(store, draft, client=client).reply("remove all doors of that room")
    assert any("can't be reached" in problem for problem in turn.tool_calls[0]["result"]["new_problems"])
    assert turn.proposal.new_problems


def test_ungrounded_number_triggers_one_repair(store, draft):
    client = ScriptedClient([message(text_block("The lab is 37.5 m² now.")), message(text_block("I can check that."))])
    turn = Builder(store, draft, client=client).reply("how big is the lab?")
    assert len(client.requests) == 2
    assert str(client.requests[1][-1]["content"]).startswith("[grounding check")
    assert turn.text == "I can check that."


def test_offline_widen_proposes_move_edge(store, draft):
    office, side = office_with_side_neighbour(store, draft)
    builder = Builder(store, draft, client=BuilderOfflineClient())
    turn = builder.reply(f"make {office['ref']} 1 m wider to the {side}")
    assert turn.proposal is not None and turn.proposal.ops[0]["op"] == "move_edge"
    assert turn.proposal.ops[0]["offset_m"] == 1.0
    assert draft.steps == [] and turn.ungrounded == []


def test_offline_rename_and_help(store, draft):
    room = a_room(store, draft)
    builder = Builder(store, draft, client=BuilderOfflineClient())
    turn = builder.reply(f"rename {room['ref']} to Quiet room")
    assert turn.proposal.ops == [{"op": "set_space", "space_id": room["id"], "name": "Quiet room"}]
    assert builder.reply("yes").applied
    help_turn = builder.reply("paint everything blue")
    assert help_turn.proposal is None and "wider" in help_turn.text


def test_offline_add_door_between_neighbours(store, draft):
    office, side = office_with_side_neighbour(store, draft)
    info = BuilderTools(store, draft).call("space_info", {"space": office["id"]})
    other = next(n for n in info["neighbours"] if n["side"] == side)
    other_ref = next(s for s in store.building(draft)["spaces"] if s["id"] == other["id"])["ref"]
    turn = Builder(store, draft, client=BuilderOfflineClient()).reply(
        f"add a door between {office['ref']} and {other_ref}")
    assert turn.proposal is not None
    assert turn.proposal.ops[0]["op"] == "add_opening"
    assert turn.proposal.ops[0]["space_ids"] == [office["id"], other["id"]]


# ---------- final-review fixes: a proposal is only confirmable by the very next message ----------


def test_ok_after_another_turn_does_not_apply(store, draft):
    room = a_room(store, draft)
    builder = Builder(store, draft, client=BuilderOfflineClient())
    assert builder.reply(f"rename {room['ref']} to Quiet room").proposal
    builder.reply("what can you do?")  # the card is gone in the UI
    turn = builder.reply("ok thanks")
    assert turn.applied is None and draft.steps == []


def test_yes_with_more_words_goes_to_the_model(store, draft):
    room = a_room(store, draft)
    client = ScriptedClient(rename_script(room) + [message(text_block("Sure — what name would you like instead?"))])
    builder = Builder(store, draft, client=client)
    builder.reply("rename it")
    turn = builder.reply("yes, but call it Library instead")
    assert turn.applied is None and draft.steps == []
    assert "yes, but call it Library instead" in str(client.requests[-1][-1]["content"])


def test_cancelled_proposal_is_not_applied_by_yes(store, draft):
    room = a_room(store, draft)
    client = ScriptedClient(rename_script(room) + [message(text_block("Nothing is open to apply."))])
    builder = Builder(store, draft, client=client)
    proposal = builder.reply("rename it").proposal
    builder.cancel(proposal.id)
    assert builder.reply("yes").applied is None and draft.steps == []


def test_hand_edit_note_drops_the_open_proposal(store, draft):
    room = a_room(store, draft)
    builder = Builder(store, draft, client=BuilderOfflineClient())
    builder.reply(f"rename {room['ref']} to Quiet room")
    builder.drafted_by_hand("The user moved a door.")
    assert builder.tools.pending == {} and builder.reply("yes").applied is None
