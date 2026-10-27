"""Drafts on an imported building (backend/api/drafts.py, plan import Task 8): a private base `import/<id>` that is not
in the catalogue until saved, validated without a base (its own errors stay errors), import notes kept on save."""

import pytest

from backend.api.drafts import IMPORT_PREFIX, DraftStore, FileDraftBackend, MemoryDraftBackend
from backend.api.sessions import load_catalogue
from backend.core.plan_import.assemble import assemble, autofix
from tests.plan_fixtures import labelled_floor


def fixture_building() -> dict:
    return autofix(assemble("imp-test", "Imported test", [labelled_floor()], ["fixture.png"]))


def broken_two_floor_building() -> dict:  # no stairs: the upper floor is unreachable
    return autofix(assemble("imp-test", "Imported test", [labelled_floor(0), labelled_floor(1)], ["fixture.png"]))


@pytest.fixture(params=["file", "memory"])
def store(request, tmp_path) -> DraftStore:
    backend = FileDraftBackend(tmp_path) if request.param == "file" else MemoryDraftBackend()
    return DraftStore(backend, load_catalogue())


def test_import_draft_is_private_and_keeps_its_errors(store):
    draft = store.create_import(broken_two_floor_building())
    assert draft.base.startswith(IMPORT_PREFIX) and draft.base not in store.catalogue
    assert draft.name == "Imported test"
    assert any(i["severity"] == "error" and i["code"] == "unreachable" for i in store.issues(draft))


def test_import_draft_can_be_reloaded_and_edited(store):
    draft = store.create_import(fixture_building())
    again = store.get(draft.id)
    assert again is not None and store.known(draft.base)
    room = next(s for s in store.building(again)["spaces"] if s["type"] == "room")
    store.apply(again, [{"op": "set_space", "space_id": room["id"], "name": "Renamed"}])
    assert any(s["name"] == "Renamed" for s in store.building(again)["spaces"])


def test_saving_an_import_keeps_its_notes(store):
    draft = store.create_import(fixture_building())
    building_id = store.save(draft, "Urban Lab")
    saved = store.base_building(building_id)["building"]
    assert saved["source"] == "imported"
    assert saved["source_ref"]["base"] == draft.base
    assert saved["source_ref"]["import"]["floors"]["0"]["scale_method"] == "doors"


def test_memory_backend_shares_imports_across_stores():  # serverless contract
    shared = MemoryDraftBackend()
    a, b = DraftStore(shared, load_catalogue()), DraftStore(shared, load_catalogue())
    draft = a.create_import(fixture_building())
    other = b.get(draft.id)
    assert other is not None and b.issues(other) == a.issues(draft)


def test_unknown_import_base_is_unknown(store):
    assert not store.known(IMPORT_PREFIX + "0" * 32)
    assert not store.known(IMPORT_PREFIX + "../../etc")
