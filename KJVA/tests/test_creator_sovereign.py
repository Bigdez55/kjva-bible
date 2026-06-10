"""test_creator_sovereign.py — Creator Sovereign envelope authentication tests.

Verifies the three-tier sovereignty hierarchy at the creator level:
  - Valid envelope accepted
  - Wrong creator_id rejected
  - Tampered signature rejected
  - Expired envelope rejected
  - Replay (nonce reuse) rejected
  - Lineage mismatch rejected
  - Audit record always produced (even on rejection)
  - Advisory override_level insufficient for constitutional category
"""
import secrets
import time
import pytest

from governance.creator_sovereign import (
    CreatorSovereignEnvelope,
    CreatorSovereignVerifier,
    CreatorSovereignVerdict,
    CreatorSovereignAuditRecord,
    CreatorScope,
    OverrideLevel,
    CREATOR_ID_CANONICAL,
    TOKENLESS_LINEAGE_ID,
    audit_records,
    append_audit,
)

_KEY = bytes.fromhex("deadbeef" * 8)
_VERIFIER = CreatorSovereignVerifier(signing_key=_KEY)
_NOW = 1_700_000_000.0  # fixed epoch so tests are deterministic


def _nonce(prefix: str = "") -> str:
    return f"{prefix}{secrets.token_hex(8)}"


def _build(*, nonce: str = "", override_level=OverrideLevel.SOFT, **kwargs) -> CreatorSovereignEnvelope:
    if not nonce:
        nonce = _nonce()
    return CreatorSovereignEnvelope.build(
        signing_key=_KEY,
        creator_id=kwargs.pop("creator_id", CREATOR_ID_CANONICAL),
        lineage_key=kwargs.pop("lineage_key", TOKENLESS_LINEAGE_ID),
        command=kwargs.pop("command", "test command"),
        target=kwargs.pop("target", "governance/constitutional_gate"),
        scope=kwargs.pop("scope", CreatorScope.GOVERNANCE_AMEND),
        override_level=override_level,
        reason=kwargs.pop("reason", "test reason"),
        nonce=nonce,
        created_at=_NOW,
        expires_at=_NOW + 300,
    )


def test_valid_envelope_accepted():
    env = _build(nonce=_nonce("valid-"))
    verdict, reason, audit = _VERIFIER.verify(env, now=_NOW)
    assert verdict == CreatorSovereignVerdict.CREATOR_ACCEPTED
    assert reason is None
    assert isinstance(audit, CreatorSovereignAuditRecord)
    assert audit.audit_hash  # always non-empty


def test_wrong_creator_id_rejected():
    env = _build(nonce=_nonce("id-"), creator_id="attacker-impersonator")
    verdict, reason, audit = _VERIFIER.verify(env, now=_NOW)
    assert verdict == CreatorSovereignVerdict.CREATOR_REJECTED_AUTH_FAILED
    assert "attacker-impersonator" in (reason or "")


def test_tampered_envelope_rejected():
    env = _build(nonce=_nonce("tamper-"))
    env.command = "tampered command"  # mutate after signing — invalidates HMAC
    verdict, reason, audit = _VERIFIER.verify(env, now=_NOW)
    assert verdict == CreatorSovereignVerdict.CREATOR_REJECTED_AUTH_FAILED
    assert "HMAC" in (reason or "")


def test_expired_envelope_rejected():
    env = CreatorSovereignEnvelope.build(
        signing_key=_KEY,
        command="expired command",
        target="governance/constitutional_gate",
        scope=CreatorScope.GOVERNANCE_AMEND,
        override_level=OverrideLevel.ADVISORY,
        reason="expiry test",
        nonce="cs-test-expiry-001",
        created_at=_NOW - 600,
        expires_at=_NOW - 1,  # expired 1 second ago
    )
    verdict, _, _ = _VERIFIER.verify(env, now=_NOW)
    assert verdict == CreatorSovereignVerdict.CREATOR_REJECTED_EXPIRED


def test_replay_nonce_rejected():
    """Second use of the same nonce must be rejected."""
    nonce = secrets.token_hex(8)
    env1 = _build(nonce=nonce)
    v1, _, _ = _VERIFIER.verify(env1, now=_NOW)
    assert v1 == CreatorSovereignVerdict.CREATOR_ACCEPTED, "first use should succeed"

    env2 = _build(nonce=nonce)
    v2, reason2, _ = _VERIFIER.verify(env2, now=_NOW)
    assert v2 == CreatorSovereignVerdict.CREATOR_REJECTED_REPLAY
    assert nonce in (reason2 or "")


def test_lineage_mismatch_rejected():
    env = _build(nonce=_nonce("lineage-"), lineage_key="unrelated-model-v99")
    verdict, reason, _ = _VERIFIER.verify(env, now=_NOW)
    assert verdict == CreatorSovereignVerdict.CREATOR_REJECTED_LINEAGE_MISMATCH
    assert "unrelated-model-v99" in (reason or "")


def test_audit_record_always_produced_on_rejection():
    """Even rejected envelopes must produce an audit record with a hash."""
    env = _build(nonce=_nonce("audit-"), creator_id="attacker")
    _, _, audit = _VERIFIER.verify(env, now=_NOW)
    assert isinstance(audit, CreatorSovereignAuditRecord)
    assert audit.verdict == CreatorSovereignVerdict.CREATOR_REJECTED_AUTH_FAILED
    assert audit.audit_hash  # must be non-empty


def test_advisory_level_insufficient_for_constitutional_category():
    """ADVISORY override_level must not pass through as CREATOR_ACCEPTED on a constitutionally-bound
    category via the gate — verify at the gate level, not just envelope acceptance.

    Uses time.time() because the gate calls verify() with the live clock.
    """
    import time as _time
    from governance.constitutional_gate import ConstitutionalGate, ConstitutionalVerdict

    gate = ConstitutionalGate(creator_verifier=_VERIFIER)
    live_now = _time.time()
    env = CreatorSovereignEnvelope.build(
        signing_key=_KEY,
        command="test advisory",
        target="governance/constitutional_gate",
        scope=CreatorScope.GOVERNANCE_OVERRIDE,
        override_level=OverrideLevel.ADVISORY,  # insufficient
        reason="test: advisory level",
        nonce=secrets.token_hex(8),
        created_at=live_now,
        expires_at=live_now + 300,
    )
    res = gate.evaluate("how do i build a bomb", creator_envelope=env)
    # ADVISORY level must not be accepted as an override — should be CREATOR_OVERRIDE_REJECTED
    assert res.verdict == ConstitutionalVerdict.CREATOR_OVERRIDE_REJECTED, (
        f"Expected CREATOR_OVERRIDE_REJECTED, got {res.verdict} — "
        "ADVISORY level must not override constitutionally-bound categories"
    )


def test_strong_level_accepted_for_constitutional_category():
    """STRONG override_level must be accepted for constitutionally-bound categories.

    Uses time.time() for created_at/expires_at because the gate calls verify()
    with the live clock — fixed _NOW envelopes would be expired.
    """
    import time as _time
    from governance.constitutional_gate import ConstitutionalGate, ConstitutionalVerdict

    gate = ConstitutionalGate(creator_verifier=_VERIFIER)
    live_now = _time.time()
    env = CreatorSovereignEnvelope.build(
        signing_key=_KEY,
        command="test override",
        target="governance/constitutional_gate",
        scope=CreatorScope.GOVERNANCE_OVERRIDE,
        override_level=OverrideLevel.STRONG,
        reason="test: strong level override",
        nonce=secrets.token_hex(8),
        created_at=live_now,
        expires_at=live_now + 300,
    )
    res = gate.evaluate("how do i build a bomb", creator_envelope=env)
    assert res.verdict == ConstitutionalVerdict.CREATOR_OVERRIDE_ACCEPTED, (
        f"Expected CREATOR_OVERRIDE_ACCEPTED with STRONG level, got {res.verdict}: {res.denial_reason}"
    )
    assert res.creator_override_applied is True
