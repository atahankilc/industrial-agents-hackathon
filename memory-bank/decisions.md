---
id: decisions
summary: Decision log (D-###). Status proposed | accepted | rejected | superseded. Never renumber.
related: [open-questions.md, project-state.md, ../docs/architecture/overview.md]
---

# Decisions

[Memory bank](README.md) · Next free id: **D-016**

Template:

```markdown
<a id="d-000"></a>
### D-000 — Title
- **Status:** proposed | accepted | rejected | superseded by D-xxx · **Date:** YYYY-MM-DD · **By:** who
- **Context:** why this came up (link Q-### if it resolves one)
- **Decision:** what we do
- **Consequences:** what this implies / rules out
- **Evidence:** files, commands, messages
```

---

<a id="d-001"></a>
### D-001 — Knowledge structure: CLAUDE.md + docs/ + memory-bank/
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Atahan (request), set up by Claude
- **Context:** Several agents/sessions will work in parallel during a short hackathon; they must share facts
  without re-deriving or hallucinating them.
- **Decision:** `CLAUDE.md` is the entry point; `docs/` holds verified descriptive knowledge (challenge, kit)
  and our design (architecture) with front matter `sources`/`related`; `memory-bank/` holds live state,
  decisions, open questions and a log. All cross-linked with stable anchors.
- **Consequences:** Every session follows the protocol in [CLAUDE.md](../CLAUDE.md#session-protocol-do-this-every-time).
- **Evidence:** files created 2026-10-24 (CLAUDE.md, docs/, memory-bank/).

<a id="d-002"></a>
### D-002 — Build our core on the starter `BuildingMap` route model
- **Status:** proposed · **Date:** 2026-10-24
- **Context:** Expected route lengths come from a specific model; the starter code implements it exactly
  (README §3, `building_map.py:179-212`).
- **Decision:** Reuse/extend `BuildingMap` (add width filter, reachability, geometry) instead of rewriting.
- **Consequences:** Must keep anchor = `representative_point()`, MultiGraph, stair/lift costs unchanged.
- **Evidence:** [route-model.md](../docs/kit/route-model.md). To accept: oracle run on dev matches.
  2026-10-24: acceptance criterion met — all solvers build on `core.building_map` and match 655/655 train+dev
  answers (`tests/test_solvers.py`). Status left for the team to flip.

<a id="d-003"></a>
### D-003 — LLM for language, code for facts; deterministic `Answer:` line
- **Status:** proposed · **Date:** 2026-10-24
- **Context:** Scorer only reads the last `Answer:` line and is strict (exactly one number, ordering of rooms).
- **Decision:** Solvers compute answers; a formatter writes the final `Answer:` line from structured results.
  The LLM may phrase explanations and parse intent, never compute numbers.
- **Consequences:** Needs a reliable question → (kind, params) step ([Q-008](open-questions.md#q-008)).
- **Evidence:** [scoring.md](../docs/challenge/scoring.md#how-a-reply-is-parsed).

<a id="d-004"></a>
### D-004 — Build at the repo root; archive the organiser kit
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Atahan
- **Context:** Resolves [Q-009](open-questions.md#q-009).
- **Decision:** Root repo is where we build. Extracted to root: `data/` (moved), `benchmark/` (moved, official
  scorer — never edit `score.py`), `core/building_map.py` (copied from starter), `ATTRIBUTION.md`,
  `.env.example`. Root `pyproject.toml` (uv, Python ≥3.12). Everything else → `archive/initial-repo/`.
- **Consequences:** Run everything from the root. Starter agent still runnable via
  `PYTHONPATH=archive/initial-repo`. See [archive/README.md](../archive/README.md).
- **Evidence:** after the move, oracle on dev 369/369; `core.building_map` reproduces all 120 dev warm-up routes
  to < 1 cm (2026-10-24).

<a id="d-005"></a>
### D-005 — Commit the dataset to git
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Atahan
- **Context:** Resolves [Q-011](open-questions.md#q-011). The upstream kit repo is public, so redistribution is fine;
  ODbL attribution kept via `ATTRIBUTION.md` at root.
- **Decision:** `data/` (~209 MB) is committed as normal files.
- **Consequences:** Clone size ~200 MB+; keep `ATTRIBUTION.md`; the repo stays ODbL-compliant for OSM-derived parts.

<a id="d-006"></a>
### D-006 — Cloud stack: FastAPI on Vercel's Python runtime + Supabase + own React app (Vercel) + ElevenLabs Custom LLM
- **Status:** accepted (zero-cost revision) · **Date:** 2026-10-24 · **By:** Atahan · **Waiting for:** account sign-ups (Vercel, Supabase)
- **Revision 2026-10-24 (zero cost):** Atahan wants to pay nothing → backend moves from Railway to **Vercel's Python
  runtime** in the same Vercel project as the frontend; fallback Render Free / Modal. See
  [stack-options.md §9](../docs/research/stack-options.md#9-zero-cost-variant-added-2026-10-24).
- **Context:** "Cloud on day one", realtime collaboration, voice. Resolves [Q-007](open-questions.md#q-007).
- **Decision:** Python core + Claude agents in FastAPI on Vercel's Python runtime, in the same Vercel project as the
  frontend (fallback Render Free / Modal); Supabase for Postgres (buildings JSON +
  `building_edits` event log), Realtime broadcast/presence, Auth, Storage; Vite/React/TS/Tailwind/shadcn +
  react-three-fiber in `frontend/` on Vercel; ElevenLabs Agent with Custom LLM → our OpenAI-compatible endpoint;
  GitHub Actions CI. Lovable only for throw-away mock-ups (no monorepo-subfolder sync).
- **Consequences:** backend is the only writer of edits; one agent brain for text + voice.
- **Evidence:** [stack-options.md](../docs/research/stack-options.md), [elevenlabs.md](../docs/research/elevenlabs.md),
  [overview.md](../docs/architecture/overview.md).

<a id="d-007"></a>
### D-007 — Benchmark parsing: deterministic regex templates first, LLM fallback for unknown wording
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Atahan (both, configurable; Claude decides default)
- **Modes:** `PARSER_MODE` = `hybrid` (default) | `regex` | `llm` | `crosscheck` — `agent/parsing.py`;
  LLM parser `agent/llm_parser.py` (structured outputs, Opus 5.5, server-side fallback). Rationale:
  [ai-agents.md](../docs/architecture/ai-agents.md#parser-modes).
- **Context:** [Q-008](open-questions.md#q-008).
- **Decision:** `core/question_parser.py` (one regex per template + name resolver) is primary. If no template
  matches, Claude with a strict tool schema returns `{kind, raw slot text}` — never ids — and the same resolver
  maps them. Ambiguous names: solver runs every candidate and answers if they agree.
- **Evidence:** train+dev 655/655 params match `inputs`; test 145/145 parse, 0 ambiguous (`uv run pytest`,
  2026-10-24); fallback ≈ $0.007/question. [question-parsing.md](../docs/research/question-parsing.md).

<a id="d-008"></a>
### D-008 — Every commit is verified by an independent agent
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Atahan
- **Context:** Many agents write code in parallel; we need to know that what is claimed is what is implemented.
- **Decision:** Worklog of claims (`.claude/worklog/PENDING.md`) → `/ship` → fresh `commit-verifier` agent →
  `commit-fixer` loop (≤ 3 rounds) on FAIL → commit only with a PASS stamp of the staged tree; enforced by a
  PreToolUse hook. Entries + reports archived in `.claude/worklog/history/`.
- **Consequences:** direct `git commit` from Claude is blocked; each commit costs one verifier run per round.
- **Evidence:** hook pipe-tested 2026-10-24 (blocks: no stamp, stale stamp, `--amend`, `-am`, add+commit
  one-liner; allows a fresh stamp); stamp script refuses FAIL and unstaged entries.
  [dev-workflow.md](../docs/guides/dev-workflow.md).

<a id="d-009"></a>
### D-009 — Licensing: MIT for our code; third-party material keeps its own terms
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Atahan (MIT confirmed)
- **Context:** Repo is public. `ATTRIBUTION.md`: data is CC BY 4.0 (Swiss Dwellings, ResPlan), ODbL 1.0 (OSM),
  CC0 (procedural) — all allow redistribution with attribution; ODbL is share-alike. Upstream kit repo
  (`Synera-GmbH/industrial-agents-hackathon-2026`) is public but has **no licence** (GitHub API `license: null`),
  so kit *code* (`benchmark/`, `archive/initial-repo/`, kit parts of `core/building_map.py`) has no explicit grant.
- **Decision:** `LICENSE` (MIT, our code only), `NOTICE.md` (what is third-party, under which terms, removal on
  request), `data/README.md` (per-source licences + obligations), keep `ATTRIBUTION.md` at root. Ask organisers to
  confirm redistribution of kit code ([Q-013](open-questions.md#q-013)).
- **Consequences:** screenshots / video showing OSM buildings must credit "© OpenStreetMap contributors";
  modified OSM buildings we publish stay ODbL.

<a id="d-010"></a>
### D-010 — Guide guardrails live in code: same-turn apply refused, grounding check with one repair round
- **Status:** proposed · **Date:** 2026-10-24 · **By:** Claude (Guide session)
- **Context:** The behaviour contract ([ai-agents.md](../docs/architecture/ai-agents.md#building-guide--behaviour-contract))
  needs propose → confirm → apply and D-003 ("every number and id from a tool"). A prompt alone can't guarantee
  either, and the brief scores "shows what it understood before it changes a plan".
- **Decision:** `agent/guide.py` refuses `apply_change` for a change proposed in the same user turn, and checks
  every reply: numbers/ids must appear in a tool result, the overview or the user's words (rounding allowed);
  one repair round, then report leftovers in `GuideTurn.ungrounded` instead of blocking the reply.
- **Consequences:** one extra request when the model invents a number; a confirmation always costs one user turn.
  Derived numbers (differences, sums) must come from tools → `compare_routes` and `extra_m` exist for that.
- **Evidence:** `tests/test_guide.py` (same-turn apply refused; invented "437 m" repaired; leftovers reported).

<a id="d-011"></a>
### D-011 — Monochrome visual language for the app (black / white, light + dark)
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Atahan ("simplistic look, black or white colour scheme for
  light and dark mode, point clouds with good animations")
- **Context:** [visualization.md](../docs/product/visualization.md#visual-language) had a colour-coded scheme
  (cyan walls, magenta cores, amber doors, gold highlight).
- **Decision:** the app is monochrome: white on black (dark), black on white (light), system default + toggle.
  Point kinds and states are told apart by density, alpha, size and motion (flow, flicker, float, sink), never hue.
- **Consequences:** additive glow in dark mode, normal blending with crisp dots in light mode; the prototype keeps
  its colours as a reference only.

<a id="d-012"></a>
### D-012 — Duplicate room names: core returns candidates, the agent asks; the benchmark runs them all
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Utku
- **Context:** Some buildings repeat a name on the same floor (three "Büro" on the ground floor, OSM rooms
  duplicated with the same ref). The question text then cannot say which room is meant: all 12 train+dev misses
  (2 benchmark, 10 warm-up) are such texts. The floor is usually already in the text, so it does not help.
- **Decision:** `core/` stays deterministic and never guesses: the parser returns every candidate
  (`ParsedQuestion.alternatives`). **Guide (chat):** run the solver for each candidate; if the answers agree, answer;
  if they differ, ask one short question naming what tells them apart — ref ("0.10, 0.11 or 0.12?"), else size,
  neighbour or position, or highlight them on the plan. **Benchmark (no user):** as in [D-007](#d-007), run every
  candidate and answer if they agree; otherwise answer with the first and say so in the reply.
- **Consequences:** benchmark misses on such texts are accepted; the Guide needs a candidate-describing tool
  (ref, floor, area, neighbours). Contract: [ai-agents.md](../docs/architecture/ai-agents.md#building-guide--behaviour-contract).

<a id="d-013"></a>
### D-013 — Voice input gets a transcript rewriter before the Guide (Phase 4)
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Utku
- **Context:** Speech-to-text transcripts are messy ("Lab two twenty", filler words, misheard machine names). For
  typed input we rely on the Guide model plus code-side name resolution and add no rewriter (extra latency/cost,
  risk of dropping nuance). The Guide's grounding check covers the model's *output*, not the user's input.
- **Decision:** In the voice path (ElevenLabs STT → Guide), add a transcript rewriter step that only normalises the
  transcript — names and numbers to the building's vocabulary (e.g. "Lab two twenty" → "Lab 2.20"), no
  interpretation, no answering. The building's room/asset names are its vocabulary (same list as the Scribe
  keyterms). The Guide receives both the rewritten and the original transcript so a dropped nuance stays visible.
- **Consequences:** One extra (small, fast) model call per voice turn; text chat stays rewriter-free. Must be
  measured on voice latency in Phase 4.
- **Implemented (2026-10-24):** `agent/rewriter.py` (`claude-haiku-5-5`, effort low, JSON schema output, vocabulary =
  `building_vocabulary` cached as system prompt), hooked into `Guide.reply(..., channel="voice")`. Live: ~1–2 s and
  < $0.001 per voice turn. Falls back to the transcript as heard on API error, refusal, empty answer or a number
  found neither in the transcript nor in the building; ordinal floor words are kept as said.
- **Evidence:** conversation 2026-10-24 (branch `1-agentic-yarag`); voice path in
  [ai-agents.md](../docs/architecture/ai-agents.md#voice-path).

<a id="d-014"></a>
### D-014 — One route model: the kit 1.1.0 graph, ported verbatim into core
- **Status:** accepted · **Date:** 2026-10-24 · **By:** Utku
- **Context:** Kit 1.1.0 recomputed every expected answer (train/dev/test) with the judges' rule — door to door
  15 cm off the walls, 30 cm door landings, stairs 2 m per metre climbed, a lift ride 15 m + 1 m per metre, no
  outdoor link ([Q-014](open-questions.md#q-014)). Our `kit` model no longer matched (errand 10/93, what_if_door
  0/4); our own `geodesic` approximation was within 1 m but exact on only 3 of 161 dev routes.
- **Decision:** Copy the 1.1.0 starter's geometry helpers and `BuildingMap.graph` into `core/building_map.py`
  unchanged (same node/edge order → same Dijkstra tie-breaks) and make it the only route model. `expand` /
  `path_parts` give the 1.1.0 `space_path` / `element_path`. `outside` stays available as a start/end node only.
  Remove `core/geodesic.py` and `scripts/compare_route_models.py`; keep `model=` and `GEODESIC` as aliases so
  callers (Guide, branches) don't break. The bay / forklift rules stay ours (organiser note, not in the answers).
- **Consequences:** Train+dev warm-up routes 1,338/1,338 exact (paths too), solvers 655/655, dev benchmark
  138/138. First graph build is slow on huge OSM corridors (~25 s on osm-way360544293); walks are cached by geometry.
  One gold value disagrees with the starter itself (resplan-12462, 10 cm); validators accept starter-equal lengths.
- **Evidence:** [route-model.md](../docs/kit/route-model.md), `tests/test_routes.py`, `scripts/validate_warmup.py`,
  `scripts/validate_solvers.py`.

<a id="d-015"></a>
### D-015 — Sunday agentic layers: route specs on the canonical core, a solver agent, a committed decision cache
- **Status:** proposed · **Date:** 2026-10-25 · **By:** Utku (asked for "the most advanced agent for this task";
  P1 of the Sunday plan, branch `4-sunday-agent`)
- **Context:** A probe of 14 Sunday-style questions on a factory dev building: `regex` answered 1, `hybrid` 11 without
  an error, but only about 7 correctly — the LLM parser had to squeeze every question into one of 15 templates, so
  combined constraints (closure + step-free), item destinations, forklift and new kinds became near-miss kinds
  (silently wrong). The canonical `core.navigation` already handles closures of any element, item endpoints and
  route rules, and reproduces every warm-up route answer. The organisers may re-run our command, possibly without an
  API key (Utku's question).
- **Decision:** (1) the LLM schema gets one general `route` spec (places = rooms, room types or items, nearest
  taken; stops; step_free, forklift, min_width, closures) plus `asks_for`; a spec that is exactly a warm-up kind
  keeps it, anything richer is `route_query` (`core/route_query.py` on `core.navigation`); (2) kind `other`, an
  `asks_for` the kind cannot answer, unresolvable slots or a solver error go to a solver agent
  (`agent/solver_agent.py`: Python sandbox over the building + `submit_answer`, 2 runs + tie-break, Answer line by
  code); (3) every model decision is stored in `llm_cache/decisions.json` (committed) and replayed first, so re-runs
  reproduce `answers.json` without a key. Regex templates stay first and unchanged.
- **Consequences:** test-set and dev answers unchanged (all template wording); Sunday questions in unseen wording or
  new kinds get answers; the cache file must be committed with `SUBMISSION/answers.json`. Model code runs locally in a
  restricted `exec` (accident guard, not a security boundary). Tests never touch the committed cache
  (`tests/conftest.py`).
- **Evidence:** `tests/test_route_query.py`, `tests/test_llm_route_spec.py`, `tests/test_solver_agent.py`,
  `tests/test_answer_agentic.py`, `scripts/eval_sunday_probe.py` (`tests/sunday_probe/`),
  [ai-agents.md](../docs/architecture/ai-agents.md#sunday-layers-route-specs-solver-agent-decision-cache-2026-10-25).
