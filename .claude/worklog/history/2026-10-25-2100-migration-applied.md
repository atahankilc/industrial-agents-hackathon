# Memory bank: builder_imports migration applied, plan import in local dev

- **Author:** Claude (Opus 5.5) session with Utku · **Date:** 2026-10-25
- **Related:** supabase/migrations/20261025180000_builder_imports.sql

## Summary
Records that the `builder_imports` migration is applied (by Utku) and that local `dev` holds the plan import.

## Claims

| # | Claim | Where (files/functions) | How to verify (command or what to read) |
|---|---|---|---|
| C1 | project-state no longer says the migration is not applied; says local dev = 99e6203, not pushed | `memory-bank/project-state.md` | read; `grep -n "NOT applied" memory-bank/project-state.md` → nothing |
| C2 | Log entry records the dev fast-forward and the applied migration with the read-only check | `memory-bank/log.md` | read |
| C3 | Links resolve | — | `python3 scripts/check_links.py` → OK |

## Checks I ran
- read-only query on Supabase: `information_schema.columns` for `builder_imports` → `[('id',), ('building',), ('created_at',)]`; `pg_class.relrowsecurity` → `True`
- `git log --oneline -1 dev` → `99e6203 …`
- `python3 scripts/check_links.py` → `OK: all links resolve in 37 files`

## Knowledge base updates
- [x] `memory-bank/project-state.md`
- [x] `memory-bank/log.md`
- [ ] decisions / open questions touched: none
- [ ] docs touched: none

## Known gaps / not done
- `dev` not pushed to origin (Utku's call).

---

## Verifier report (round 1)

VERDICT: PASS
TREE: 46d12378f37555f6407a7b3705f17da260229e5f
C1–C3 MET; read-only Supabase check re-run (3 columns, RLS on); links OK; no secrets.
