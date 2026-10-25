"""Turn a Guide reply into text a voice (ElevenLabs TTS) can read naturally.

The model is already asked for a spoken style on voice turns (agent/guide.py VOICE_STYLE); this is the
deterministic safety net on top: no markdown, no list markers, no ids, no symbols a TTS voice would spell out.
It only removes or spells out characters — it never adds a number, so a grounded reply stays grounded.

`SpokenStream` speaks a voice reply while the model is still writing it: sentence by sentence, each one
grounding-checked before it is said."""

import re
from collections.abc import Callable

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


# A sentence ends at . ! ? (or …) once whitespace follows, or at a line break. "3.07" never ends one, and neither
# does a list marker on its own ("1." at the start of a line).
SENTENCE_END = re.compile(r"[.!?…]+[\"')\]]*(?=\s)|\n")
LIST_MARKER_ONLY = re.compile(r"^\s*(?:\d+[.)]|[-•*])\s*$")


def cut(text: str) -> int | None:
    """Where the first complete sentence of `text` ends, or None while it is still being written."""
    for match in SENTENCE_END.finditer(text):
        if not LIST_MARKER_ONLY.match(text[:match.end()].rsplit("\n", 1)[-1]):
            return match.end()
    return None


def sentences(text: str) -> list[str]:
    parts = []
    while (end := cut(text)) is not None:
        parts.append(text[:end])
        text = text[end:]
    return [*parts, text]


class SpokenStream:
    """A voice reply said while it is written. `feed` takes the model's text as it streams; each complete sentence
    that `grounded` accepts goes to `emit` at once, made speakable. The first sentence that is not grounded holds all
    further live speech (the Guide then repairs the reply), as does `hold` (a redo is coming). `finish` gets the final
    reply and says what of it was not said yet, so a repaired reply is never cut short and nothing is said twice."""

    def __init__(self, emit: Callable[[str], None], grounded: Callable[[str], bool]) -> None:
        self.emit = emit
        self.grounded = grounded
        self.buffer = ""
        self.said: list[str] = []  # speakable sentences already emitted, in order
        self.held = False

    def feed(self, text: str) -> None:
        self.buffer += text
        while (end := cut(self.buffer)) is not None:
            sentence, self.buffer = self.buffer[:end], self.buffer[end:]
            self.say(sentence)

    def end_block(self) -> None:
        """A text block ended: what is left in it is a sentence too."""
        sentence, self.buffer = self.buffer, ""
        self.say(sentence)

    def say(self, sentence: str) -> None:
        text = speakable(sentence)
        if self.held or not text:
            return
        if not self.grounded(sentence):
            self.held = True
            return
        self.said.append(text)
        self.emit(text)

    def hold(self) -> None:
        self.held = True
        self.buffer = ""

    def finish(self, reply: str) -> None:
        self.buffer = ""
        already = list(self.said)
        for sentence in sentences(reply):
            text = speakable(sentence)
            if not text:
                continue
            if text in already:
                already.remove(text)
                continue
            self.said.append(text)
            self.emit(text)
