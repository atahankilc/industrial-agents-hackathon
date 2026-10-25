# D-013: voice transcript rewriter in the Guide

- **Author:** Claude (Utku's session) · **Date:** 2026-10-24
- **Related:** D-013, D-003, docs/architecture/ai-agents.md#voice-path

## Summary
Implements D-013: before the Guide sees a voice turn, one small fast model call normalises the speech-to-text
transcript to the building's vocabulary; the Guide gets the rewritten and the original transcript. Any doubt keeps
the transcript as heard. Typed chat is untouched.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | `TranscriptRewriter(building, client=None, model=None)`: model from `GUIDE_REWRITER_MODEL` (default `claude-haiku-5-5`), system = RULES + `building_vocabulary(building)` with `cache_control`, `client.messages.create` with `output_config={"effort": "low", "format": json_schema {rewritten}}`; no `fallbacks` (not available on Haiku) | `agent/rewriter.py` | read; `test_rewrite_normalises_to_the_vocabulary` |
| C2 | Falls back to the transcript unchanged on `anthropic.APIError`, `stop_reason != "end_turn"`, unparsable/empty JSON, or a number in the rewrite found neither in the transcript nor in the vocabulary (`invented_numbers`) | `agent/rewriter.py:rewrite, invented_numbers` | `test_a_number_neither_heard_*`, `test_api_errors_and_empty_answers_*`, `test_invented_numbers_*` |
| C3 | RULES keep ordinal floor words as said and never pick among unnamed rooms; no "second floor → Floor 2" example | `agent/rewriter.py:RULES` | read |
| C4 | `Guide.__init__` creates a rewriter only when `self.client` is an `anthropic.Anthropic` instance and `GUIDE_REWRITER` != off (so offline/fake clients and tests never call the API) | `agent/guide.py` | `test_offline_guide_has_no_rewriter`; read |
| C5 | `Guide.reply(..., channel="voice")`: when the rewrite differs, the user message is `<rewritten>\n\n[speech transcript as heard: <original>]`, both strings go to the grounding corpus, `GuideTurn.rewritten` holds the rewrite; text turns and unchanged transcripts send the text as before (`rewritten` None) | `agent/guide.py:reply`, `GuideTurn.rewritten` | `test_voice_turn_shows_the_guide_both_transcripts`, `test_text_turns_and_unchanged_transcripts_are_left_alone` |
| C6 | Full suite passes | all | `uv run pytest -q` → 275 passed, 1 skipped |
| C7 | Live (real API): Haiku rewrites "lab two seventeen" → "Lab 2.17", "office zero oh two to meeting room three oh seven" → "Office 0.02 to Meeting room 3.07", "defib" → "defibrillator", "lift one" → "Lift 1"; keeps "the kitchen" and (after the RULES fix) "the second floor"; ~1–2 s per call. End to end with a Sonnet 5.5 low Guide: voice turn 4.7 s, one `find_route(Office 0.02 → Lab 2.17)`, 0 ungrounded | session output | stated in log; costs money to re-run |
| C8 | Docs: D-013 has an "Implemented" line; ai-agents.md voice path describes the implementation; commands.md lists `GUIDE_REWRITER` / `GUIDE_REWRITER_MODEL`; project-state + log updated (log also notes `origin/dev` is ahead of main and not merged) | `memory-bank/decisions.md`, `docs/architecture/ai-agents.md`, `docs/guides/commands.md`, `memory-bank/project-state.md`, `memory-bank/log.md` | read |

## Checks I ran
- `uv run pytest tests/test_rewriter.py -q` → 6 passed / 1 failed first (a scripted reply in my test was ungrounded, so the Guide's repair round asked for one more request); fixed the test reply → 7 passed
- `uv run pytest -q` → `275 passed, 1 skipped in 61.95s`
- live Haiku rewrites (6 + 3 phrases) and one live voice turn, outputs as in C7
- `uv run python scripts/check_links.py` → `OK: all links resolve in 28 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md` updated
- [x] `memory-bank/log.md` entry added
- [x] decisions / open questions touched: D-013 (implemented note)
- [x] docs touched: `docs/architecture/ai-agents.md`, `docs/guides/commands.md`

## Known gaps / not done
- The rewriter's token usage is kept in `TranscriptRewriter.usage`, not in `Guide.usage` (cost estimates in the REPL / live script don't include it; it is < $0.001 per call).
- Adds ~1–2 s latency to every voice turn whose transcript reaches the backend; not measured on Vercel (preview is behind Vercel Authentication).
- `origin/dev` (browser voice orb, `/chat/stream`, photo turns, Sunday route model) also edits `Guide.reply`; merging it will need the rewriter hook re-applied next to the photo handling.
- The profile safety net still reads the original transcript, not the rewrite.

## Verification rounds
- Round 1: PASS — all 8 claims MET (C7 plausibility only, no live call).

## Verification report (round 1)

VERDICT: PASS
TREE: 224494966ce6e88ee11a70c524f072b29d639c2c

C1–C8 MET. pytest 275 passed, 1 skipped (test_rewriter 7 passed); links OK in 28 files; no secrets; score.py
unchanged; no hard-coding. Notes: tests/test_rewriter.py imports `httpx2`, a transitive dependency of anthropic
2.3.0 only; TranscriptRewriter builds its own Anthropic client.
