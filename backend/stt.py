"""ElevenLabs Scribe Realtime for the user's words (POST /stt/token in backend/app.py).

The browser streams its microphone straight to ElevenLabs (frontend/app/src/voice/scribe.ts); the backend only mints a
single-use token (valid 15 minutes, consumed on connect), so the API key never leaves it, and picks the building's
keyterms: the words people will say about this building, which Scribe is biased toward ("Staircase", "Meeting room",
"CNC mill"). Without ELEVENLABS_API_KEY, or with STT_MODE=browser, the app keeps the browser's own speech recognition.
docs/research/elevenlabs.md#2-speech-to-text-scribe."""

import json
import os
import re
import urllib.error
import urllib.request
from collections import Counter

from core.building_map import BuildingMap

TOKEN_URL = "https://api.elevenlabs.io/v1/single-use-token/realtime_scribe"
TIMEOUT_S = 10
# Realtime keyterm limits, enforced by the API (checked live 2026-10-25: 51 terms or a 21-character term are refused).
MAX_KEYTERMS = 50
KEYTERM_CHARS = 20
REF = re.compile(r"\s*\b[\w.-]*\d[\w.-]*\b")  # "Meeting room 3.07" → "Meeting room", "Desk 0.02-A" → "Desk"


class SttError(Exception):
    """ElevenLabs refused the token or could not be reached; `status` is its HTTP status (None: network)."""

    def __init__(self, status: int | None, detail: str):
        super().__init__(f"{status or 'network'}: {detail}")
        self.status = status


def enabled() -> bool:
    return bool(os.environ.get("ELEVENLABS_API_KEY")) and os.environ.get("STT_MODE", "scribe").lower() != "browser"


def single_use_token() -> str:
    request = urllib.request.Request(TOKEN_URL, data=b"", method="POST",
                                     headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return json.load(response)["token"]
    except urllib.error.HTTPError as error:
        raise SttError(error.code, error.read().decode(errors="replace")[:200]) from None
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as error:
        raise SttError(None, str(getattr(error, "reason", error))) from None


def keyterms(building: BuildingMap) -> list[str]:
    """Up to MAX_KEYTERMS words for this building with their numbers dropped (numbers are recognised anyway; there
    are too many rooms to list them all): names of spaces, lifts, stairs and floors first, then asset names, then room
    and asset types — each group most used first."""
    def ranked(names: list[str]) -> list[str]:
        return [term for term, _ in Counter(REF.sub("", name).strip(" -_,") for name in names).most_common()]

    places = ranked([*(space["name"] for space in building.spaces.values()),
                     *(connector["name"] for connector in building.connectors.values()),
                     *(floor["name"] for floor in building.floors.values())])
    things = ranked([asset["name"] for asset in building.assets.values()])
    kinds = ranked([kind.replace("_", " ").capitalize() for kind in
                    [*(space["room_type"] for space in building.spaces.values()),
                     *(asset["type"] for asset in building.assets.values())]])
    seen: set[str] = set()
    terms = []
    for term in [*places, *things, *kinds]:
        if term and len(term) <= KEYTERM_CHARS and term.lower() not in seen:
            seen.add(term.lower())
            terms.append(term)
    return terms[:MAX_KEYTERMS]
