"""core/validate.py: issues for a building dict; pre-existing issues of the base are warnings, new ones errors."""

import copy
import json
from pathlib import Path

import pytest

from core.validate import validate

DATA = Path(__file__).resolve().parent.parent / "data"
DATASET = sorted(path for split in ("train", "dev", "test") for path in (DATA / split).glob("*/building.json"))
FIXTURE = DATA / "train" / "proc-campus-train-000" / "building.json"


@pytest.fixture
def base() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def codes(issues: list[dict], severity: str = "error") -> set[str]:
    return {issue["code"] for issue in issues if issue["severity"] == severity}


def room_with_doors(building: dict) -> dict:
    return next(space for space in building["spaces"] if space["type"] == "room"
                and any(space["id"] in opening["space_ids"] for opening in building["openings"]))


def test_dataset_size():
    assert len(DATASET) == 280


@pytest.mark.parametrize("path", DATASET, ids=lambda path: f"{path.parent.parent.name}/{path.parent.name}")
def test_dataset_has_no_errors_against_itself(path):
    building = json.loads(path.read_text(encoding="utf-8"))
    assert codes(validate(building, base=building)) == set()


@pytest.mark.parametrize("path", [path for path in DATASET if "/proc-" in str(path)][:40],
                         ids=lambda path: path.parent.name)
def test_procedural_buildings_are_clean_without_base(path):
    assert codes(validate(json.loads(path.read_text(encoding="utf-8")))) == set()


def test_clean_fixture_has_no_issues(base):
    assert validate(base) == []


def test_overlap_detected(base):
    changed = copy.deepcopy(base)
    room = room_with_doors(changed)
    other = next(space for space in changed["spaces"]
                 if space["floor_id"] == room["floor_id"] and space["id"] != room["id"] and space["type"] == "room")
    room["polygon"] = copy.deepcopy(other["polygon"])  # drawn right on top of another room
    issues = validate(changed, base=base)
    assert any(issue["code"] == "overlap" and issue["severity"] == "error"
               and set(issue["ids"]) == {room["id"], other["id"]} for issue in issues)


def test_opening_off_wall_detected(base):
    changed = copy.deepcopy(base)
    opening = changed["openings"][0]
    opening["position"] = [opening["position"][0], opening["position"][1] + 3.0]
    issues = validate(changed, base=base)
    assert any(issue["code"] == "opening_off_wall" and opening["id"] in issue["ids"] and issue["severity"] == "error"
               for issue in issues)


def test_unreachable_detected(base):
    changed = copy.deepcopy(base)
    room = room_with_doors(changed)
    changed["openings"] = [opening for opening in changed["openings"] if room["id"] not in opening["space_ids"]]
    issues = validate(changed, base=base)
    assert any(issue["code"] == "unreachable" and issue["ids"] == [room["id"]] for issue in issues)


def test_dangling_ref_detected(base):
    changed = copy.deepcopy(base)
    changed["openings"][0]["space_ids"] = [changed["openings"][0]["space_ids"][0], "no-such-space"]
    assert "dangling_ref" in codes(validate(changed, base=base))


def test_duplicate_id_detected(base):
    changed = copy.deepcopy(base)
    changed["assets"].append(copy.deepcopy(changed["assets"][0]))
    assert "duplicate_id" in codes(validate(changed, base=base))


def test_asset_outside_detected(base):
    changed = copy.deepcopy(base)
    changed["assets"][0]["position"] = [10_000.0, 10_000.0]
    assert "asset_outside" in codes(validate(changed, base=base))


def test_polygon_invalid_detected(base):
    changed = copy.deepcopy(base)
    changed["spaces"][1]["polygon"] = [[0, 0], [4, 4], [4, 0], [0, 4]]
    assert "polygon_invalid" in codes(validate(changed, base=base))


def test_no_entrance_is_a_warning(base):
    changed = copy.deepcopy(base)
    changed["openings"] = [opening for opening in changed["openings"] if "outside" not in opening["space_ids"]]
    issues = validate(changed, base=base)
    assert "no_entrance" in codes(issues, "warning")
    assert "unreachable" not in codes(issues)


def test_pre_existing_issue_is_a_warning(base):
    broken = copy.deepcopy(base)
    broken["openings"][0]["position"] = [broken["openings"][0]["position"][0], broken["openings"][0]["position"][1] + 3]
    assert "opening_off_wall" in codes(validate(broken, base=broken), "warning")
    assert "opening_off_wall" in codes(validate(broken), "error")


def test_issue_shape_and_order(base):
    changed = copy.deepcopy(base)
    changed["openings"] = [opening for opening in changed["openings"] if "outside" not in opening["space_ids"]]
    changed["assets"][0]["position"] = [10_000.0, 10_000.0]
    issues = validate(changed, base=base)
    assert all(set(issue) == {"severity", "code", "message", "ids"} for issue in issues)
    severities = [issue["severity"] for issue in issues]
    assert severities == sorted(severities, key=lambda severity: severity != "error")
