"""The user's routing profile (step-free, door width, no lifts, forklift — docs/product/routing-profiles.md), its
persona presets and the app's route preferences, and the Guide tools that set them."""

import copy
from dataclasses import asdict, dataclass, field


from backend.core.preferences import Penalties
from backend.core.route_models import FORKLIFT_MIN_WIDTH_M


# Persona presets for set_profile, from the "Profiles per persona" table in docs/product/routing-profiles.md.
# Only presets the graph can honour today (hard filters: step-free, minimum door width, no lifts). "assumed" lists
# values the user did not give, so the Guide can say "I assumed 0.8 m; tell me if yours is wider". "needs" lists
# values that have no default and must be asked (trolley width). `avoid_stairs` is not a separate field: every
# stairs connector in the data is step_free: false, so step_free routing already excludes stairs.
PRESETS: dict[str, dict] = {
    "default": {"values": {"step_free": False, "min_door_width_m": None, "avoid_lifts": False}},
    "wheelchair": {"values": {"step_free": True, "min_door_width_m": 0.8}, "assumed": ["min_door_width_m"]},
    "pram": {"values": {"step_free": True, "min_door_width_m": 0.8}, "assumed": ["min_door_width_m"]},
    "trolley": {"values": {"step_free": True}, "needs": ["min_door_width_m"]},
    "no_lifts": {"values": {"avoid_lifts": True}},
    # Organiser rule (Q-014): forklift aisles and openings >= 3 m only, pedestrian walkways don't count.
    "forklift": {"values": {"step_free": True, "min_door_width_m": FORKLIFT_MIN_WIDTH_M, "forklift": True}},
}
PROFILE_FIELDS = ("step_free", "min_door_width_m", "avoid_lifts", "forklift")
# Route preferences (app access mode only, archive/hackathon/superpowers/specs/2026-10-25-access-profiles-design.md): soft
# penalties in metres-equivalent from the persona table in docs/product/routing-profiles.md, and avoided room types.
PREFERENCE_FIELDS = ("avoid_room_types", "prefer_lifts", "fewer_doors", "quiet", "avoid_halls", "simple_routes")
PENALTIES_M = {  # field → Penalties values; several preferences combine by the larger value
    "prefer_lifts": {"stairs_per_flight_m": 20.0},  # low_stamina: stairs 20 m/floor
    "fewer_doors": {"door_m": 3.0},  # crutches: door 3 m
    "quiet": {"noisy_m": 40.0, "hall_m": 10.0},  # quiet: noisy 40 m, hall 10 m
    "avoid_halls": {"hall_m": 30.0},  # low_vision: hall 30 m
    "simple_routes": {"space_change_m": 3.0},  # simple: space change 3 m
}
GUIDE_PREFERENCES = ("language", "reply_style", "voice")  # how the Guide talks; no effect on routes


@dataclass
class RoutingProfile:
    step_free: bool = False
    min_door_width_m: float | None = None
    avoid_lifts: bool = False
    forklift: bool = False  # no stairs, openings >= 3 m, no walkway-like spaces (route_models.RouteRules)
    preset: str = "default"  # the last preset applied; explicit fields may refine it
    assumed: list[str] = field(default_factory=list)  # fields set from a preset default, not from the user
    avoid_room_types: list[str] = field(default_factory=list)  # PREFERENCE_FIELDS: app preferences only
    prefer_lifts: bool = False
    fewer_doors: bool = False
    quiet: bool = False
    avoid_halls: bool = False
    simple_routes: bool = False

    def penalties(self) -> Penalties | None:
        values: dict[str, float] = {}
        for name, spec in PENALTIES_M.items():
            if getattr(self, name):
                for key, metres in spec.items():
                    values[key] = max(values.get(key, 0.0), metres)
        penalties = Penalties(**values, avoid_room_types=frozenset(self.avoid_room_types))
        return penalties if penalties.active() else None

    def describe(self) -> str:
        parts = ["step-free" if self.step_free else "stairs allowed"]
        if self.min_door_width_m:
            assumed = " (assumed)" if "min_door_width_m" in self.assumed else ""
            parts.append(f"doors at least {self.min_door_width_m} m wide{assumed}")
        if self.avoid_lifts:
            parts.append("no lifts")
        if self.forklift:
            parts.append("forklift (no stairs, no walkways)")
        if self.avoid_room_types:
            parts.append("avoiding " + ", ".join(room.replace("_", " ") for room in self.avoid_room_types))
        labels = {"prefer_lifts": "prefers lifts", "fewer_doors": "fewer doors", "quiet": "quiet route",
                  "avoid_halls": "avoids open halls", "simple_routes": "simple routes"}
        parts += [label for name, label in labels.items() if getattr(self, name)]
        return ", ".join(parts)


class ProfileTools:
    def tool_set_profile(
        self, preset: str | None = None, step_free: bool | None = None, min_door_width_m: float | None = None,
        avoid_lifts: bool | None = None, forklift: bool | None = None, avoid_room_types: list[str] | None = None,
        prefer_lifts: bool | None = None, fewer_doors: bool | None = None, quiet: bool | None = None,
        avoid_halls: bool | None = None, simple_routes: bool | None = None, scope: str | None = None,
    ) -> dict:
        """Apply a persona preset (its fields only; others are kept), then explicit fields, which override it.
        preset "default" resets everything. The result says what changed and which values are assumed."""
        if preset is not None and preset not in PRESETS:
            raise ValueError(f"Unknown preset '{preset}'; use one of {', '.join(PRESETS)}")
        if min_door_width_m is not None and min_door_width_m < 0:
            raise ValueError("min_door_width_m must be ≥ 0 (0 clears it)")
        fields = PROFILE_FIELDS + PREFERENCE_FIELDS
        before = {name: copy.copy(getattr(self.profile, name)) for name in fields}
        needs: list[str] = []
        if preset == "default":
            self.profile = RoutingProfile()
        elif preset is not None:
            spec = PRESETS[preset]
            for name, value in spec["values"].items():
                setattr(self.profile, name, value)
                if name in self.profile.assumed:
                    self.profile.assumed.remove(name)
            self.profile.assumed += [name for name in spec.get("assumed", []) if name not in self.profile.assumed]
            self.profile.preset = preset
            needs = [name for name in spec.get("needs", []) if min_door_width_m is None]
        explicit = {"step_free": step_free, "min_door_width_m": min_door_width_m, "avoid_lifts": avoid_lifts,
                    "forklift": forklift}
        if preset == "default":  # clears mobility constraints only; route preferences are changed by name
            for name in PREFERENCE_FIELDS:
                setattr(self.profile, name, before[name])
        explicit.update({"avoid_room_types": avoid_room_types, "prefer_lifts": prefer_lifts,
                         "fewer_doors": fewer_doors, "quiet": quiet, "avoid_halls": avoid_halls,
                         "simple_routes": simple_routes})
        if avoid_room_types is not None:
            explicit["avoid_room_types"] = sorted({str(room).strip().lower().replace(" ", "_")
                                                   for room in avoid_room_types if str(room).strip()})
        for name, value in explicit.items():
            if value is None:
                continue
            setattr(self.profile, name, (value or None) if name == "min_door_width_m" else value)
            if name in self.profile.assumed:
                self.profile.assumed.remove(name)
        changed = {name: getattr(self.profile, name) for name in fields
                   if getattr(self.profile, name) != before[name]}
        result = {"profile": asdict(self.profile), "summary": self.profile.describe(), "changed": changed,
                  "assumed": list(self.profile.assumed)}
        if preset is not None:
            result["preset"] = preset
        if needs:
            result["needs"] = needs  # ask the user, e.g. how wide the trolley is
        self.remember_preference(changed, scope, result)
        return result

    def remember_preference(self, changed: dict, scope: str | None, result: dict) -> None:
        """Access mode: tell the app to store what changed (global, or for this building only)."""
        if not (self.preferences_enabled and self.auto_capture and changed):
            return
        scope = "building" if scope == "building" else "global"
        self.events.append({"type": "preference", "scope": scope, "values": changed})
        result["remembered"] = scope

    def tool_set_preference(self, language: str | None = None, reply_style: str | None = None,
                            voice: bool | None = None, favourite: str | None = None,
                            scope: str | None = None) -> dict:
        """How the Guide talks to this user, and saved places (favourites are always per building)."""
        if not self.preferences_enabled:
            return {"error": "Preferences are not available here."}
        if reply_style is not None and reply_style not in ("brief", "detailed"):
            raise ValueError("reply_style must be 'brief' or 'detailed'")
        changed = {name: value for name, value in
                   {"language": language, "reply_style": reply_style, "voice": voice}.items()
                   if value is not None and self.guide_preferences.get(name) != value}
        self.guide_preferences.update(changed)
        result: dict = {"preferences": dict(self.guide_preferences), "changed": changed}
        if favourite is not None:
            space_id = self.resolve(favourite)
            result["favourite"] = self.space_summary(space_id)
            if self.auto_capture:
                self.events.append({"type": "preference", "scope": "building", "values": {"favourite": space_id}})
                result["remembered"] = "building"
        self.remember_preference(changed, scope, result)
        return result

    def apply_preferences(self, values: dict) -> None:
        """Effective preferences from the app (global ← this building) at session start or after a settings change;
        no events, nothing re-remembered."""
        for name in ("step_free", "avoid_lifts", *PREFERENCE_FIELDS[1:]):
            if name in values:
                setattr(self.profile, name, bool(values[name]))
        if "avoid_room_types" in values:
            rooms = values["avoid_room_types"] or []
            if not isinstance(rooms, list):
                raise ValueError("avoid_room_types must be a list")
            self.profile.avoid_room_types = sorted({str(room) for room in rooms})
        if "min_door_width_m" in values:
            width = values["min_door_width_m"]
            self.profile.min_door_width_m = float(width) if width else None
            if "min_door_width_m" in self.profile.assumed:
                self.profile.assumed.remove("min_door_width_m")
        self.guide_preferences = {name: values[name] for name in GUIDE_PREFERENCES if values.get(name) is not None}
