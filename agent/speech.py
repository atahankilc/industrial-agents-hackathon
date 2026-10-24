"""Turn a Guide reply into text a voice (ElevenLabs TTS) can read naturally.

The model is already asked for a spoken style on voice turns (agent/guide.py VOICE_STYLE); this is the
deterministic safety net on top: no markdown, no list markers, no ids, no symbols a TTS voice would spell out.
It only removes or spells out characters — it never adds a number, so a grounded reply stays grounded."""

import re

ID_IN_BRACKETS = re.compile(r"\s*\[[A-Za-z0-9]+(?:-[A-Za-z0-9]+){2,}\]")
BARE_ID = re.compile(r"\s*\(?\b[A-Za-z0-9]+(?:-[A-Za-z0-9]+){3,}\b\)?")
MARKDOWN = [
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),
    (re.compile(r"(?<!\w)\*(.+?)\*(?!\w)"), r"\1"),
    (re.compile(r"`([^`]*)`"), r"\1"),
    (re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE), ""),
]
LIST_LINE = re.compile(r"^\s*(?:\d+[.)]|[-•*])\s+", re.MULTILINE)
SYMBOLS = [
    (re.compile(r"\s*→\s*"), " to "),
    (re.compile(r"\s*->\s*"), " to "),
    (re.compile(r"≥\s*"), "at least "),
    (re.compile(r"≤\s*"), "at most "),
    (re.compile(r"\s*&\s*"), " and "),
    (re.compile(r"(\d)\s*m²|(\d)\s*m2\b"), lambda match: f"{match.group(1) or match.group(2)} square metres"),
    (re.compile(r"(\d)\s*m\b"), r"\1 metres"),
    (re.compile(r"(\d)\s*cm\b"), r"\1 centimetres"),
    (re.compile(r"(\d)\s*km\b"), r"\1 kilometres"),
]


def speakable(text: str) -> str:
    """Plain sentences for speech: list items become sentences, ids and markup disappear."""
    text = ID_IN_BRACKETS.sub("", text)
    text = BARE_ID.sub("", text)
    for pattern, replacement in MARKDOWN:
        text = pattern.sub(replacement, text)
    sentences = []
    for line in text.splitlines():
        line = LIST_LINE.sub("", line).strip()
        if not line:
            continue
        if line[-1] not in ".!?:":
            line += "."
        sentences.append(line)
    text = " ".join(sentences).replace(":.", ":")
    for pattern, replacement in SYMBOLS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()
