"""Drive a fake moving object along its missions (demo for access mode, backend/fleet.py).

  uv run python scripts/sim_object.py --api http://localhost:8765 --object obj-… --token … [--speed 1.2]

Polls GET /objects/{id}/mission; for an active mission it walks the `move` waypoints at --speed m/s, posting
POST /objects/{id}/position twice a second, waits at lifts and stairs, then posts /mission/done. A new mission
version (re-dispatch, cancel) interrupts the current one. Stdlib only."""

import argparse
import json
import math
import time
import urllib.request

TICK_S = 0.5
RIDE_S = {"call_lift": 4.0, "take_stairs": 2.0}  # demo pauses, not measured


class Device:
    def __init__(self, api: str, object_id: str, token: str) -> None:
        self.base = f"{api.rstrip('/')}/objects/{object_id}"
        self.token = token

    def call(self, method: str, path: str = "", body: dict | None = None) -> dict:
        request = urllib.request.Request(self.base + path, method=method,
                                         data=json.dumps(body).encode() if body is not None else None,
                                         headers={"X-Object-Token": self.token, "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read() or b"{}")

    def post(self, floor_id: str, x: float, y: float, heading: float | None) -> int | None:
        reply = self.call("POST", "/position", {"floor_id": floor_id, "x": x, "y": y, "heading_deg": heading})
        return reply.get("mission_version")


def heading_deg(first: list[float], second: list[float]) -> float | None:
    dx, dy = second[0] - first[0], second[1] - first[1]
    return None if dx == dy == 0 else round(math.degrees(math.atan2(dy, dx)), 1)


def run(device: Device, mission: dict, speed: float) -> bool:
    """Follow one mission; False if it was replaced or cancelled meanwhile."""
    version = mission["version"]
    for step in mission["steps"]:
        if step["op"] in RIDE_S:
            print(f"  {step['op']} {step['from_floor']} → {step['to_floor']}")
            time.sleep(RIDE_S[step["op"]])
        elif step["op"] == "move":
            points = step["waypoints"]
            for first, second in zip(points, points[1:]):
                distance = math.dist(first, second)
                ticks = max(1, math.ceil(distance / (speed * TICK_S)))
                for tick in range(1, ticks + 1):
                    x = first[0] + (second[0] - first[0]) * tick / ticks
                    y = first[1] + (second[1] - first[1]) * tick / ticks
                    if device.post(step["floor_id"], round(x, 3), round(y, 3), heading_deg(first, second)) != version:
                        return False
                    time.sleep(TICK_S)
        elif step["op"] == "arrive":
            device.call("POST", "/mission/done")
            print(f"  arrived at {step['name']}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="http://localhost:8765")
    parser.add_argument("--object", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--speed", type=float, default=1.2, help="metres per second")
    args = parser.parse_args()
    device = Device(args.api, args.object, args.token)
    done: set[tuple[str, int]] = set()
    while True:
        mission = device.call("GET", "/mission")
        key = (mission.get("mission_id"), mission.get("version"))
        if mission.get("status") == "active" and key not in done:
            print(f"mission {key[0]} v{key[1]} → {mission['to']['name']} ({mission['length_m']} m)")
            if run(device, mission, args.speed):
                done.add(key)
        time.sleep(1.0)


if __name__ == "__main__":
    main()
