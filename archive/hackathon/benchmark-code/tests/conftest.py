"""Shared test setup: no test reads or writes the committed decision cache (llm_cache/decisions.json); tests of
the cache give it their own temporary path."""

import pytest


@pytest.fixture(autouse=True)
def no_committed_decision_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_CACHE", "off")
