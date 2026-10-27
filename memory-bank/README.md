---
id: memory-bank-index
summary: Protocol for the memory bank — what each file holds, ID schemes, and when/how to update.
related: [../CLAUDE.md, ../docs/README.md]
---

# Memory bank

[CLAUDE.md](../CLAUDE.md) · [Docs index](../docs/README.md)

`docs/` = **what is true** about the challenge, kit and our design. `memory-bank/` = **where we are**:
live state, decisions, unknowns, history. Small, frequently edited, always current.

| File | Holds | Update when |
|---|---|---|
| [project-state.md](project-state.md) | current phase, what works, what's next, blockers | end of every work chunk |
| [decisions.md](decisions.md) | decision records `D-###` (proposed → accepted / rejected / superseded) | a choice is made or changed |
| [open-questions.md](open-questions.md) | unknowns `Q-###` with how to resolve; resolved ones keep their answer | something is unclear / gets answered |
| [log.md](log.md) | append-only, dated session log (newest on top); the hackathon weekend is in [archive/hackathon/](../archive/hackathon/README.md) | end of every session |

## Rules

1. **IDs are permanent.** Never renumber or reuse. Next free id = highest + 1.
2. **Anchors:** every item starts with `<a id="d-001"></a>` / `<a id="q-001"></a>` so links like
   `decisions.md#d-001` are stable regardless of title edits.
3. **Link both ways.** A decision that resolves a question links `Q-###`, and the question links back to `D-###`.
   Docs that depend on an item link to it.
4. **Resolve, don't delete.** Answered questions move to *Resolved* with the answer, source and date.
   Rejected/superseded decisions stay with their status.
5. **Evidence over memory.** Each answer/decision cites its evidence (file:line, command output, organiser
   message). No evidence → it stays open.
6. **Dates are absolute** (YYYY-MM-DD HH:MM local). Hackathon weekend: Sat 2026-10-24 – Sun 2026-10-25.
7. When a decision changes a doc in `docs/architecture/`, update that doc in the same change.
