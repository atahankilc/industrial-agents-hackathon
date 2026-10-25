"""Parser modes and the LLM slot path, tested offline with a fake Claude client.

The fake client plays a perfect LLM: it answers with the slots that the gold `inputs` imply, using names from
the building. That checks everything after the model (slot mapping, resolution, retry, mode switching) on all
labelled questions without API calls. Live LLM accuracy: scripts/eval_llm_parser.py."""

import json
from types import SimpleNamespace

import pytest

from agent.llm_parser import LlmQuestionParser
from agent.parsing import QuestionUnderstanding
from core.question_parser import ParseError
from tests.test_question_parser import building, labelled_questions


def gold_slots(question: dict, building_map) -> dict:
    inputs = question["inputs"]
    slots = dict.fromkeys(
        ["start", "first", "second", "floor", "room_type", "asset_type", "min_width_m", "item", "closed",
         "direction", "may_use_stairs"]
    )
    slots["kind"] = question["kind"]
    for slot in ("start", "first", "second"):
        if slot in inputs:
            space = building_map.spaces[inputs[slot]]
            slots[slot] = {"name": space["name"], "floor": building_map.floors[space["floor_id"]]["name"]}
    if "floor_id" in inputs:
        slots["floor"] = building_map.floors[inputs["floor_id"]]["name"]
    for key in ("room_type", "asset_type", "direction"):
        slots[key] = inputs.get(key)
    if "min_width" in inputs:
        slots["min_width_m"] = inputs["min_width"]
    if "closed" in inputs:
        slots["closed"] = building_map.connectors[inputs["closed"]]["name"]
    if question["kind"] == "errand":
        slots["may_use_stairs"] = True
    return slots


def response(text: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop_reason, usage=usage)


class FakeClient:
    """Returns the queued replies in order; records how many requests were made."""

    def __init__(self, *replies: SimpleNamespace) -> None:
        self.replies = list(replies)
        self.calls = 0
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **_: object) -> SimpleNamespace:
        self.calls += 1
        return self.replies.pop(0)


def first_question(kind: str) -> tuple:
    return next((directory, q) for directory, q in labelled_questions() if q["kind"] == kind)


def test_llm_slot_path_reproduces_every_labelled_question():
    wrong = []
    for directory, question in labelled_questions():
        building_map = building(directory)
        client = FakeClient(response(json.dumps(gold_slots(question, building_map))))
        parsed = LlmQuestionParser(client).parse(question["question"], building_map)
        expected = question["inputs"]
        candidates = {slot: parsed.alternatives.get(slot, [parsed.params.get(slot)]) for slot in expected}
        if parsed.kind != question["kind"] or any(expected[key] not in candidates[key] for key in expected):
            wrong.append((question["id"], parsed.kind, parsed.params, expected))
    assert not wrong, wrong[:5]


def test_regex_mode_never_calls_the_llm():
    directory, question = first_question("largest_room")
    client = FakeClient()
    parsed = QuestionUnderstanding("regex", LlmQuestionParser(client)).parse(question["question"], building(directory))
    assert parsed.notes["parser"] == "regex" and client.calls == 0


def test_regex_mode_rejects_unknown_wording():
    directory, _ = first_question("largest_room")
    with pytest.raises(ParseError):
        QuestionUnderstanding("regex", LlmQuestionParser(FakeClient())).parse("Biggest kitchen upstairs?", building(directory))


def test_hybrid_falls_back_to_llm_on_unknown_wording():
    directory, question = first_question("largest_room")
    building_map = building(directory)
    client = FakeClient(response(json.dumps(gold_slots(question, building_map))))
    parsed = QuestionUnderstanding("hybrid", LlmQuestionParser(client)).parse("Biggest one up there?", building_map)
    assert parsed.notes["parser"] == "llm" and client.calls == 1
    assert parsed.params["room_type"] == question["inputs"]["room_type"]


def test_llm_mode_uses_llm_even_when_a_template_matches():
    directory, question = first_question("straight_line_3d")
    building_map = building(directory)
    client = FakeClient(response(json.dumps(gold_slots(question, building_map))))
    parsed = QuestionUnderstanding("llm", LlmQuestionParser(client)).parse(question["question"], building_map)
    assert parsed.notes["parser"] == "llm" and parsed.params["first"] == question["inputs"]["first"]


def test_crosscheck_reports_agreement_and_disagreement():
    directory, question = first_question("shared_walls_count")
    building_map = building(directory)
    good = gold_slots(question, building_map)
    agree = QuestionUnderstanding("crosscheck", LlmQuestionParser(FakeClient(response(json.dumps(good)))))
    assert agree.parse(question["question"], building_map).notes["crosscheck"] == "agree"
    other_space = next(s for s in building_map.spaces.values() if s["id"] != question["inputs"]["start"]
                       and s["floor_id"] == building_map.spaces[question["inputs"]["start"]]["floor_id"])
    bad = {**good, "start": {"name": other_space["name"], "floor": good["start"]["floor"]}}
    disagree = QuestionUnderstanding("crosscheck", LlmQuestionParser(FakeClient(response(json.dumps(bad)))))
    result = disagree.parse(question["question"], building_map)
    assert result.notes["parser"] == "regex" and result.notes["crosscheck"].startswith("disagree")


def test_llm_retries_once_after_a_resolution_error():
    directory, question = first_question("shared_walls_count")
    building_map = building(directory)
    good = gold_slots(question, building_map)
    bad = {**good, "start": {"name": "Room that does not exist", "floor": good["start"]["floor"]}}
    client = FakeClient(response(json.dumps(bad)), response(json.dumps(good)))
    parsed = LlmQuestionParser(client).parse(question["question"], building_map)
    assert client.calls == 2 and parsed.params["start"] == question["inputs"]["start"]


@pytest.mark.parametrize("reply", [response("{}", "refusal"), response(json.dumps({"kind": "unsupported"}))])
def test_refusal_or_unsupported_raises(reply):
    directory, question = first_question("largest_room")
    with pytest.raises(ParseError):
        LlmQuestionParser(FakeClient(reply, reply)).parse(question["question"], building(directory))


def warm_up_slots(parsed, building_map) -> dict:
    """The slots a perfect LLM would return for a warm-up question, built from the regex parse."""
    params = parsed.params
    slots = dict.fromkeys(
        ["start", "first", "second", "destination", "stops", "floor", "room_type", "asset_type", "min_width_m",
         "item", "closed", "direction", "may_use_stairs"]
    )
    slots["kind"] = parsed.kind

    def space_slot(space_id: str) -> dict:
        space = building_map.spaces[space_id]
        return {"name": space["name"], "floor": building_map.floors[space["floor_id"]]["name"]}

    stops = params.get("stops")
    for slot in ("start", "destination"):
        if slot in params:
            slots[slot] = space_slot(params[slot])
    if stops:
        slots["stops"] = [space_slot(stop) for stop in stops[1:-1]]
    if "floor_id" in params:
        slots["floor"] = building_map.floors[params["floor_id"]]["name"]
    if "closed" in params:
        slots["closed"] = building_map.connectors[params["closed"]]["name"]
    slots["asset_type"] = params.get("asset_type")
    return slots


def test_llm_slot_path_handles_every_warm_up_kind():
    from core.question_parser import parse_question
    from tests.test_warm_up import warm_up_questions

    seen = set()
    for directory, question in warm_up_questions():
        building_map = building(directory)
        regex = parse_question(question["question"], building_map)
        if question["kind"] in seen or regex.ambiguous:
            continue
        seen.add(question["kind"])
        client = FakeClient(response(json.dumps(warm_up_slots(regex, building_map))))
        parsed = LlmQuestionParser(client).parse(question["question"], building_map)
        assert (parsed.kind, parsed.params) == (regex.kind, regex.params), question["id"]
    assert len(seen) == 6
