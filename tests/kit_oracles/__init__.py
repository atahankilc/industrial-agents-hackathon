"""Test-only checkers against the kit's gold answers: the benchmark question parsers and the `Answer:` line formatter.

Moved out of backend/core/ on 2026-10-26 (the app does not use them); tests/test_navigation.py and the solver tests use them
to check the app's core against data/ train+dev answers with tests/kit_oracles/score.py."""
