"""agent.compute, the Guide's python tool sandbox (moved from tests/test_solver_agent.py with the module, 2026-10-26).
proc-factory-dev-004 has 50 spaces."""

from pathlib import Path

import pytest

from agent import compute
from agent.compute import namespace, run_code
from core.building_map import BuildingMap

DIRECTORY = Path(__file__).resolve().parent.parent / "data" / "dev" / "proc-factory-dev-004"


@pytest.fixture(scope="module")
def bmap() -> BuildingMap:
    return BuildingMap.load(DIRECTORY)


def test_python_tool_sees_the_building(bmap: BuildingMap) -> None:
    assert run_code("print(len(b.spaces))", namespace(bmap)) == {"output": "50\n"}


def test_python_tool_keeps_variables_and_reports_errors(bmap: BuildingMap) -> None:
    scope = namespace(bmap)
    run_code("x = 2", scope)
    assert run_code("print(x + 1)", scope)["output"] == "3\n"
    assert "ZeroDivisionError" in run_code("1 / 0", scope)["error"]


def test_python_tool_has_no_files_and_only_whitelisted_imports(bmap: BuildingMap) -> None:
    scope = namespace(bmap)
    assert "NameError" in run_code("open('/etc/hosts')", scope)["error"]
    assert "ImportError" in run_code("import os", scope)["error"]
    assert run_code("import math\nprint(math.floor(2.5))", scope)["output"] == "2\n"


def test_code_that_runs_too_long_is_stopped(bmap: BuildingMap, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(compute, "CODE_TIME_LIMIT_S", 1)
    assert "TimeoutError" in run_code("while True:\n    pass", namespace(bmap))["error"]


def test_helpers_route_and_place_use_the_canonical_core(bmap: BuildingMap) -> None:
    scope = namespace(bmap)
    output = run_code("r = route('Kitchen 1.12', 'Office 0.31')\nprint(r['optimal_length_m'])", scope)["output"]
    assert output == "92.01\n"  # warm-up answer proc-factory-dev-004-Q05
    assert run_code("print(sorted(describe(s) for s in place('toilet')))", scope)["output"].count("Toilet") == 2
