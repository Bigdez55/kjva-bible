"""test_l5_l7_failclosed.py — the L5→L7 governance coupling must FAIL CLOSED,
and the deterministic-replay record must carry real inputs.

Background (advisor-found, this session): L5 (ResponseVerifier) is advisory, L7
(InvariantEnforcer) is the hard gate. They are coupled through `verdict`: if
`verify()` *raises*, `verdict` stays None, which the L7 ctx previously read as
`passed=True` / `safety_failed=False` / `total_errors=0` — i.e. a CRASHED verifier
silently handed the hard gate a clean bill (fail-OPEN). The fix propagates an L5
crash into the L7 ctx as `safety_failed=True` / not-passed.

IMPORT ISOLATION (load-bearing). The repo has TWO `heptagon` packages: the agent-side
cognitive-control package `ai/tokenless-agent/src/heptagon/` (owns state_machine,
verification, enforcement, determinant_record) and a ROOT governance package
`heptagon/`. Under `python3 -m pytest`, the repo root is on sys.path[0], so a bare
`import heptagon` resolves to ROOT — which lacks those submodules — and the agent
silently degrades (verifier/enforcer/determinant unavailable). Production runs the
server from `src/`, where agent-side wins. To assert PRODUCTION behavior faithfully
(and avoid contaminating the shared pytest sys.path), these tests exercise the agent
in a clean subprocess whose cwd is `src/` — exactly the production resolution order.

Run:  python3 -m pytest tests/test_l5_l7_failclosed.py -q
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "ai" / "tokenless-agent" / "src"

# Driver executed in a clean interpreter with cwd=SRC (agent-side heptagon wins,
# exactly as in production). Emits a single JSON verdict on stdout.
_DRIVER = r"""
import json, sys
sys.path.insert(0, ".")
from agent import TokenlessAgentWithHeptagon, AgentConfig, HeptagonLayer

out = {}

# --- Scenario A: crashed L5 verifier must fail CLOSED into the L7 hard gate -------
a = TokenlessAgentWithHeptagon(AgentConfig(), HeptagonLayer.build())
out["wired"] = (a.heptagon.verifier is not None and a.heptagon.enforcer is not None)
if out["wired"]:
    def _boom(*_a, **_k):
        raise RuntimeError("verifier exploded")
    a.heptagon.verifier.verify = _boom
    cap = {}
    _orig = a.heptagon.enforcer.check_all
    def _spy(ctx, *p, **k):
        cap.clear(); cap.update(ctx); return _orig(ctx, *p, **k)
    a.heptagon.enforcer.check_all = _spy
    a.chat("s", "tell me something")
    out["crash_safety_failed"] = cap.get("safety_failed")
    out["crash_total_errors"] = cap.get("total_errors")

# --- Scenario B: healthy turn must NOT spuriously trip safety_failed --------------
b = TokenlessAgentWithHeptagon(AgentConfig(), HeptagonLayer.build())
if b.heptagon.enforcer is not None:
    cap2 = {}
    _o2 = b.heptagon.enforcer.check_all
    def _spy2(ctx, *p, **k):
        cap2.clear(); cap2.update(ctx); return _o2(ctx, *p, **k)
    b.heptagon.enforcer.check_all = _spy2
    b.chat("s", "Psalm 105:1")
    out["healthy_safety_failed"] = cap2.get("safety_failed")

# --- Scenario C: DeterminantProbabilityRecord carries REAL replay inputs ----------
c = TokenlessAgentWithHeptagon(AgentConfig(), HeptagonLayer.build())
c.chat("s", "Psalm 105:1")
dpr = getattr(c, "_last_determinant", None)
out["determinant_emitted"] = dpr is not None
if dpr is not None:
    out["det_inputs"] = dpr.deterministic_inputs
    out["det_replayable"] = dpr.replayable
mat = getattr(c, "_last_materialization", None)
out["materialization_emitted"] = mat is not None

print(json.dumps(out))
"""


@pytest.fixture(scope="module")
def result():
    proc = subprocess.run(
        [sys.executable, "-c", _DRIVER],
        cwd=str(SRC), capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"driver failed:\n{proc.stderr}"
    line = proc.stdout.strip().splitlines()[-1]
    return json.loads(line)


def test_cognitive_modules_wired_in_production_resolution(result):
    """Sanity: with src-first resolution (production), L5/L7 are actually wired."""
    assert result["wired"] is True, "verifier/enforcer not wired even with agent-side heptagon"


def test_crashed_L5_verifier_fails_closed_into_L7(result):
    """A verifier that raises must NOT let the L7 hard gate see safety_failed=False."""
    assert result.get("crash_safety_failed") is True, (
        "FAIL-OPEN: crashed L5 verifier handed L7 safety_failed=False")
    assert (result.get("crash_total_errors") or 0) >= 1, (
        "FAIL-OPEN: crashed L5 verifier handed L7 total_errors=0")


def test_healthy_L5_does_not_force_safety_failed(result):
    """Control: a normal grounded turn does NOT spuriously trip the safety flag."""
    assert result.get("healthy_safety_failed") is False, (
        "healthy turn must not spuriously set safety_failed")


def test_determinant_inputs_are_populated(result):
    """DeterminantProbabilityRecord must carry REAL replay inputs, not empty defaults."""
    assert result["determinant_emitted"] is True, "no DeterminantProbabilityRecord emitted"
    di = result["det_inputs"]
    assert di["policy_snapshot_hash"].startswith("sha256:"), "policy snapshot empty"
    assert di["model_snapshot_hash"].startswith("sha256:"), "model snapshot empty"
    assert di["route_policy_hash"].startswith("sha256:"), "route policy snapshot empty"
    assert di["budget_state_hash"].startswith("sha256:"), "budget snapshot empty"
    assert result["det_replayable"] is True


def test_materialization_emitted(result):
    """The response materialization record is emitted on the real path."""
    assert result["materialization_emitted"] is True, "no MaterializationRecord emitted"
