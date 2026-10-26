---
id: plan-guide-agent
summary: Task-by-task implementation plan for the Phase 3 Building Guide brain (resolution + fan-out, tools, grounding, tool-use loop, REPL, scripted conversations).
sources: [../specs/2026-10-24-guide-agent-design.md, core/building_map.py, core/solvers.py, core/question_parser.py, agent/llm_parser.py, tests/test_parsing_modes.py]
related: [../specs/2026-10-24-guide-agent-design.md, ../../architecture/ai-agents.md]
---

# Building Guide Agent Implementation Plan

> **Since the merge of `origin/main` (2026-10-24):** this Guide lives at `agent/guide_v1/` (REPL:
> `python -m agent.guide_v1`) and its solvers at `core/solvers_v1.py`; `agent/guide/` and `core/solvers.py` below
> are the names at the time of writing. The canonical Guide used by the backend is `agent/guide.py`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A multi-turn, terminal-testable Building Guide that answers building questions and gives directions using only facts from `core/`, asks back only when the answer depends on it, and never states an ungrounded number or ref.

**Architecture:** A new package `agent/guide/`. Code resolves free-text place names to candidate space ids and runs each solver once per candidate (`resolve.py`); a small read-only tool layer wraps `core/` and holds session state (`tools.py`); a manual Anthropic tool-use loop drives the conversation (`guide.py`, `prompt.py`); a code checker verifies every number/ref in the reply against tool results (`grounding.py`); a REPL wraps it (`__main__.py`). The benchmark path (`agent/answer.py`, `run_benchmark`, `core/`) is not modified.

**Tech Stack:** Python ≥ 3.12 via `uv`, `anthropic` SDK (`client.beta.messages.create`), networkx/shapely via `core/`, pytest.

**Spec:** [docs/superpowers/specs/2026-10-24-guide-agent-design.md](../specs/2026-10-24-guide-agent-design.md)

## Global Constraints

- Never modify `core/building_map.py`, `core/solvers.py`, `core/question_parser.py`, `agent/answer.py`, `agent/run_benchmark.py`, `benchmark/`. Import from them only. `uv run pytest -q` must stay green (benchmark tests included).
- Every room, ref, count, area, distance, metre value or route step in a reply comes from a tool result in this session.
- Tools never guess: 0 matches → `status: "not_found"` (+ nearest names); several candidates with different answers → `status: "ambiguous"` (+ options, ≤ 5). Code compares candidate answers, never the model.
- Model: env `GUIDE_MODEL`, default `claude-opus-5-5`; effort env `GUIDE_EFFORT`, default `medium`; send `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"` (same as `agent/llm_parser.py`). No `thinking` param (Opus 5.5 runs adaptive), no `temperature`, no forced `tool_choice`.
- Append the full `response.content` as the assistant message every iteration (thinking blocks must be passed back unchanged); all `tool_result` blocks of one response go in a single user message.
- Session state (position, step_free, closures) lives in code (`Session`), lasts for the conversation, never written to `building.json`.
- No hard-coding to dataset buildings, names or ids in `agent/guide/` (tests may use dev fixtures).
- Commit only via `/ship` with `.claude/worklog/PENDING.md` filled ([dev-workflow.md](../../../../docs/guides/dev-workflow.md)); never `git commit` directly.
- Docs/memory-bank edits → `uv run python scripts/check_links.py` must print `OK`.

## Review Focus

1. **Turkish input** ("3D yazıcı nerede?", "asansör bozuk") — the model translates to tool arguments; tools only see English/building vocabulary. Expect a correct Turkish reply with grounded numbers (comma decimals). Pinned by a scripted conversation in Task 6 and a grounding test in Task 3.
2. **Room typed by ref or with a "room" prefix** ("room 1.14", "1.14") — must resolve to the space with that ref. Test in Task 1.
3. **Something the building doesn't have** ("coffee machine" in a lab building, "room 9.99", "the lift" in a building without lifts) — `not_found` with nearest names, never a made-up place. Tests in Tasks 1 and 2.
4. **API failure mid-turn** (rate limit, network) in the REPL — print a one-line error, keep the session and history usable, don't crash. Test in Task 5.
5. **Blank or whitespace-only input** in the REPL — ignored without an API call. Test in Task 5.

---

### Task 1: Place resolution and candidate fan-out

**Files:**
- Create: `agent/guide/__init__.py` (empty), `agent/guide/resolve.py`
- Test: `tests/test_guide_resolve.py`

**Interfaces:**
- Consumes: `BuildingMap` (`spaces`, `assets`, `connectors`, `openings`, `floors`, `search`, `floor_name`), `core.question_parser.Resolver(bmap).asset_type(phrase)` (raises `ParseError`), `core.solvers.label`.
- Produces:
  - `MAX_OPTIONS = 5`
  - `resolve_places(bmap: BuildingMap, text: str) -> list[str]` — candidate **space ids**, deduplicated, stable order.
  - `resolve_elements(bmap: BuildingMap, text: str) -> list[str]` — candidate connector/opening ids that can be closed.
  - `nearest_names(bmap: BuildingMap, text: str, n: int = 3) -> list[str]`
  - `describe(bmap: BuildingMap, element_id: str) -> dict` — `{"id", "name", "ref", "floor", "kind"}` for a space (`kind` = room_type), connector (`kind` = lift/stairs, `floor` = joined floor names) or opening.
  - `fan_out(bmap, slots: dict[str, list[str]], run: Callable[[dict[str, str]], dict]) -> dict` — see Step 3.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_guide_resolve.py — fixtures are dev buildings (tests may name them; agent/guide may not)
FACTORY = Path("data/dev/proc-factory-dev-004")   # two 3D printers, both in F0-S004
CAMPUS = Path("data/dev/proc-campus-dev-001")     # 3D printers in F1-S014 (Makerspace 1.14) and F2-S020 (Lab 2.20); Lift 1, Lift 2
OSM_DUP = Path("data/dev/osm-way27917482")        # three "Generic room 03.08.033" on Floor 3 (S015, S016, S017)

def test_asset_type_phrase_resolves_to_rooms_holding_it():
    assert resolve_places(bmap(FACTORY), "the 3D printer") == ["proc-factory-dev-004-F0-S004"]
    assert sorted(resolve_places(bmap(CAMPUS), "3D printer")) == ["proc-campus-dev-001-F1-S014", "proc-campus-dev-001-F2-S020"]

def test_type_phrase_does_not_pull_in_substring_types():
    # "printer" is its own type in CAMPUS; must not include multifunction printers' rooms
    spaces = resolve_places(bmap(CAMPUS), "printer")
    assert all(any(a["type"] == "printer" and a["space_id"] == s for a in bmap(CAMPUS).assets.values()) for s in spaces)

def test_ref_and_room_prefix_resolve_to_the_space():
    assert resolve_places(bmap(CAMPUS), "1.14") == ["proc-campus-dev-001-F1-S014"]
    assert resolve_places(bmap(CAMPUS), "room 1.14") == ["proc-campus-dev-001-F1-S014"]
    assert resolve_places(bmap(CAMPUS), "Makerspace 1.14") == ["proc-campus-dev-001-F1-S014"]

def test_duplicate_names_return_every_candidate():
    assert resolve_places(bmap(OSM_DUP), "Generic room 03.08.033") == [f"osm-way27917482-F3-S0{n}" for n in (15, 16, 17)]

def test_unknown_place_returns_nothing_and_nearest_names():
    assert resolve_places(bmap(CAMPUS), "room 9.99") == []
    assert resolve_places(bmap(FACTORY), "espresso robot") == []
    assert len(nearest_names(bmap(CAMPUS), "Makerspace 1.41")) >= 1

def test_closure_elements():
    assert resolve_elements(bmap(CAMPUS), "the lift") == ["proc-campus-dev-001-V02", "proc-campus-dev-001-V04"]
    assert resolve_elements(bmap(CAMPUS), "Lift 2") == ["proc-campus-dev-001-V04"]
    assert resolve_elements(bmap(Path("data/dev/resplan-1465")), "the lift") == []

def test_fan_out_agrees_when_results_match():
    out = fan_out(bmap(CAMPUS), {"place": ["a", "b"]}, lambda c: {"summary": "same", "x": 1})
    assert out == {"status": "ok", "summary": "same", "x": 1}

def test_fan_out_ambiguous_lists_options_with_their_results():
    out = fan_out(bmap(CAMPUS), {"place": ["proc-campus-dev-001-F1-S014", "proc-campus-dev-001-F2-S020"]},
                  lambda c: {"summary": c["place"]})
    assert out["status"] == "ambiguous" and len(out["options"]) == 2
    assert out["options"][0]["choices"]["place"]["ref"] == "1.14"
    assert out["options"][0]["result"]["summary"] == "proc-campus-dev-001-F1-S014"

def test_fan_out_not_found_and_too_many():
    assert fan_out(bmap(CAMPUS), {"place": []}, lambda c: {})["status"] == "not_found"
    many = fan_out(bmap(CAMPUS), {"a": list("123"), "b": list("12")}, lambda c: {"summary": str(c)})
    assert many["status"] == "ambiguous" and len(many["options"]) <= MAX_OPTIONS
```

(`bmap(path)` = a `functools.cache`d `BuildingMap.load`.)

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_guide_resolve.py -q`
Expected: FAIL / ImportError (`agent.guide.resolve` missing).

- [ ] **Step 3: Implement `agent/guide/resolve.py`**

`resolve_places` tries, in order, and returns the first non-empty result (deduplicated, order kept):
1. exact space id / asset id (asset → its space);
2. after stripping a leading "the ", "a ", "room ", case-insensitive exact space ref or name;
3. `Resolver(bmap).asset_type(phrase)` → spaces holding an asset of that type (sorted by space id);
4. exact asset name → its space;
5. `bmap.search(phrase)` → space hits + asset hits' spaces.
Do **not** use `search` before step 3 (substring "printer" would pull in multifunction printers).

`resolve_elements`: exact connector/opening id or name (case-insensitive, leading "the " stripped) → that one; otherwise connectors whose `kind` equals the phrase's last word with a trailing "s" stripped ("lift", "lifts", "stairs"/"staircase" → `stairs`), sorted by id; else `[]`.

`nearest_names`: `difflib.get_close_matches` over space names, refs and asset names, `cutoff=0.6`.

`fan_out` algorithm:
```
if any slot list is empty → {"status": "not_found", "slot": <first empty slot>}
combos = itertools.product over slots (dict per combo); keep at most MAX_OPTIONS combos
if the full product is larger than MAX_OPTIONS → do not run; return
    {"status": "ambiguous", "options": [{"choices": {slot: describe(id)}} ...first MAX_OPTIONS combos], "truncated": True}
results = [run(combo) for combo in combos]
if all results equal (json.dumps(sort_keys=True)) → {"status": "ok", **results[0]}
else → {"status": "ambiguous", "options": [{"choices": {slot: describe(id) for slots with >1 candidate}, "result": r}]}
```
A `run` may raise `MapError`/`ValueError`; catch it per combo and use `{"status": "error", "summary": str(error)}` as that combo's result.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_guide_resolve.py -q` → all pass.

- [ ] **Step 5: Commit** — fill `.claude/worklog/PENDING.md` (claims: resolution order, fan-out contract, tests), run `/ship`.

---

### Task 2: Lookup tools — locate, find, place info, building facts

**Files:**
- Create: `agent/guide/tools.py`
- Test: `tests/test_guide_tools.py`

**Interfaces:**
- Consumes: Task 1 (`resolve_places`, `resolve_elements`, `nearest_names`, `describe`, `fan_out`); `core.solvers` (`SOLVERS`, `reachable_rooms`, `shared_walls`, `room_stacked`, `area`, `label`); `Resolver(bmap).floor_id(phrase)`, `.room_type(phrase)`, `.asset_type(phrase)`.
- Produces:
  - `@dataclass Session: position: str | None = None; step_free: bool = False; closures: list[list[str]] = field(default_factory=list)` (each inner list = candidate element ids for one stated closure).
  - `TOOLS: list[dict]` — Anthropic tool definitions (`name`, `description`, `input_schema` with `additionalProperties: false`, `strict: True`), stable order.
  - `run_tool(bmap: BuildingMap, session: Session, name: str, args: dict) -> dict` — dispatch; unknown tool or bad args → `{"status": "error", "summary": ...}`; never raises.
  - Every result dict has `status` (`ok` | `not_found` | `ambiguous` | `error` | `need_start`) and `summary` (one code-written sentence, used by the grounding fallback). `not_found` results carry `nearest`.
  - Tool names and inputs (this task): `locate(thing: str)`, `find_places(query: str, floor: str | null)`, `place_info(place: str)`, `building_fact(kind: enum, place: str|null, place2: str|null, floor: str|null, room_type: str|null, asset_type: str|null, direction: "above"|"below"|null, min_width_m: number|null, closed: str|null, step_free: bool|null)`. `kind` enum = `largest_room, floor_area_total, count, shared_walls_count, room_stacked, straight_line_3d, errand, wide_delivery_count, step_free_reachable_count, what_if_door`.

- [ ] **Step 1: Write the failing tests**

```python
def test_locate_lists_every_room_with_counts():
    out = run_tool(bmap(CAMPUS), Session(), "locate", {"thing": "3D printer"})
    assert out["status"] == "ok"
    assert {(r["ref"], r["count"]) for r in out["rooms"]} == {("1.14", 4), ("2.20", 1)}

def test_locate_unknown_thing_is_not_found_with_nearest():
    out = run_tool(bmap(FACTORY), Session(), "locate", {"thing": "espresso robot"})
    assert out["status"] == "not_found" and "nearest" in out

def test_place_info_matches_core():
    b = bmap(CAMPUS); out = run_tool(b, Session(), "place_info", {"place": "1.14"})
    assert out["area_m2"] == round(area(b, "proc-campus-dev-001-F1-S014"), 2)
    assert out["shared_walls"] == shared_walls(b, "proc-campus-dev-001-F1-S014")["count"]
    assert "3D printer 1.14-A" in out["assets"]

def test_place_info_ambiguous_place_asks():
    out = run_tool(bmap(OSM_DUP), Session(), "place_info", {"place": "Generic room 03.08.033"})
    assert out["status"] == "ambiguous" and len(out["options"]) == 3

def test_building_fact_equals_solver_on_gold_inputs():
    # every dev benchmark question: rebuild names from gold inputs, call building_fact, compare with core.solvers.solve
    for directory, q in dev_benchmark_questions():       # helper reuses tests.test_question_parser.labelled_questions filtered to data/dev and kinds above
        out = run_tool(bmap(directory), Session(), "building_fact", args_from_gold(bmap(directory), q))
        assert out["status"] in ("ok", "ambiguous"), (q["id"], out)
        if out["status"] == "ok":
            assert out["result"] == solve(bmap(directory), q["kind"], q["inputs"]), q["id"]

def test_tools_schema_is_strict_and_stable():
    assert [t["name"] for t in TOOLS][:4] == ["locate", "find_places", "place_info", "building_fact"]
    assert all(t["input_schema"]["additionalProperties"] is False for t in TOOLS)

def test_bad_args_never_raise():
    assert run_tool(bmap(CAMPUS), Session(), "building_fact", {"kind": "largest_room"})["status"] == "error"
    assert run_tool(bmap(CAMPUS), Session(), "nope", {})["status"] == "error"
```

`args_from_gold` maps gold `inputs` to names: space ids → space **name** (or ref when the name is duplicated on that floor), `floor_id` → floor name, `closed` → connector name, `min_width` → `min_width_m`; it lives in the test file.

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_guide_tools.py -q` → ImportError.

- [ ] **Step 3: Implement the four tools in `agent/guide/tools.py`**

- `locate`: asset type via `Resolver.asset_type`, else exact asset name, else assets whose name contains every word; group by space → `rooms: [{**describe(space), "count", "assets": [names]}]` sorted by floor level then ref. No fan-out: it lists them all.
- `find_places`: `bmap.search(query, floor_level)` (floor phrase → level via `Resolver.floor_id`), ≤ 10 hits, each `describe`d plus containing room for assets.
- `place_info`: `fan_out` over `resolve_places(place)`; per space: `describe`, `area_m2` (2 dp), `assets` (names, ≤ 15, + `assets_total`), `shared_walls` (count) + `neighbours` (names), `above`/`below` (`room_stacked` name or null; catch `ValueError`).
- `building_fact`: map args to the solver's `inputs` (place/place2 → `start`/`first`/`second` candidates via `resolve_places`; floor → `floor_id`; room_type/asset_type via `Resolver`; `closed` via `resolve_elements`; `min_width_m` → `min_width`), then `fan_out` calling `core.solvers.solve(bmap, kind, inputs)`. `count` uses `asset_type` + `floor`. Result key `result` = the solver's dict unchanged; `summary` written per kind (e.g. `"The largest lab on Floor 2 is Lab 2.20 (2.20) at 41.37 m²."`).

- [ ] **Step 4: Run to verify they pass** — `uv run pytest tests/test_guide_tools.py tests/test_guide_resolve.py -q` → pass.

- [ ] **Step 5: Commit** via `/ship`.

---

### Task 3: Route tool and session tool

**Files:**
- Modify: `agent/guide/tools.py` (add `route`, `update_session`, append to `TOOLS`)
- Test: `tests/test_guide_route.py`

**Interfaces:**
- Consumes: Task 1, Task 2 (`Session`, `run_tool`, `TOOLS`), `core.solvers.route`, `BuildingMap.closed`.
- Produces:
  - `route(to: str, from: str|null, via: list[str]|null, step_free: bool|null)` → `ok` result with `result` = the `core.solvers.route` dict (`reachable`, `optimal_length_m`, `space_path`, `element_path`, `legs`, `steps`), plus `from`, `to` (`describe`d), `step_free`, `closed` (names). `from` null → `session.position`; both null → `{"status": "need_start", "summary": "Ask where the user is starting from."}`. `step_free` null → `session.step_free`.
  - `update_session(position: str|null, step_free: bool|null, close: list[str]|null, reopen: list[str]|null)` → `ok` with the new session state described by names; ambiguous/not_found position follows the fan-out contract; each `close` phrase → `resolve_elements` candidates appended to `session.closures` (not_found if empty); `reopen` removes closures whose candidates intersect the phrase's elements.

- [ ] **Step 1: Write the failing tests**

```python
def test_route_equals_core_route():
    b = bmap(CAMPUS)
    out = run_tool(b, Session(), "route", {"from": "Main lobby", "to": "Makerspace 1.14", "via": None, "step_free": None})
    assert out["status"] == "ok"
    assert out["result"] == core_route(b, "proc-campus-dev-001-F0-S014", "proc-campus-dev-001-F1-S014")

def test_route_to_two_printer_rooms_is_ambiguous_but_one_room_is_not():
    s = Session(position="proc-campus-dev-001-F0-S014")
    assert run_tool(bmap(CAMPUS), s, "route", {"to": "3D printer", "from": None, "via": None, "step_free": None})["status"] == "ambiguous"
    s2 = Session(position=lobby_of(FACTORY))
    assert run_tool(bmap(FACTORY), s2, "route", {"to": "3D printer", "from": None, "via": None, "step_free": None})["status"] == "ok"

def test_no_start_asks_for_it():
    assert run_tool(bmap(CAMPUS), Session(), "route", {"to": "1.14", "from": None, "via": None, "step_free": None})["status"] == "need_start"

def test_session_step_free_and_closures_apply_to_later_routes():
    b, s = bmap(CAMPUS), Session()
    run_tool(b, s, "update_session", {"position": "Main lobby", "step_free": True, "close": ["Lift 1"], "reopen": None})
    out = run_tool(b, s, "route", {"to": "Lab 2.20", "from": None, "via": None, "step_free": None})
    assert out["result"] == core_route(b, "proc-campus-dev-001-F0-S014", "proc-campus-dev-001-F2-S020",
                                       step_free=True, closed="proc-campus-dev-001-V02")
    assert b.closed == set()          # session closures never leak into the shared map

def test_ambiguous_closure_only_asks_when_routes_differ():
    # "the lift" = Lift 1 or Lift 2: ok if both closures give the same route, else ambiguous with lift options
    b, s = bmap(CAMPUS), Session(position="proc-campus-dev-001-F0-S014", step_free=True)
    run_tool(b, s, "update_session", {"position": None, "step_free": None, "close": ["the lift"], "reopen": None})
    out = run_tool(b, s, "route", {"to": "Lab 2.20", "from": None, "via": None, "step_free": None})
    r1 = core_route(b, s.position, "proc-campus-dev-001-F2-S020", step_free=True, closed="proc-campus-dev-001-V02")
    r2 = core_route(b, s.position, "proc-campus-dev-001-F2-S020", step_free=True, closed="proc-campus-dev-001-V04")
    assert out["status"] == ("ok" if r1 == r2 else "ambiguous")

def test_close_in_building_without_lifts_is_not_found():
    out = run_tool(bmap(Path("data/dev/resplan-1465")), Session(), "update_session",
                   {"position": None, "step_free": None, "close": ["the lift"], "reopen": None})
    assert out["status"] == "not_found"
```

(`core_route(b, start, dest, step_free=False, closed=None)` = `core.solvers.route`; `lobby_of` = the space a step-free entrance opens into, computed from `b.overview()["entrances"]` in the test file.)

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_guide_route.py -q` → FAIL.

- [ ] **Step 3: Implement `route` and `update_session`**

`route` fan-out slots: `from`, `to`, each `via[i]`, and one slot per session closure (`closure0`, …). `run(combo)`: set `bmap.closed = saved | {closure ids in combo}`, call `core.solvers.route(bmap, from, to, step_free=..., via=[...])`, restore `bmap.closed` in `finally`. Unreachable → still `status: "ok"` with `result.reachable == False` and a summary saying no (step-free) route exists with the current closures. Summary for reachable: `"<from name> → <to name>: <metres rounded to 0 dp> m<, step-free><, avoiding X>."`

- [ ] **Step 4: Run to verify they pass** — `uv run pytest tests/test_guide_route.py tests/test_guide_tools.py -q` → pass.

- [ ] **Step 5: Commit** via `/ship`.

---

### Task 4: Grounding checker

**Files:**
- Create: `agent/guide/grounding.py`
- Test: `tests/test_guide_grounding.py`

**Interfaces:**
- Consumes: nothing from earlier tasks except result dicts (plain JSON).
- Produces:
  - `NUMBER = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*(?![\w])")` — token pattern used on both sides ("3D" is not a number; "03.08.033" is one token).
  - `grounded_tokens(sources: list[dict | str]) -> set[str]` — every NUMBER token in the JSON dump of each source (comma → dot), every float rounded to 0/1/2 dp, and `len()` of every list found in the dicts.
  - `ungrounded(text: str, grounded: set[str]) -> list[str]` — NUMBER tokens in `text` (comma → dot) not in `grounded`, ignoring list markers (a token at line start followed by `.` or `)`).
  - `fallback_text(results: list[dict]) -> str` — the `summary` of each result in order, plus numbered `result.steps` for route results; never empty (`"I couldn't find an answer to that in this building."`).

- [ ] **Step 1: Write the failing tests**

```python
G = grounded_tokens([{"optimal_length_m": 37.42, "ref": "1.14", "name": "Generic room 03.08.033", "options": [1, 2]}])

def test_rounding_and_comma_decimals_are_grounded():
    assert ungrounded("About 37 m, exactly 37.4 m or 37,42 m.", G) == []

def test_invented_and_over_rounded_numbers_are_caught():
    assert ungrounded("It is about 40 m from room 9.99.", G) == ["40", "9.99"]

def test_refs_names_option_counts_and_list_markers():
    assert ungrounded("1. Go to 1.14\n2) then Generic room 03.08.033. I found 2 options.", G) == []

def test_3d_is_not_a_number():
    assert ungrounded("The 3D printer is in 1.14.", G) == []

def test_turkish_reply_with_comma_decimal():
    assert ungrounded("3D yazıcı 1.14 numaralı odada, yaklaşık 37,4 m.", G) == []

def test_fallback_uses_summaries_and_steps():
    text = fallback_text([{"status": "ok", "summary": "A → B: 37 m.", "result": {"steps": ["Start in A.", "Arrive at B."]}}])
    assert "A → B: 37 m." in text and "1. Start in A." in text
    assert fallback_text([])
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_guide_grounding.py -q` → ImportError.
- [ ] **Step 3: Implement `agent/guide/grounding.py`** per the interface.
- [ ] **Step 4: Run to verify they pass** — same command → pass.
- [ ] **Step 5: Commit** via `/ship`.

---

### Task 5: Guide loop, prompt and REPL

**Files:**
- Create: `agent/guide/prompt.py`, `agent/guide/guide.py`, `agent/guide/__main__.py`
- Test: `tests/test_guide_loop.py`

**Interfaces:**
- Consumes: Task 2/3 (`Session`, `TOOLS`, `run_tool`), Task 4 (`grounded_tokens`, `ungrounded`, `fallback_text`), `agent.llm_parser.LlmUsage`, `BuildingMap.overview()`.
- Produces:
  - `prompt.system_blocks(bmap: BuildingMap) -> list[dict]` — `[{"type": "text", "text": RULES}, {"type": "text", "text": overview_text(bmap), "cache_control": {"type": "ephemeral"}}]`. `overview_text` = `bmap.overview()` (floors, lifts/stairs, entrances) + sorted room types + sorted asset types; **no** per-room facts.
  - `RULES` covers: only state facts from tool results; call a tool for every fact; on `ambiguous` ask one short question listing the options by ref/floor; on `not_found` say so and offer `nearest`; on `need_start` ask where they are; a constraint the user states → `update_session` and acknowledge as a statement in the same reply; echo understanding in one line then numbered steps with landmarks, explicit floor changes, rounded metres; no arithmetic on tool numbers; reply in the user's language; out-of-scope → one line that you help with this building.
  - `@dataclass TurnResult: text: str; asked: bool; space_ids: list[str]; asset_ids: list[str]; connector_ids: list[str]; routes: list[dict]; options: list[dict]; tool_calls: list[dict]; usage: LlmUsage; grounded: bool`
  - `class Guide: __init__(self, building_dir: Path, client: anthropic.Anthropic | None = None)`; attributes `bmap`, `session: Session`, `messages: list`, `usage: LlmUsage`; `turn(self, text: str) -> TurnResult`.
  - Constants: `MODEL = os.environ.get("GUIDE_MODEL", "claude-opus-5-5")`, `EFFORT = os.environ.get("GUIDE_EFFORT", "medium")`, `MAX_TOKENS = 16000`, `MAX_TOOL_ROUNDS = 8`.
  - CLI: `uv run --env-file .env python -m agent.guide <building_dir> [--show-tools]`.

- [ ] **Step 1: Write the failing tests** (offline; `FakeClient` as in `tests/test_parsing_modes.py`, extended so a reply can carry `tool_use` blocks: `SimpleNamespace(type="tool_use", id=..., name=..., input={...})`; it records every `create(**kwargs)` call)

```python
def test_tool_round_then_answer():
    client = FakeClient(tool_reply("locate", {"thing": "3D printer"}), text_reply("The 3D printers are in Makerspace 1.14 (1.14) and Lab 2.20 (2.20)."))
    result = Guide(CAMPUS, client).turn("Where is the 3D printer?")
    assert result.grounded and not result.asked
    assert "proc-campus-dev-001-F1-S014" in result.space_ids
    second = client.calls[1]
    assert second["messages"][-1]["content"][0]["type"] == "tool_result"        # all results in one user message
    assert second["messages"][-2]["content"] is client.replies_sent[0].content   # full content appended

def test_request_shape():
    client = FakeClient(text_reply("Hello."))
    Guide(CAMPUS, client).turn("hi")
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["tools"] == TOOLS
    assert call["betas"] == ["server-side-fallback-2026-07-01"] and call["fallbacks"] == "default"
    assert call["output_config"] == {"effort": "medium"}
    assert "thinking" not in call and "tool_choice" not in call
    assert call["system"][-1]["cache_control"] == {"type": "ephemeral"}

def test_ungrounded_reply_gets_one_repair_then_fallback():
    client = FakeClient(tool_reply("place_info", {"place": "1.14"}), text_reply("It is 999 m²."), text_reply("Still 999 m²."))
    result = Guide(CAMPUS, client).turn("How big is 1.14?")
    assert len(client.calls) == 3 and "999" in client.calls[2]["messages"][-1]["content"]
    assert not result.grounded and "999" not in result.text and "1.14" in result.text   # fallback from summaries

def test_ambiguous_turn_reports_options_and_asked():
    client = FakeClient(tool_reply("route", {"to": "3D printer", "from": "Main lobby", "via": None, "step_free": None}),
                        text_reply("There are 3D printers in Makerspace 1.14 (Floor 1) and Lab 2.20 (Floor 2). Which one?"))
    result = Guide(CAMPUS, client).turn("Take me to the 3D printer, I'm in the main lobby")
    assert result.asked and len(result.options) == 2

def test_session_survives_turns():
    client = FakeClient(tool_reply("update_session", {"position": "Main lobby", "step_free": True, "close": None, "reopen": None}),
                        text_reply("Noted — step-free routes from now on."), text_reply("Hi again."))
    g = Guide(CAMPUS, client); g.turn("I'm in a wheelchair, in the main lobby"); g.turn("hello")
    assert g.session.step_free and g.session.position == "proc-campus-dev-001-F0-S014"
    assert len(client.calls[2]["messages"]) == 5     # user, assistant(tool_use), user(tool_result), assistant, user

def test_too_many_tool_rounds_falls_back():
    client = FakeClient(*[tool_reply("locate", {"thing": "3D printer"})] * 9)
    assert Guide(CAMPUS, client).turn("loop").text

def test_repl_ignores_blank_input_and_survives_api_errors(capsys):
    client = FakeClient(raises=anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x")))
    guide = Guide(CAMPUS, client)
    repl(guide, ["", "   ", "hi"])                      # agent.guide.__main__.repl
    assert len(client.calls) == 1 and "error" in capsys.readouterr().out.lower()
    assert guide.messages == []        # failed turn rolled back, session still usable
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_guide_loop.py -q` → ImportError.

- [ ] **Step 3: Implement**

`Guide.turn` algorithm:
```
if text.strip() == "": return empty TurnResult (no API call)
checkpoint = len(self.messages); append {"role": "user", "content": text}
turn_results = []; repaired = False
for round in range(MAX_TOOL_ROUNDS):
    response = client.beta.messages.create(model, max_tokens, system=system_blocks, tools=TOOLS, messages,
                                           output_config={"effort": EFFORT}, betas=[FALLBACK_BETA], fallbacks="default")
    track usage; append {"role": "assistant", "content": response.content}
    if stop_reason == "refusal" or "max_tokens": text = fallback_text(turn_results); break
    tool_uses = [b for b in response.content if b.type == "tool_use"]
    if tool_uses:
        results = [run_tool(bmap, session, b.name, b.input) for b in tool_uses]; turn_results += results
        append one user message with tool_result blocks (content=json.dumps(result), is_error=result["status"]=="error")
        continue
    text = joined text blocks
    bad = ungrounded(text, grounded_tokens(all session tool results + [overview_text]))
    if bad and not repaired: append user message "These values are not in any tool result: <bad>. Rewrite using only tool results."; repaired = True; continue
    if bad: text = fallback_text(turn_results); grounded = False
    break
else: text = fallback_text(turn_results)
```
On any `anthropic.APIError`: truncate `self.messages` to `checkpoint` and re-raise. Keep all session tool results across turns (grounded set for follow-ups). `asked` = last non-empty line of `text` ends with "?". ids: from `ok` results of this turn (`describe`d ids, `result.space_path`, `result.element_path` split into connector ids via `bmap.connectors`, asset ids from `locate`); `routes` = `result` of `ok` route calls; `options` = options of the last `ambiguous` result.

`__main__.py`: `repl(guide, lines: Iterable[str])` loop — skip blank lines; print reply; with `--show-tools` print each tool call name + args + status; after each turn print `tokens in/out, cache read` and estimated cost (`$4/M in, $20/M out, $0.20/M cache read, $5/M cache write` for the default model); catch `anthropic.APIError` → print `error: <message>` and continue. `main()` reads stdin lines via `input("> ")` until EOF/`exit`.

- [ ] **Step 4: Run to verify they pass** — `uv run pytest tests/test_guide_loop.py -q` → pass; then `uv run pytest -q` → whole suite green.

- [ ] **Step 5: Manual smoke test (live, ~$0.10)** — `uv run --env-file .env python -m agent.guide data/dev/proc-campus-dev-001 --show-tools`, ask "Where is the 3D printer?", then "how do I get there from the main lobby?" → expect a question about which printer room. Paste the transcript into PENDING.md.

- [ ] **Step 6: Commit** via `/ship`.

---

### Task 6: Scripted conversations, live runner, docs

**Files:**
- Create: `tests/guide_conversations/*.json` (≥ 7 files), `scripts/eval_guide.py`, `tests/test_guide_conversations.py`
- Modify: `docs/guides/commands.md` (Guide section), `docs/architecture/ai-agents.md` (Guide status → implemented v1, link plan/spec), `docs/README.md` (link the plan), `memory-bank/project-state.md`, `memory-bank/log.md`

**Interfaces:**
- Consumes: Task 5 (`Guide`, `TurnResult`), Task 2/3 tools (to compute expected values in code).
- Produces:
  - Conversation file shape: `{"building": "data/dev/<dir>", "turns": [{"user": "...", "expect": {"asked": bool?, "tools": [names]?, "route_to": "<space id>"?, "step_free": bool?, "space_ids_include": [...]?, "grounded": true?}}]}`.
  - `check_turn(guide: Guide, result: TurnResult, expect: dict) -> list[str]` (in `scripts/eval_guide.py`) — failure messages; for `route_to`, recompute the route with `core.solvers.route` from the session state and compare `optimal_length_m` with `result.routes[-1]`.
  - CLI: `uv run --env-file .env python scripts/eval_guide.py [files...]` → per-turn PASS/FAIL, total cost; exit 1 on any failure.

- [ ] **Step 1: Write conversations** (dev buildings only) covering: two-room 3D printer (count → no question; route → question; answer "the one on floor 2" → route to `proc-campus-dev-001-F2-S020`); same-room printers (FACTORY → no question); unknown room "room 9.99" (not found + nearest, no invented room); follow-up "how do I get there?"; wheelchair stated once → later routes step-free without asking; "the lift is out" then a cross-floor route, then "it works again"; Turkish turn "3D yazıcı nerede?"; out-of-scope "what's the weather?" (no tool call, `asked` false).
- [ ] **Step 2: Write `tests/test_guide_conversations.py`** — offline: every file parses, building exists, `expect` keys are known; `check_turn` returns `[]` for a hand-built passing `TurnResult` and a message for a wrong `route_to` length.
- [ ] **Step 3: Run** `uv run pytest tests/test_guide_conversations.py -q` → FAIL, implement `scripts/eval_guide.py`, re-run → pass.
- [ ] **Step 4: Live run** `uv run --env-file .env python scripts/eval_guide.py` → record PASS count and cost (budget: < ~$2 per full run). Fix prompt/tool descriptions for failures (not tests); re-run once.
- [ ] **Step 5: Docs + memory bank** — commands.md: REPL + eval commands; ai-agents.md Guide row/status; project-state: Phase 3 v1 status with the live numbers; log entry; `uv run python scripts/check_links.py` → OK; `uv run pytest -q` → green.
- [ ] **Step 6: Commit** via `/ship`.
