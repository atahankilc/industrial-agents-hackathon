"""Routing-profile presets (set_profile) and the Guide's deterministic cue safety net, offline.

Presets come from the "Profiles per persona" table in docs/product/routing-profiles.md; the safety net applies a
mobility cue the model's turn left unhonoured (docs/product/routing-profiles.md#todo-preference-extraction)."""

import pytest

from agent.guide import profile_cues
from agent.offline_llm import message, text_block
from agent.tools import BuildingSession, RoutingProfile
from tests.test_guide import BUILDING, LIFT_1, call, give_directions, run, say

ROUTE = {"start": "Main lobby", "destination": "Meeting room 3.07"}
WHEELCHAIR_SUMMARY = "step-free, doors at least 0.8 m wide (assumed)"


@pytest.fixture
def session() -> BuildingSession:
    return BuildingSession.load(BUILDING)


# ---------- presets ----------


def test_wheelchair_preset_sets_step_free_and_assumed_width(session):
    result = session.call("set_profile", {"preset": "wheelchair"})
    assert session.profile.step_free and session.profile.min_door_width_m == 0.8
    assert result["assumed"] == ["min_door_width_m"] and result["preset"] == "wheelchair"
    assert result["changed"] == {"step_free": True, "min_door_width_m": 0.8}
    assert result["summary"] == WHEELCHAIR_SUMMARY
    route = session.call("find_route", ROUTE)
    assert route["step_free"] and route["profile"] == WHEELCHAIR_SUMMARY


def test_explicit_field_overrides_preset_and_is_not_assumed(session):
    result = session.call("set_profile", {"preset": "wheelchair", "min_door_width_m": 0.9})
    assert session.profile.min_door_width_m == 0.9 and result["assumed"] == []
    assert result["summary"] == "step-free, doors at least 0.9 m wide"
    session.call("set_profile", {"preset": "wheelchair"})  # again: the preset's assumed value comes back
    session.call("set_profile", {"min_door_width_m": 0.7})  # P26: "my chair is narrow, 0.7 m"
    assert session.profile.min_door_width_m == 0.7 and session.profile.assumed == []


def test_presets_change_only_their_fields_and_default_resets(session):
    session.call("set_profile", {"preset": "no_lifts"})
    session.call("set_profile", {"preset": "wheelchair"})
    assert session.profile.avoid_lifts and session.profile.step_free  # composed, not replaced
    result = session.call("set_profile", {"preset": "default"})  # P26: "I'm out of the cast now"
    assert session.profile == RoutingProfile() and result["summary"] == "stairs allowed"
    assert result["changed"] == {"step_free": False, "min_door_width_m": None, "avoid_lifts": False}


def test_trolley_preset_asks_for_the_width(session):
    result = session.call("set_profile", {"preset": "trolley"})
    assert session.profile.step_free and session.profile.min_door_width_m is None
    assert result["needs"] == ["min_door_width_m"]
    result = session.call("set_profile", {"preset": "trolley", "min_door_width_m": 1.1})
    assert "needs" not in result and session.profile.min_door_width_m == 1.1


def test_bad_preset_and_width_are_errors(session):
    assert "Unknown preset" in session.call("set_profile", {"preset": "hovercraft"})["error"]
    assert "error" in session.call("set_profile", {"min_door_width_m": -1})
    assert session.profile == RoutingProfile()


# ---------- cue detector ----------


@pytest.mark.parametrize("text, arguments", [
    ("I use a wheelchair.", {"preset": "wheelchair"}),
    ("Where's the nearest toilet for my mother? She uses a wheelchair.", {"preset": "wheelchair"}),  # P19
    ("I'm a wheelchair user", {"preset": "wheelchair"}),
    ("Ich sitze im Rollstuhl", {"preset": "wheelchair"}),
    ("I'm here with a pram", {"preset": "pram"}),
    ("My trolley is 80 cm wide", {"preset": "trolley", "min_door_width_m": 0.8}),
    ("I'm pushing a pallet 1.2 m wide to the lab.", {"preset": "trolley", "min_door_width_m": 1.2}),
    ("Actually my chair is narrow, 0.7 m.", {"min_door_width_m": 0.7}),
    ("I can't use stairs", {"step_free": True}),
    ("I have a mobility scooter", {"step_free": True}),
    ("I won't take lifts", {"preset": "no_lifts"}),
    ("I'm claustrophobic", {"preset": "no_lifts"}),
    ("I'm in a wheelchair and I won't take lifts", {"preset": "wheelchair", "avoid_lifts": True}),
    ("I'm in a wheelchair, the lobby is 2 m away", {"preset": "wheelchair"}),  # a distance, not a width
    ("I'm out of the cast now.", {"preset": "default"}),
    ("I'm not in the chair anymore", {"preset": "default"}),
])
def test_cues(text, arguments):
    assert profile_cues(text)["arguments"] == arguments


@pytest.mark.parametrize("text", [
    "Where is the wheelchair-accessible toilet?",  # a facility, not the user's constraint
    "Is there a wheelchair toilet on floor 2?",
    "Take the wheelchair lift to level 3",
    "A wheelchair user complained about door 3",  # third party, not the guided person
    "rollstuhlgerechte Toilette",
    "I don't use a wheelchair",
    "I'm not claustrophobic",
    "I can't take the lift, it's broken",  # a closure, handled by propose_change
    "Is there a pram room?",
    "Where is the coffee cart?",
    "How many rooms are step-free reachable if Lift 1 is closed?",  # analytics, not a constraint
])
def test_no_cue(text):
    assert profile_cues(text) is None


# ---------- safety net in the Guide loop ----------


def test_safety_net_applies_an_ignored_wheelchair_cue_and_redoes_the_route(session):
    guide, client = run(session, [
        call(("find_route", ROUTE)),
        give_directions,  # the model ignored "I use a wheelchair": a route with stairs allowed
        call(("find_route", ROUTE)),  # after the Guide's profile check
        give_directions,
        call(("find_route", ROUTE)),
        give_directions,
    ])
    turn = guide.reply("I use a wheelchair. How do I get from the main lobby to meeting room 3.07?")
    assert "[profile check" in client.requests[2]["messages"][-1]["content"]
    assert turn.auto_profile["arguments"] == {"preset": "wheelchair"}
    assert turn.auto_profile["cues"] == ["wheelchair"]
    assert turn.tool_calls[-1]["name"] == "set_profile" and turn.tool_calls[-1]["auto"] is True
    first, redone = (call_["result"] for call_ in turn.tool_calls if call_["name"] == "find_route")
    assert not first["step_free"] and first["length_m"] == 57.68
    assert redone["step_free"] and redone["length_m"] == 61.24 and LIFT_1 in redone["element_path"]
    assert "about 61 m" in turn.text and "about 58 m" not in turn.text  # step-free 61.24 m, not 57.68 m
    assert turn.text.endswith(f"(Noted: {WHEELCHAIR_SUMMARY}. I'll use that for every route. Tell me if your "
                              "doors need to be wider or can be narrower.)")
    assert turn.ungrounded == []

    later = guide.reply("And again from the main lobby to meeting room 3.07?")
    assert later.auto_profile is None
    assert later.tool_calls[0]["result"]["step_free"] and later.tool_calls[0]["result"]["profile"] == \
        WHEELCHAIR_SUMMARY
    assert not client.steps


def test_safety_net_without_a_route_leaves_a_note_for_the_next_turn(session):
    guide, client = run(session, [say("Okay."), call(("find_route", ROUTE)), give_directions])
    turn = guide.reply("I'm claustrophobic, so no lifts for me.")
    assert len(client.requests) == 1  # no route this turn: no extra model round
    assert session.profile.avoid_lifts and turn.auto_profile["arguments"] == {"preset": "no_lifts"}
    assert turn.text == "Okay.\n\n(Noted: stairs allowed, no lifts. I'll use that for every route.)"
    later = guide.reply("From the main lobby to meeting room 3.07?")
    sent = client.requests[1]["messages"][-1]["content"]
    assert sent.startswith("[profile note, not from the user]") and sent.endswith(
        "From the main lobby to meeting room 3.07?")
    route = later.tool_calls[0]["result"]
    assert route["reachable"] and not any("-V02" in element or "-V04" in element for element in
                                          route["element_path"])  # no lift on the way
    assert later.ungrounded == []


def test_no_duplicate_when_the_model_set_the_profile(session):
    guide, client = run(session, [call(("set_profile", {"step_free": True, "min_door_width_m": 0.9})),
                                  say("Step-free, doors at least 0.9 m wide.")])
    turn = guide.reply("I use a wheelchair, quite a wide one.")
    assert turn.auto_profile is None and [c["name"] for c in turn.tool_calls] == ["set_profile"]
    assert session.profile.min_door_width_m == 0.9 and len(client.requests) == 2


def test_partial_model_profile_is_completed_without_overwriting(session):
    guide, _ = run(session, [call(("set_profile", {"step_free": True, "avoid_lifts": False})), say("Step-free.")])
    turn = guide.reply("I use a wheelchair.")
    assert turn.auto_profile["result"]["changed"] == {"min_door_width_m": 0.8}
    assert session.profile.step_free and session.profile.min_door_width_m == 0.8
    assert turn.ungrounded == []


def test_facility_question_sets_no_profile(session):
    guide, _ = run(session, [call(("search", {"query": "toilet"})), say("There are several toilets.")])
    turn = guide.reply("Where is the wheelchair-accessible toilet?")
    assert turn.auto_profile is None and session.profile == RoutingProfile()
    assert "Noted" not in turn.text


def test_reset_cue_clears_the_profile(session):
    session.call("set_profile", {"preset": "wheelchair"})
    guide, _ = run(session, [say("Good to hear!")])
    turn = guide.reply("I'm out of the cast now.")
    assert session.profile == RoutingProfile() and turn.auto_profile["arguments"] == {"preset": "default"}
    assert turn.text.endswith("(Noted: no mobility constraints any more; routes may use stairs and lifts again.)")
    assert turn.ungrounded == []


def test_reset_cue_with_default_profile_does_nothing(session):
    guide, _ = run(session, [lambda request: message(text_block("Great."))])
    assert guide.reply("I'm out of the cast now.").auto_profile is None


def test_trolley_width_from_the_user_is_applied(session):
    guide, _ = run(session, [say("Sure, where to?")])
    turn = guide.reply("I'm pushing a trolley, it's 80 cm wide.")
    assert session.profile.step_free and session.profile.min_door_width_m == 0.8
    assert session.profile.assumed == [] and turn.ungrounded == []
    assert "doors at least 0.8 m wide." in turn.text and "assumed" not in turn.text

