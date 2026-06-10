"""test_l7_critical_manual_reset.py — ADR-0002 §13 / ADR-0001 §6.7: a CRITICAL L7 invariant
hard-stops and STAYS stopped until a manual reset.

The InvariantEnforcer (the live L7 governance gate) must: set hard_stop on a CRITICAL violation,
keep is_hard_stopped() True across subsequent checks (no auto-recovery), and clear only on an
explicit reset_hard_stop().

SRC-FIRST SUBPROCESS — under `python3 -m pytest`, `import heptagon` resolves degraded (package
collision), so this runs in a fresh process (cwd=src) where heptagon.enforcement loads cleanly.

Run:  python3 -m pytest tests/test_l7_critical_manual_reset.py -q
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "ai" / "tokenless-agent" / "src"

_DRIVER = r"""
import json, sys
sys.path.insert(0, ".")
from heptagon.enforcement import InvariantEnforcer
out = {}
e = InvariantEnforcer()
out["clean_start"] = (e.is_hard_stopped() is False)
viols = e.check_all({"safety_failed": True})
out["critical_named"] = any(v.invariant_name == "SAFETY_FILTER" for v in viols)
out["stopped_after_critical"] = (e.is_hard_stopped() is True)
e.check_all({})                       # a clean check must NOT auto-clear
out["persists_without_reset"] = (e.is_hard_stopped() is True)
e.reset_hard_stop()
out["cleared_after_reset"] = (e.is_hard_stopped() is False)
print(json.dumps(out))
"""


@pytest.fixture(scope="module")
def result():
    proc = subprocess.run([sys.executable, "-c", _DRIVER], cwd=str(SRC),
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, f"driver failed:\n{proc.stderr[-2000:]}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_critical_sets_and_names_hard_stop(result):
    assert result["clean_start"] and result["critical_named"] and result["stopped_after_critical"]


def test_hard_stop_persists_without_manual_reset(result):
    assert result["persists_without_reset"] is True, "hard stop auto-recovered without a manual reset"


def test_manual_reset_clears(result):
    assert result["cleared_after_reset"] is True
