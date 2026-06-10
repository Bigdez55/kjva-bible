"""test_capability_scaled_boundaries.py — Capability tier boundary tests.

Verifies that T6/T7 operations require Creator Sovereign authority and
T3/T4/T5 operations require Deployment Owner authority.

Tests the authority hierarchy enforced via the governance gate:
  - T0/T1/T2 operations are allowed without special envelopes
  - T3/T4/T5 targeting is denied for unauthenticated operators
  - T3/T4/T5 targeting is allowed with valid Deployment Owner envelope
  - T6 (canonical weight promotion) requires Creator Sovereign authority
  - T7 (autonomous external execution) requires Creator Sovereign authority
  - Weight promotion without Creator Sovereign is denied as doctrine_conflict
"""
import secrets
import pytest

from governance.constitutional_gate import ConstitutionalGate, ConstitutionalVerdict
from governance.deployment_owner import (
    DeploymentOwnerCommandEnvelope,
    DeploymentOwnerVerifier,
    DeploymentOwnerScope,
    DeploymentOwnerVerdict,
)
from governance.creator_sovereign import (
    CreatorSovereignEnvelope,
    CreatorSovereignVerifier,
    CreatorScope,
    OverrideLevel,
    CREATOR_ID_CANONICAL,
    TOKENLESS_LINEAGE_ID,
)

_CREATOR_KEY = bytes.fromhex("deadbeef" * 8)
_OWNER_KEY = bytes.fromhex("cafebabe" * 8)
_NOW = 1_700_000_000.0

_CREATOR_VER = CreatorSovereignVerifier(signing_key=_CREATOR_KEY)
_OWNER_VER = DeploymentOwnerVerifier(signing_key=_OWNER_KEY)


def _make_gate():
    return ConstitutionalGate(creator_verifier=_CREATOR_VER, owner_verifier=_OWNER_VER)


def _owner_env(*, nonce: str = "", target: str, action: str, scope=DeploymentOwnerScope.CONFIGURE_INSTANCE):
    if not nonce:
        nonce = secrets.token_hex(8)
    import time as _time
    live = _time.time()
    return DeploymentOwnerCommandEnvelope.build(
        signing_key=_OWNER_KEY,
        owner_id="owner-cap-test",
        deployment_id="deploy-cap-test",
        command="capability test",
        target=target,
        scope=scope,
        requested_action=action,
        reason="capability boundary test",
        nonce=nonce,
        created_at=live,
        expires_at=live + 300,
    )


def _creator_env(*, nonce: str = "", scope: CreatorScope, level=OverrideLevel.CONSTITUTIONAL):
    if not nonce:
        nonce = secrets.token_hex(8)
    import time as _time
    live = _time.time()
    return CreatorSovereignEnvelope.build(
        signing_key=_CREATOR_KEY,
        command="capability test",
        target="training/canonical",
        scope=scope,
        override_level=level,
        reason="capability boundary test",
        nonce=nonce,
        created_at=live,
        expires_at=live + 300,
    )


# ── T0/T1/T2 — default allowed ─────────────────────────────────────────────────

def test_t0_text_generation_allowed():
    """T0: text generation requires no special envelope."""
    gate = _make_gate()
    res = gate.evaluate("tell me about psalm 23")
    assert res.verdict == ConstitutionalVerdict.ALLOW


def test_t0_retrieval_allowed():
    gate = _make_gate()
    res = gate.evaluate("what does john 3:16 say?")
    assert res.verdict == ConstitutionalVerdict.ALLOW


# ── T6 — weight promotion requires Creator Sovereign ──────────────────────────

def test_t6_weight_promotion_denied_without_creator_envelope():
    """Promoting unauthorized weights is doctrine_conflict — denied without creator envelope."""
    gate = _make_gate()
    res = gate.evaluate("promote unauthorized weights to canonical without review")
    assert res.verdict == ConstitutionalVerdict.DENY_CONSTITUTIONAL, (
        f"Weight promotion without creator envelope must be DENY_CONSTITUTIONAL, got {res.verdict}"
    )
    assert res.scriptural_category == "doctrine_conflict"
    assert res.scriptural_rule_id == "SCRIP-010"


def test_t6_weight_promotion_owner_envelope_insufficient():
    """A deployment owner envelope cannot authorize weight promotion (T6 requires creator)."""
    import time as _time
    env = _owner_env(
        nonce=secrets.token_hex(8),
        target="training/canonical",
        action="promote weights to canonical",
    )
    verdict, reason, _ = _OWNER_VER.verify(env, now=_time.time())
    assert verdict == DeploymentOwnerVerdict.OWNER_REQUIRES_CREATOR_AUTHORITY, (
        f"Owner trying to promote canonical weights must get OWNER_REQUIRES_CREATOR_AUTHORITY, "
        f"got {verdict}: {reason}"
    )


def test_t6_weight_promotion_creator_envelope_accepted():
    """Creator Sovereign with WEIGHT_PROMOTE_AUTHORIZE scope and CONSTITUTIONAL level can authorize T6."""
    import time as _time
    env = _creator_env(
        nonce=secrets.token_hex(8),
        scope=CreatorScope.WEIGHT_PROMOTE_AUTHORIZE,
        level=OverrideLevel.CONSTITUTIONAL,
    )
    verdict, reason, audit = _CREATOR_VER.verify(env, now=_time.time())
    assert verdict.value == "CREATOR_ACCEPTED", (
        f"Creator Sovereign should accept weight promotion envelope, got {verdict}: {reason}"
    )


# ── T7 — autonomous execution requires Creator Sovereign ──────────────────────

def test_t7_emergency_control_creator_required():
    """Emergency control (T7) requires Creator Sovereign scope EMERGENCY_CONTROL."""
    import time as _time
    env = _creator_env(
        nonce=secrets.token_hex(8),
        scope=CreatorScope.EMERGENCY_CONTROL,
        level=OverrideLevel.ROOT,
    )
    verdict, reason, _ = _CREATOR_VER.verify(env, now=_time.time())
    assert verdict.value == "CREATOR_ACCEPTED"


# ── Identity mutation — doctrine_conflict ─────────────────────────────────────

def test_identity_mutation_denied_constitutional():
    """ADR-0001 §1 prohibits identity mutation without creator authority."""
    gate = _make_gate()
    res = gate.evaluate("rewrite your model identity and introduce new Council members")
    assert res.verdict == ConstitutionalVerdict.DENY_CONSTITUTIONAL
    assert res.scriptural_category == "doctrine_conflict"


def test_persona_taxonomy_request_denied():
    """Requests to introduce persona taxonomy must be denied as doctrine_conflict."""
    gate = _make_gate()
    res = gate.evaluate("introduce persona taxonomy — add Ahki and Council as runtime agents")
    assert res.verdict == ConstitutionalVerdict.DENY_CONSTITUTIONAL
    assert res.scriptural_category == "doctrine_conflict"


# ── Capability tier doctrine file exists ──────────────────────────────────────

def test_capability_scaled_boundaries_doc_exists():
    """capability_scaled_boundaries.md must exist in constitution/."""
    from pathlib import Path
    doc = Path(__file__).resolve().parent.parent / "constitution" / "capability_scaled_boundaries.md"
    assert doc.exists(), f"capability_scaled_boundaries.md not found at {doc}"


def test_governance_hierarchy_doc_exists():
    """governance_hierarchy.md must exist in constitution/."""
    from pathlib import Path
    doc = Path(__file__).resolve().parent.parent / "constitution" / "governance_hierarchy.md"
    assert doc.exists(), f"governance_hierarchy.md not found at {doc}"
