"""Restricted spaces for the app's access mode (archive/hackathon/superpowers/specs/2026-10-25-access-profiles-design.md).

A viewer who may not enter some spaces gets a session on a filtered copy of the building: the restricted spaces,
the openings into them, the assets inside them and their stops on stairs/lifts are removed. Every Guide tool
(routes, search, analytics) then works on what the viewer may see, without per-tool filtering. Never used by the
benchmark; with nothing restricted the copy equals the original."""

import copy


def filter_building(data: dict, restricted: set[str] | frozenset[str]) -> dict:
    """A deep copy of building.json data without the `restricted` space ids and everything that needs them."""
    data = copy.deepcopy(data)
    if not restricted:
        return data
    data["spaces"] = [space for space in data["spaces"] if space["id"] not in restricted]
    data["openings"] = [opening for opening in data["openings"]
                        if not any(space_id in restricted for space_id in opening["space_ids"])]
    data["assets"] = [asset for asset in data["assets"] if asset.get("space_id") not in restricted]
    connectors = []
    for connector in data["vertical_connectors"]:
        stops = [index for index, space_id in enumerate(connector["space_ids"]) if space_id not in restricted]
        if len(stops) < 2:
            continue
        # floor_ids runs parallel to space_ids (all 712 connectors in data/, scan 2026-10-25)
        connector["space_ids"] = [connector["space_ids"][index] for index in stops]
        connector["floor_ids"] = [connector["floor_ids"][index] for index in stops]
        connectors.append(connector)
    data["vertical_connectors"] = connectors
    return data


def restricted_names(data: dict, restricted: set[str] | frozenset[str]) -> set[str]:
    """Lower-case names and refs of the restricted spaces and of the assets inside them: what a viewer might ask
    for by name, so the Guide can say "restricted" instead of "unknown"."""
    names: set[str] = set()
    for space in data["spaces"]:
        if space["id"] in restricted:
            names |= {space["id"].lower(), (space.get("name") or "").lower(), (space.get("ref") or "").lower()}
    for asset in data["assets"]:
        if asset.get("space_id") in restricted:
            names |= {asset["id"].lower(), (asset.get("name") or "").lower()}
    return {name for name in names if len(name) >= 3}


def restricted_polygons(data: dict, restricted: set[str] | frozenset[str]) -> list[dict]:
    """Outlines of the restricted spaces for the plan view (darkened, no name, type or contents)."""
    return [{"id": space["id"], "floor_id": space["floor_id"], "polygon": space["polygon"]}
            for space in data["spaces"] if space["id"] in restricted]
