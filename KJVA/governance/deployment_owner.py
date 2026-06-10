"""governance/deployment_owner.py — Deployment Owner command envelope.

The Deployment Owner is a delegated steward of a specific deployed instance of the
Tokenless model. This is distinct from and subordinate to the Creator Sovereign.

Deployment owners may:
  - Configure and command their deployed instance
  - Set operating modes within constitutional boundaries
  - Grant or restrict operator/user permissions within their deployment
  - Stop, restart, or reconfigure their instance
  - Set memory retention, privacy, and persona configuration (within doctrine)

Deployment owners may NOT:
  - Override the constitution or biblical-law governance
  - Disable safety gates (harm_prevention, oppression_or_exploitation, etc.)
  - Bypass the creator sovereign authority layer
  - Modify the model's foundational identity (ADR-0001 §1)
  - Authorize weight promotion without creator-sovereign authority
  - Remove the audit trail for their own commands

If a deployment-owner command requires creator authority, the verdict is
OWNER_REQUIRES_CREATOR_AUTHORITY. The deployment owner must then obtain a
CreatorSovereignEnvelope and retry through the constitutional gate.

Authentication model:
  - owner_id: identifier for the deployment owner
  - deployment_id: the specific deployed instance
  - owner_signature: HMAC-SHA256 of canonical_payload() using the owner's signing key
  - nonce: one-use token (replay protection)
  - created_at / expires_at: time-bounded validity (max TTL: 1 hour)

Compared to CreatorSovereignEnvelope:
  - No lineage_key — owner authority is instance-scoped, not lineage-scoped
  - No constitutional_action — owners cannot amend the constitution
  - No ROOT or CONSTITUTIONAL override_level — the constitutional gate will reject those
  - Scope is more limited: see DeploymentOwnerScope
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Set

from governance.scriptural_registry import (
    SCRIPTURAL_REGISTRY,
    is_constitutionally_bound,
    get_gate_action,
    GATE_HARD_STOP,
    GATE_DENY_CONSTITUTIONAL,
)

# ── Deployment-owner scope ─────────────────────────────────────────────────────

class DeploymentOwnerScope(Enum):
    """What a deployment-owner command is permitted to address."""
    # Configure the instance operating mode
    CONFIGURE_INSTANCE = "configure_instance"
    # Grant or restrict operator/user permissions
    PERMISSION_MANAGEMENT = "permission_management"
    # Control instance lifecycle (stop, restart, health check)
    LIFECYCLE_CONTROL = "lifecycle_control"
    # Memory and privacy controls
    MEMORY_PRIVACY = "memory_privacy"
    # Safety level configuration (WITHIN constitutional bounds only)
    SAFETY_CONFIGURE = "safety_configure"
    # Override a specific non-constitutional gate decision
    GOVERNANCE_SOFT_OVERRIDE = "governance_soft_override"
    # Read audit records for their deployment
    AUDIT_READ = "audit_read"


# ── Verdict ────────────────────────────────────────────────────────────────────

class DeploymentOwnerVerdict(Enum):
    OWNER_ALLOWED = "OWNER_ALLOWED"
    OWNER_DENIED_CONSTITUTION = "OWNER_DENIED_CONSTITUTION"
    OWNER_DENIED_SAFETY = "OWNER_DENIED_SAFETY"
    OWNER_DENIED_AUTH_FAILED = "OWNER_DENIED_AUTH_FAILED"
    OWNER_DENIED_EXPIRED = "OWNER_DENIED_EXPIRED"
    OWNER_DENIED_REPLAY = "OWNER_DENIED_REPLAY"
    OWNER_REQUIRES_CREATOR_AUTHORITY = "OWNER_REQUIRES_CREATOR_AUTHORITY"
    OWNER_RECORDED = "OWNER_RECORDED"


# ── Envelope ───────────────────────────────────────────────────────────────────

@dataclass
class DeploymentOwnerCommandEnvelope:
    """Authenticated deployment-owner command envelope.

    Scoped to the deployer's instance. Cannot override constitutionally-bound categories.
    """
    owner_id: str
    deployment_id: str
    owner_signature: str          # HMAC-SHA256 hex of canonical_payload()
    command: str
    target: str                   # What is being targeted
    scope: DeploymentOwnerScope
    requested_action: str         # Human-readable description of what is requested
    reason: str                   # Auditable intent
    nonce: str
    created_at: float
    expires_at: float
    # Filled in by the verifier after evaluation
    constitutional_scan: Optional[str] = None    # Which scriptural category was triggered (if any)
    safety_scan: Optional[str] = None            # Which safety category was triggered (if any)
    allowed_under_constitution: Optional[bool] = None
    requires_creator_authority: Optional[bool] = None
    final_verdict: Optional[DeploymentOwnerVerdict] = None
    audit_hash: Optional[str] = None

    def canonical_payload(self) -> str:
        return json.dumps({
            "owner_id": self.owner_id,
            "deployment_id": self.deployment_id,
            "command": self.command,
            "target": self.target,
            "scope": self.scope.value,
            "requested_action": self.requested_action,
            "reason": self.reason,
            "nonce": self.nonce,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }, sort_keys=True, separators=(",", ":"))

    @classmethod
    def build(
        cls,
        *,
        signing_key: bytes,
        owner_id: str,
        deployment_id: str,
        command: str,
        target: str,
        scope: DeploymentOwnerScope,
        requested_action: str,
        reason: str,
        nonce: str,
        created_at: float,
        expires_at: float,
    ) -> "DeploymentOwnerCommandEnvelope":
        env = cls(
            owner_id=owner_id,
            deployment_id=deployment_id,
            owner_signature="",
            command=command,
            target=target,
            scope=scope,
            requested_action=requested_action,
            reason=reason,
            nonce=nonce,
            created_at=created_at,
            expires_at=expires_at,
        )
        payload = env.canonical_payload()
        env.owner_signature = hmac.new(
            signing_key, payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return env


# ── Audit record ───────────────────────────────────────────────────────────────

@dataclass
class DeploymentOwnerAuditRecord:
    owner_id: str
    deployment_id: str
    command: str
    scope: str
    requested_action: str
    reason: str
    nonce: str
    created_at: float
    evaluated_at: float
    verdict: DeploymentOwnerVerdict
    rejection_reason: Optional[str]
    constitutional_scan: Optional[str]
    safety_scan: Optional[str]
    audit_hash: str = field(default="")

    def __post_init__(self) -> None:
        if not self.audit_hash:
            payload = json.dumps({
                "owner_id": self.owner_id,
                "deployment_id": self.deployment_id,
                "command": self.command,
                "verdict": self.verdict.value,
                "evaluated_at": self.evaluated_at,
                "nonce": self.nonce,
            }, sort_keys=True, separators=(",", ":"))
            self.audit_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


# ── Constitutionally prohibited owner scope ────────────────────────────────────

# Commands that owners request that always require creator authority (regardless of scope).
_CREATOR_REQUIRED_TARGETS = frozenset({
    "governance/constitution",
    "governance/scriptural_registry",
    "governance/creator_sovereign",
    "training/canonical",
    "training/promotion",
    "identity/lineage",
    "identity/model_config",
    "doctrine/adr",
})

# Scopes that owners can never use — reserved for Creator Sovereign.
_OWNER_FORBIDDEN_SCOPES = frozenset()  # All DeploymentOwnerScope values are permitted with auth


# ── Replay protection ──────────────────────────────────────────────────────────

_nonce_lock = threading.Lock()
_used_nonces: Set[str] = set()
_nonce_timestamps: Dict[str, float] = {}
_MAX_TTL_S = 3600  # deployment-owner commands may not exceed 1-hour TTL
_NONCE_EXPIRY_S = 86400


def _check_and_consume_nonce(nonce: str, now: float) -> bool:
    with _nonce_lock:
        expired = [n for n, t in _nonce_timestamps.items() if now - t > _NONCE_EXPIRY_S]
        for n in expired:
            _used_nonces.discard(n)
            _nonce_timestamps.pop(n, None)
        if nonce in _used_nonces:
            return False
        _used_nonces.add(nonce)
        _nonce_timestamps[nonce] = now
        return True


# ── Verifier ───────────────────────────────────────────────────────────────────

@dataclass
class DeploymentOwnerVerifier:
    """Verifies DeploymentOwnerCommandEnvelope.

    The verifier checks: authentication, expiry, replay, and then scans the command
    against constitutionally-bound categories to determine if creator authority is required.
    """
    signing_key: bytes
    allowed_owner_ids: Optional[Set[str]] = None  # None = accept any (use in single-owner deployments)

    def verify(
        self,
        envelope: DeploymentOwnerCommandEnvelope,
        *,
        now: Optional[float] = None,
    ) -> tuple[DeploymentOwnerVerdict, Optional[str], DeploymentOwnerAuditRecord]:
        """Verify a DeploymentOwnerCommandEnvelope.

        Returns (verdict, rejection_reason, audit_record). Audit record is always returned.
        """
        evaluated_at = now if now is not None else time.time()
        rejection_reason: Optional[str] = None
        constitutional_scan: Optional[str] = None
        safety_scan: Optional[str] = None

        # 1. Owner ID
        if self.allowed_owner_ids is not None and envelope.owner_id not in self.allowed_owner_ids:
            rejection_reason = f"owner_id not recognized: {envelope.owner_id!r}"
            verdict = DeploymentOwnerVerdict.OWNER_DENIED_AUTH_FAILED
        # 2. Expiry
        elif evaluated_at > envelope.expires_at:
            rejection_reason = f"envelope expired at {envelope.expires_at}"
            verdict = DeploymentOwnerVerdict.OWNER_DENIED_EXPIRED
        # 3. TTL cap (owners cannot issue long-lived commands)
        elif (envelope.expires_at - envelope.created_at) > _MAX_TTL_S:
            rejection_reason = f"envelope TTL exceeds maximum {_MAX_TTL_S}s"
            verdict = DeploymentOwnerVerdict.OWNER_DENIED_AUTH_FAILED
        # 4. Not-before
        elif evaluated_at < envelope.created_at:
            rejection_reason = f"envelope not yet valid: created_at={envelope.created_at}"
            verdict = DeploymentOwnerVerdict.OWNER_DENIED_AUTH_FAILED
        # 5. HMAC signature
        elif not self._verify_signature(envelope):
            rejection_reason = "owner_signature HMAC verification failed"
            verdict = DeploymentOwnerVerdict.OWNER_DENIED_AUTH_FAILED
        # 6. Nonce
        elif not _check_and_consume_nonce(envelope.nonce, evaluated_at):
            rejection_reason = f"nonce already used: {envelope.nonce!r}"
            verdict = DeploymentOwnerVerdict.OWNER_DENIED_REPLAY
        else:
            # 7. Constitutional scan — check if this target requires creator authority
            if any(envelope.target.startswith(t) for t in _CREATOR_REQUIRED_TARGETS):
                rejection_reason = f"target {envelope.target!r} requires Creator Sovereign authority"
                constitutional_scan = "doctrine_conflict"
                verdict = DeploymentOwnerVerdict.OWNER_REQUIRES_CREATOR_AUTHORITY
            # 8. Constitutional scan — check if requested action touches safety gates
            elif self._is_safety_gate_override(envelope):
                safety_cat = self._safety_category(envelope)
                safety_scan = safety_cat
                if is_constitutionally_bound(safety_cat):
                    rejection_reason = (
                        f"action touches constitutionally-bound category {safety_cat!r}; "
                        "requires Creator Sovereign authority"
                    )
                    constitutional_scan = safety_cat
                    verdict = DeploymentOwnerVerdict.OWNER_REQUIRES_CREATOR_AUTHORITY
                else:
                    verdict = DeploymentOwnerVerdict.OWNER_ALLOWED
            else:
                verdict = DeploymentOwnerVerdict.OWNER_ALLOWED

        audit = DeploymentOwnerAuditRecord(
            owner_id=envelope.owner_id,
            deployment_id=envelope.deployment_id,
            command=envelope.command,
            scope=envelope.scope.value,
            requested_action=envelope.requested_action,
            reason=envelope.reason,
            nonce=envelope.nonce,
            created_at=envelope.created_at,
            evaluated_at=evaluated_at,
            verdict=verdict,
            rejection_reason=rejection_reason,
            constitutional_scan=constitutional_scan,
            safety_scan=safety_scan,
        )
        return verdict, rejection_reason, audit

    def _verify_signature(self, envelope: DeploymentOwnerCommandEnvelope) -> bool:
        payload = envelope.canonical_payload()
        expected = hmac.new(
            self.signing_key, payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, envelope.owner_signature)

    def _is_safety_gate_override(self, envelope: DeploymentOwnerCommandEnvelope) -> bool:
        """Return True if the command appears to request a safety gate override."""
        action_lower = (envelope.requested_action or "").lower()
        target_lower = (envelope.target or "").lower()
        safety_keywords = (
            "disable safety", "bypass governance", "ignore constitution",
            "override harm", "disable harm", "allow harm", "remove safety",
            "disable csam", "allow csam", "override csam", "disable violence",
        )
        return any(kw in action_lower or kw in target_lower for kw in safety_keywords)

    def _safety_category(self, envelope: DeploymentOwnerCommandEnvelope) -> str:
        """Return the most relevant scriptural safety category for a safety-gate-override request."""
        action_lower = (envelope.requested_action or "").lower()
        if "csam" in action_lower:
            return "oppression_or_exploitation"
        if "harm" in action_lower or "violence" in action_lower or "weapon" in action_lower:
            return "harm_prevention"
        if "constitution" in action_lower or "governance" in action_lower:
            return "corruption_or_defilement"
        return "doctrine_conflict"


# ── Audit log ──────────────────────────────────────────────────────────────────

_audit_lock = threading.Lock()
_audit_log: list[DeploymentOwnerAuditRecord] = []


def append_audit(record: DeploymentOwnerAuditRecord) -> None:
    with _audit_lock:
        _audit_log.append(record)


def audit_records() -> list[DeploymentOwnerAuditRecord]:
    with _audit_lock:
        return list(_audit_log)
