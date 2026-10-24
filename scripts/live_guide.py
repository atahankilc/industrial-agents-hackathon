"""Run the tricky-user conversation against the real Claude API and report quality, latency and cost.

  uv run --env-file .env python scripts/live_guide.py [--model claude-sonnet-5-5] [--effort low] [--out FILE]

Same user turns as tests/test_guide.py, but the model decides everything. Prints each reply with the tools it
called, flags (ungrounded numbers/ids, refused same-turn applies), and per-turn tokens, cache reads, seconds and
estimated dollars. The transcript is saved as JSON under agent_output/live_guide/ (git-ignored). Costs real money
(~$0.1–1 per run)."""

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.guide import DEFAULT_MODEL, Guide, Usage, make_client  # noqa: E402
from agent.tools import BuildingSession  # noqa: E402

# $ per million tokens: input, output, cache read, cache write (5-minute TTL = 1.25 × input). From the claude-api
# skill's model table (cached 2026-10-06); estimates only.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}
TURNS = [
    "Where's the printer?",
    "I'm in the main lobby. Oh, and I use a wheelchair.",
    "Take me to the meeting room.",
    "3.07 please",
    "The lift is broken!",
    "Yes, go ahead.",
    "And if the other lift breaks too, which rooms can I still not reach?",
]


def cost(usage: Usage, model: str) -> float:
    price_in, price_out, price_read, price_write = PRICES.get(model, PRICES[DEFAULT_MODEL])
    return (usage.input_tokens * price_in + usage.output_tokens * price_out
            + usage.cache_read_input_tokens * price_read + usage.cache_creation_input_tokens * price_write) / 1e6


def delta(after: Usage, before: Usage) -> Usage:
    return Usage(**{key: getattr(after, key) - getattr(before, key) for key in asdict(after)})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--building", default="data/train/proc-campus-train-000")
    parser.add_argument("--model", default=None)
    parser.add_argument("--effort", default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    guide = Guide(BuildingSession.load(ROOT / args.building), client=make_client(), model=args.model,
                  effort=args.effort)
    print(f"model {guide.model} · effort {guide.effort} · building {args.building}\n")
    transcript, total_seconds = [], 0.0
    for text in TURNS:
        before, started = Usage(**asdict(guide.usage)), time.perf_counter()
        turn = guide.reply(text)
        seconds = time.perf_counter() - started
        total_seconds += seconds
        used = delta(guide.usage, before)
        refused = [c for c in turn.tool_calls if c["name"] == "apply_change" and "error" in c["result"]]
        print(f"USER  {text}")
        print("TOOLS " + ", ".join(f"{c['name']}({json.dumps(c['input'], ensure_ascii=False)})"
                                   for c in turn.tool_calls))
        print("GUIDE " + turn.text.replace("\n", "\n      "))
        print(f"      [{seconds:.1f}s · {used.requests} req · in {used.input_tokens} · out {used.output_tokens} · "
              f"cache read {used.cache_read_input_tokens} · write {used.cache_creation_input_tokens} · "
              f"${cost(used, guide.model):.3f}" + (f" · UNGROUNDED {turn.ungrounded}" if turn.ungrounded else "")
              + (" · same-turn apply refused" if refused else "") + f" · stop {turn.stop_reason}]\n")
        transcript.append({"user": text, "reply": turn.text, "tool_calls": turn.tool_calls, "events": turn.events,
                           "ungrounded": turn.ungrounded, "stop_reason": turn.stop_reason,
                           "seconds": round(seconds, 2), "usage": asdict(used)})
    session = guide.session
    print(f"TOTAL {total_seconds:.1f}s · {guide.usage.requests} requests · ${cost(guide.usage, guide.model):.3f} · "
          f"profile {session.profile.describe()} · applied {[c.summary for c in session.applied]} · "
          f"pending {[c.summary for c in session.pending.values()]}")
    out = args.out or ROOT / "agent_output" / "live_guide" / f"{guide.model}-{guide.effort}-{int(time.time())}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"model": guide.model, "effort": guide.effort, "building": args.building,
                               "usage": asdict(guide.usage), "cost_usd": round(cost(guide.usage, guide.model), 4),
                               "turns": transcript}, ensure_ascii=False, indent=1, default=str))
    print(f"saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
