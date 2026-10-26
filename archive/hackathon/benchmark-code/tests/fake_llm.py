"""A fake Anthropic client for offline tests: returns queued replies in order (was in tests/test_parsing_modes.py)."""

from types import SimpleNamespace


def response(text: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop_reason, usage=usage)


class FakeClient:
    """Returns the queued replies in order; records how many requests were made."""

    def __init__(self, *replies: SimpleNamespace) -> None:
        self.replies = list(replies)
        self.calls = 0
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **_: object) -> SimpleNamespace:
        self.calls += 1
        return self.replies.pop(0)
