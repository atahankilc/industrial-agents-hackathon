"""The living building in the Guide (backend/api/live): live clearance and effects on routes, live_status,
send_object."""



from backend.core.live import WALKER_CLEARANCE_M, LiveEffects

from backend.agents.tools.shared import MAX_RESULTS



class LiveTools:
    def live_clearance(self) -> float:
        """Free width this user needs to get past something standing in a walkway (backend/core/live.py)."""
        if self.profile.forklift:
            return 1.6
        return max(WALKER_CLEARANCE_M, self.profile.min_door_width_m or 0.0, 0.9 if self.profile.step_free else 0.0)

    def live_effects(self) -> LiveEffects | None:
        if self.live is None:
            return None
        obstacles, hazards = self.live.state()
        return LiveEffects(self.building, obstacles, hazards, self.live_clearance()) if obstacles or hazards else None

    def tool_live_status(self, query: str | None = None) -> dict:
        """What the building's connected things report now (backend/api/live/): each one's kind, state, where it is,
        where it drives to and whether it blocks a walkway; `query` keeps those whose name, kind or place has it."""
        if self.live is None:
            return {"error": "This building has no live data right now."}
        devices = self.live.devices(set(self.building.spaces))  # none in a space this viewer may not see
        if query:
            wanted = query.strip().lower()
            devices = [item for item in devices if any(wanted in str(item.get(key) or "").lower()
                                                       for key in ("name", "kind", "label", "space", "to"))] or devices
        self.highlight([item["space_id"] for item in devices if item.get("space_id") and query][:MAX_RESULTS])
        return {"simulated": any(item.get("source") == "sim" for item in devices), "devices": devices[:MAX_RESULTS * 2]}

    def tool_send_object(self, object: str, destination: str) -> dict:
        if self.object_dispatch is None:
            return {"error": "Only the building admin can send robots or vehicles."}
        return self.object_dispatch(object, destination)
