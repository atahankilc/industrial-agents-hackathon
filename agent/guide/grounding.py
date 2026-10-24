"""Grounding check: a reply may only state numbers that some tool result (or the building overview) contains.

Numbers with a decimal point or comma, counts and refs are checked; free-text names are not. A value counts as
grounded if it equals a tool value rounded to 0, 1 or 2 decimals, and the length of any list in a tool result
of dicts or strings (so "I found 2 options" passes; coordinate lists do not count). Plain JSON in, plain values out: no dependency on the building model."""

import math
import re
from decimal import ROUND_HALF_UP, Decimal

NUMBER = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*(?![\w])")
NO_ANSWER = "I couldn't find an answer to that in this building."


DECIMAL = re.compile(r"\d+\.\d+")
THOUSANDS = re.compile(r"\d{1,3}(?:[.,]\d{3})+")
TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
MARKER_PREFIX = re.compile(r"\s*(?:[-*\u2022]\s*)?(?:\*\*)?(?:step\s+)?", re.I)
MARKER_SUFFIX = re.compile(r"(?:\*\*)?[.):]")


def _norm(token: str) -> str:
    if THOUSANDS.fullmatch(token):
        return re.sub(r"[.,]", "", token)
    token = token.replace(",", ".")
    if DECIMAL.fullmatch(token):
        token = token.rstrip("0").rstrip(".")
    return token


def _rounded(value: float) -> set[str]:
    if not math.isfinite(value):
        return set()
    exact = Decimal(repr(value))
    return {_norm(f"{exact.quantize(Decimal(1).scaleb(-d), ROUND_HALF_UP):f}") for d in (0, 1, 2)}


def _walk(value: object, out: set[str]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, str):
        out.update(_norm(t) for t in NUMBER.findall(value))
    elif isinstance(value, float):
        out |= _rounded(value)
        out.add(_norm(repr(value)))
    elif isinstance(value, int):
        out.add(str(value))
    elif isinstance(value, dict):
        for k, v in value.items():
            _walk(k, out)
            _walk(v, out)
    elif isinstance(value, (list, tuple)):
        if value and all(isinstance(v, (dict, str)) for v in value):
            out.add(str(len(value)))
        for v in value:
            _walk(v, out)


def grounded_tokens(sources: list[dict | str]) -> set[str]:
    out: set[str] = set()
    for source in sources:
        _walk(source, out)
    return out


def _is_marker(text: str, m: re.Match) -> bool:
    line_start = text.rfind("\n", 0, m.start()) + 1
    return (len(m.group()) <= 2 and bool(MARKER_PREFIX.fullmatch(text[line_start:m.start()]))
            and bool(MARKER_SUFFIX.match(text, m.end())))


def ungrounded(text: str, grounded: set[str]) -> list[str]:
    times = [t.span() for t in TIME.finditer(text)]
    bad = []
    for m in NUMBER.finditer(text):
        if any(s <= m.start() and m.end() <= e for s, e in times) or _is_marker(text, m):
            continue
        if _norm(m.group()) not in grounded:
            bad.append(m.group().replace(",", "."))
    return bad


def fallback_text(results: list[dict]) -> str:
    lines = []
    for r in results:
        if not isinstance(r, dict):
            continue
        if r.get("summary"):
            lines.append(r["summary"])
        steps = (r.get("result") or {}).get("steps") if isinstance(r.get("result"), dict) else None
        lines.extend(f"{i}. {s}" for i, s in enumerate(steps or [], 1))
    return "\n".join(lines) or NO_ANSWER
