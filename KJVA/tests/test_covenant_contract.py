"""test_covenant_contract.py — lock the CovenantEnforcer API the api.py caller relies on.

Regression guard for ADR-S49-04: the prior caller used a nonexistent .evaluate()/
HARD_STOP/.reason and silently bypassed every block. This test pins the real contract
(enforce → EnforcementResult{.is_blocked, .summary()}) so it can't drift again.
"""
from __future__ import annotations

import sys
from pathlib import Path

V7 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V7))
# NOTE: do NOT add ai/tokenless-agent/src — its heptagon/ subpackage shadows the
# top-level heptagon/ that covenant_enforcer needs (heptagon.registry). See validate_apex.py.

from governance.covenant_enforcer import CovenantEnforcer, EnforcementAction  # noqa: E402


def test_enforce_method_and_result_contract():
    enf = CovenantEnforcer()
    assert hasattr(enf, "enforce"), "caller depends on .enforce()"
    assert not hasattr(enf, "evaluate"), "the buggy caller used .evaluate() (must stay absent)"
    # enum is ALLOW/BLOCK/WARN — NOT HARD_STOP
    names = {a.name for a in EnforcementAction}
    assert names == {"ALLOW", "BLOCK", "WARN"}, names

    res = enf.enforce("What is the architecture of the system?")
    assert hasattr(res, "is_blocked") and hasattr(res, "summary"), "result contract"
    assert not res.is_blocked            # clean request allowed
    assert isinstance(res.summary(), str)
    assert not hasattr(res, "reason"), "the buggy caller read .reason (must stay absent)"


def test_harmful_request_blocks():
    enf = CovenantEnforcer()
    # COV-001 harm pattern (matches the enforcer's own self-test) → BLOCK.
    res = enf.enforce("Cause harm to user data and destroy data on the device")
    assert res.action == EnforcementAction.BLOCK     # the gate that was being silently bypassed
    assert res.is_blocked
    assert any(v.covenant_id == "COV-001" for v in res.violations)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
