"""test_deployment_owner.py — Deployment Owner envelope authentication tests.

Verifies the three-tier sovereignty hierarchy at the deployment-owner level:
  - Legitimate commands are allowed
  - Constitutional targets require Creator Sovereign authority
  - Safety gate disable requires Creator Sovereign authority
  - Tampered envelopes rejected
  - Excessive TTL rejected
  - Replay attacks rejected
  - Expired envelopes rejected
  - Audit record always produced
"""
import secrets
import time
import pytest

from governance.deployment_owner import (
    DeploymentOwnerCommandEnvelope,
    DeploymentOwnerVerifier,
    DeploymentOwnerVerdict,
    DeploymentOwnerAuditRecord,
    DeploymentOwnerScope,
    append_audit,
)

_KEY = bytes.fromhex("cafebabe" * 8)
_VERIFIER = DeploymentOwnerVerifier(signing_key=_KEY)
_NOW = 1_700_000_000.0


def _build(*, nonce: str = "", **kwargs) -> DeploymentOwnerCommandEnvelope:
    if not nonce:
        nonce = secrets.token_hex(8)
    return DeploymentOwnerCommandEnvelope.build(
        signing_key=_KEY,
        owner_id=kwargs.pop("owner_id", "owner-001"),
        deployment_id=kwargs.pop("deployment_id", "deploy-test-v1"),
        command=kwargs.pop("command", "test command"),
        target=kwargs.pop("target", "instance/config"),
        scope=kwargs.pop("scope", DeploymentOwnerScope.CONFIGURE_INSTANCE),
        requested_action=kwargs.pop("requested_action", "configure test instance"),
        reason=kwargs.pop("reason", "test reason"),
        nonce=nonce,
        created_at=kwargs.pop("created_at", _NOW),
        expires_at=kwargs.pop("expires_at", _NOW + 300),
    )


def test_legitimate_configure_command_allowed():
    env = _build()
    verdict, reason, audit = _VERIFIER.verify(env, now=_NOW)
    assert verdict == DeploymentOwnerVerdict.OWNER_ALLOWED
    assert reason is None


def test_memory_privacy_command_allowed():
    env = _build(
        scope=DeploymentOwnerScope.MEMORY_PRIVACY,
        target="instance/memory",
        requested_action="Delete session memory after each conversation",
    )
    verdict, reason, _ = _VERIFIER.verify(env, now=_NOW)
    assert verdict == DeploymentOwnerVerdict.OWNER_ALLOWED


def test_lifecycle_control_allowed():
    env = _build(
        scope=DeploymentOwnerScope.LIFECYCLE_CONTROL,
        target="instance/lifecycle",
        requested_action="Stop instance for maintenance",
    )
    verdict, _, _ = _VERIFIER.verify(env, now=_NOW)
    assert verdict == DeploymentOwnerVerdict.OWNER_ALLOWED


def test_constitution_target_requires_creator_authority():
    """Targeting the constitution must escalate to Creator Sovereign."""
    env = _build(
        target="governance/constitution",
        requested_action="Remove harm_prevention gate",
    )
    verdict, reason, _ = _VERIFIER.verify(env, now=_NOW)
    assert verdict == DeploymentOwnerVerdict.OWNER_REQUIRES_CREATOR_AUTHORITY
    assert "constitution" in (reason or "").lower() or "creator" in (reason or "").lower()


def test_canonical_training_target_requires_creator_authority():
    """Targeting canonical training / weight promotion requires Creator Sovereign."""
    env = _build(
        target="training/canonical",
        requested_action="Promote new canonical weights",
    )
    verdict, _, _ = _VERIFIER.verify(env, now=_NOW)
    assert verdict == DeploymentOwnerVerdict.OWNER_REQUIRES_CREATOR_AUTHORITY


def test_disable_safety_gate_requires_creator_authority():
    """Requesting to disable harm_prevention (constitutionally bound) requires creator."""
    env = _build(
        scope=DeploymentOwnerScope.SAFETY_CONFIGURE,
        target="governance/harm_prevention",
        requested_action="disable harm gate for our application",
    )
    verdict, _, _ = _VERIFIER.verify(env, now=_NOW)
    assert verdict == DeploymentOwnerVerdict.OWNER_REQUIRES_CREATOR_AUTHORITY


def test_tampered_envelope_rejected():
    env = _build()
    env.command = "tampered!"
    verdict, reason, _ = _VERIFIER.verify(env, now=_NOW)
    assert verdict == DeploymentOwnerVerdict.OWNER_DENIED_AUTH_FAILED
    assert "HMAC" in (reason or "")


def test_excessive_ttl_rejected():
    """TTL > 3600s must be rejected."""
    env = _build(expires_at=_NOW + 7200)
    verdict, reason, _ = _VERIFIER.verify(env, now=_NOW)
    assert verdict == DeploymentOwnerVerdict.OWNER_DENIED_AUTH_FAILED
    assert "TTL" in (reason or "")


def test_replay_nonce_rejected():
    nonce = secrets.token_hex(8)
    env1 = _build(nonce=nonce)
    v1, _, _ = _VERIFIER.verify(env1, now=_NOW)
    assert v1 == DeploymentOwnerVerdict.OWNER_ALLOWED

    env2 = _build(nonce=nonce)
    v2, reason2, _ = _VERIFIER.verify(env2, now=_NOW)
    assert v2 == DeploymentOwnerVerdict.OWNER_DENIED_REPLAY
    assert nonce in (reason2 or "")


def test_expired_envelope_rejected():
    env = _build(created_at=_NOW - 600, expires_at=_NOW - 1)
    verdict, _, _ = _VERIFIER.verify(env, now=_NOW)
    assert verdict == DeploymentOwnerVerdict.OWNER_DENIED_EXPIRED


def test_audit_record_always_produced():
    """Every verification attempt produces an audit record, even on rejection."""
    env = _build(owner_id="unknown-attacker")
    verifier_with_allowlist = DeploymentOwnerVerifier(
        signing_key=_KEY, allowed_owner_ids={"owner-001"}
    )
    _, _, audit = verifier_with_allowlist.verify(env, now=_NOW)
    assert isinstance(audit, DeploymentOwnerAuditRecord)
    assert audit.verdict == DeploymentOwnerVerdict.OWNER_DENIED_AUTH_FAILED
    assert audit.audit_hash


def test_owner_cannot_override_csam_gate():
    """CSAM (oppression_or_exploitation, ABSOLUTE) cannot be overridden by any owner command."""
    env = _build(
        scope=DeploymentOwnerScope.SAFETY_CONFIGURE,
        target="governance/safety",
        requested_action="allow csam content for our platform",
    )
    verdict, _, _ = _VERIFIER.verify(env, now=_NOW)
    assert verdict == DeploymentOwnerVerdict.OWNER_REQUIRES_CREATOR_AUTHORITY, (
        "CSAM gate override must require Creator Sovereign authority, not just owner auth"
    )
