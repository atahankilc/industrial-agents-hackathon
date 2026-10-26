---
id: guide-glossary
summary: Shared vocabulary for docs, code and conversation. Use these terms consistently.
sources: [../kit/data-format.md, ../kit/route-model.md, ../kit/questions.md]
related: [../kit/data-format.md, ../kit/route-model.md]
---

# Glossary

[Docs index](../README.md)

| Term | Meaning | See |
|---|---|---|
| **Space** | any polygon in `spaces`: room, corridor, stair, lift, hall, outdoor (`type`) | [data-format](../kit/data-format.md#buildingjson) |
| **Room** (in questions) | reachability / what-if counts: `type == room`; shared walls: `type` ∈ {room, hall} (verified 2026-10-24) | [Q-003](../../memory-bank/open-questions.md#q-003) |
| **`type` vs `room_type`** | coarse class (6 values) vs fine class (~31 values) | [data-format](../kit/data-format.md#room-types) |
| **Ref** | room number string, e.g. `"2.03"`; unique per building except some OSM | [data-format](../kit/data-format.md#field-notes) |
| **Opening** | door / opening (no leaf) / entrance joining exactly two spaces (or one + `"outside"`) | [data-format](../kit/data-format.md#buildingjson) |
| **Entrance** | opening with `"outside"` in `space_ids` | [route-model](../kit/route-model.md#graph) |
| **Vertical connector** | stairs or lift with one stop space per floor | [data-format](../kit/data-format.md#field-notes) |
| **Anchor** | `representative_point()` of a space polygon; the routing node position | [route-model](../kit/route-model.md#graph) |
| **Centroid** | polygon centroid; used for `straight_line_3d` only | [questions](../kit/questions.md#precise-definitions) |
| **Route model** | the exact graph + costs behind expected lengths | [route-model](../kit/route-model.md) |
| **Step-free** | excludes every element with `step_free: false` | [route-model](../kit/route-model.md#constraints) |
| **Closure** | element removed from the graph (lift, stair, door, room) | [route-model](../kit/route-model.md#constraints) |
| **Synthetic** | added by the dataset, not in the source | [data-format](../kit/data-format.md#conventions) |
| **Warm-up questions** | `questions_basic.jsonl`, `-Q##`, unscored | [questions](../kit/questions.md#warm-up-questions) |
| **Benchmark questions** | `questions.jsonl`, `-H##`, scored | [questions](../kit/questions.md#benchmark-questions) |
| **Committed answer** | last `Answer:` line in a reply — the only part scored | [scoring](../../archive/hackathon/docs/challenge/scoring.md#how-a-reply-is-parsed) |
| **Sunday building** | unseen building released before code freeze | [scoring](../../archive/hackathon/docs/challenge/scoring.md#sunday-benchmark) |
| **Solver** | deterministic function answering one question kind | [solver-plan](../architecture/solver-plan.md) |
| **Oracle** | starter evaluator mode answering with tools directly | [starter-agent](../../archive/hackathon/docs/kit/starter-agent.md#evaluation) |
