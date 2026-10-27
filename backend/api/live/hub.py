"""The hub: one world per building, the tick thread that runs them while someone looks, and a session's view of
its building's world."""

import queue
import threading
import time
import traceback
from typing import Callable


from backend.core.building_map import BuildingMap
from backend.core.live import Hazard, Obstacle

from backend.api.live.reroute import visible
from backend.api.live.world import IDLE_S, TICK_S, LiveWorld


class LiveHub:
    def __init__(self, building_map: Callable[[str], BuildingMap]) -> None:
        self.building_map = building_map  # building id → BuildingMap (base data, read only)
        self.worlds: dict[str, LiveWorld] = {}
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.planner_thread: threading.Thread | None = None
        self.jobs: queue.Queue = queue.Queue()

    def world(self, building_id: str, start: bool = True) -> LiveWorld | None:
        with self.lock:
            world = self.worlds.get(building_id)
        if world is None and start:
            # built outside the hub's lock: a big building takes a while, and other buildings keep running
            built = LiveWorld(building_id, self.building_map(building_id))
            built.planner = self.plan
            with self.lock:
                world = self.worlds.setdefault(building_id, built)
            self.ensure_thread()
        if world is not None and start:
            world.last_view = time.time()
        return world

    def ensure_thread(self) -> None:
        with self.lock:
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self.run, daemon=True, name="live-world")
                self.thread.start()
            if self.planner_thread is None or not self.planner_thread.is_alive():
                self.planner_thread = threading.Thread(target=self.plan_forever, daemon=True, name="live-planner")
                self.planner_thread.start()

    def plan(self, world: LiveWorld, device_id: str) -> None:
        self.jobs.put((world, device_id))

    def plan_forever(self) -> None:
        while True:
            world, device_id = self.jobs.get()
            try:
                world.plan_off_clock(device_id)
            except Exception:  # noqa: BLE001 — a failed plan leaves the device idle; it asks again
                traceback.print_exc()
                with world.lock:
                    device = world.devices.get(device_id)
                    if device is not None:
                        device.planning, device.pause_s, device.pause_state = False, 10.0, "idle"

    def run(self) -> None:
        last = time.time()
        while True:
            time.sleep(TICK_S)
            now = time.time()
            self.tick(min(now - last, 1.0), now)
            last = now

    def tick(self, dt: float, now: float) -> None:
        """Every world one step on; a world nobody looked at for IDLE_S stops (its things vanish with it)."""
        with self.lock:
            worlds = list(self.worlds.items())
        for building_id, world in worlds:
            if now - world.last_view > IDLE_S:
                with self.lock:
                    if self.worlds.get(building_id) is world:
                        del self.worlds[building_id]
                continue
            try:
                world.step(dt)
            except Exception:  # noqa: BLE001 — one broken world must not stop the others
                traceback.print_exc()

    def state(self, building_id: str) -> tuple[list[Obstacle], list[Hazard]]:
        world = self.world(building_id, start=False)
        return world.obstacles() if world else ([], [])


class SessionLive:
    """What a session (backend/agents/tools/ `session.live`) asks of its building's live world."""

    def __init__(self, hub: "LiveHub", building_id: str) -> None:
        self.hub = hub
        self.building_id = building_id

    def state(self) -> tuple[list[Obstacle], list[Hazard]]:
        return self.hub.state(self.building_id)

    def devices(self, spaces: set[str] | None = None) -> list[dict]:
        """The things as the Guide's live_status gives them; with `spaces`, only those standing in one of them or
        in no space (access mode: never one in a space the viewer may not see)."""
        world = self.hub.world(self.building_id, start=False)
        if world is None:
            return []
        keys = ("name", "label", "kind", "source", "state", "to", "left_s")
        return [{**{key: item[key] for key in keys if item.get(key) is not None},
                 "space": item["position"]["space"], "space_id": item["position"]["space_id"],
                 "floor": world.building.floor_name(item["position"]["floor_id"]),
                 **({"blocking": item["blocking"]["space"]} if item.get("blocking") else {}),
                 "reported_ago_s": item["reported_ago_s"]}
                for item in visible(world.snapshot()["devices"], spaces)]
