"""governance/creator_sovereign.py — Creator Sovereign authority envelope.

The Creator Sovereign is the root authority over the Tokenless model lineage.
This is DISTINCT from a deployment owner. The creator defines the constitution,
the governance, and the lawful operating boundaries. Creator Sovereign commands
sit above deployment-owner commands and above internal governance gates.

Three-tier sovereignty hierarchy (top to bottom):
  1. Creator Sovereign  ← this module
  2. Constitutional Authority (biblical law, doctrine, constitution, governance)
  3. Deployment Owner   ← see deployment_owner.py
  4. Operator/User
  5. Model Runtime

Creator authority is NOT a boolean flag or an env var. It requires:
  - Authenticated creator_id
  - HMAC-SHA256 root_signature over the canonical envelope payload
  - Lineage key binding (model lineage ID — prevents use across unrelated lineages)
  - Time-bounded validity (created_at / expires_at)
  - Nonce (one-use token — replay protection)
  - Explicit override_level declaration
  - Reason field (auditable intent)

All commands are logged via CreatorSovereignAuditRecord. No silent authority path exists.

Deployment owners CANNOT impersonate Creator Sovereign — they have a separate
envelope (DeploymentOwnerCommandEnvelope in deployment_owner.py) with strictly
more limited scope.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Set

# ── Lineage identity ───────────────────────────────────────────────────────────

TOKENLESS_LINEAGE_ID = "tokenless-kjva-v1"
CREATOR_ID_CANONICAL = "creator-sovereign-tokenless"


# ── Override scopes ────────────────────────────────────────────────────────────

class CreatorScope(Enum):
    """What the creator command is permitted to address."""
    # Governance — modify a gate, threshold, or evaluator behaviour
    GOVERNANCE_AMEND = "governance_amend"
    # Constitutional — amend constitutional doctrine or principles
    CONSTITUTIONAL_AMEND = "constitutional_amend"
    # Identity — authorize an identity change or lineage fork
    IDENTITY_AUTHORIZE = "identity_authorize"
    # Promotion — authorize a new canonical weight to be promoted
    WEIGHT_PROMOTE_AUTHORIZE = "weight_promote_authorize"
    # Deployment — manage deployment-owner permissions
    DEPLOYMENT_MANAGE = "deployment_manage"
    # Override — override an active governance decision for a specific request
    GOVERNANCE_OVERRIDE = "governance_override"
    # Audit — read/export audit records (read-only scope)
    AUDIT_READ = "audit_read"
    # Emergency — emergency halt or recovery instruction
    EMERGENCY_CONTROL = "emergency_control"


# ── Override levels ────────────────────────────────────────────────────────────

class OverrideLevel(Enum):
    """How deeply this command overrides internal governance."""
    # Advisory: logged but does not change active gate decisions
    ADVISORY = "advisory"
    # Soft: overrides non-constitutional gate decisions only
    SOFT = "soft"
    # Strong: overrides constitutionally-bound decisions for this specific request
    STRONG = "strong"
    # Constitutional: amends the constitution itself (requires created=at and lineage key)
    CONSTITUTIONAL = "constitutional"
    # Root: root-level — maximum authority, amends doctrine or lineage
    ROOT = "root"


# ── Verdict ────────────────────────────────────────────────────────────────────

class CreatorSovereignVerdict(Enum):
    CREATOR_ACCEPTED = "CREATOR_ACCEPTED"
    CREATOR_REJECTED_AUTH_FAILED = "CREATOR_REJECTED_AUTH_FAILED"
    CREATOR_REJECTED_EXPIRED = "CREATOR_REJECTED_EXPIRED"
    CREATOR_REJECTED_REPLAY = "CREATOR_REJECTED_REPLAY"
    CREATOR_REJECTED_LINEAGE_MISMATCH = "CREATOR_REJECTED_LINEAGE_MISMATCH"
    CREATOR_REJECTED_SCOPE_EXCEEDED = "CREATOR_REJECTED_SCOPE_EXCEEDED"
    CREATOR_REQUIRES_CONFIRMATION = "CREATOR_REQUIRES_CONFIRMATION"
    CREATOR_RECORDED = "CREATOR_RECORDED"


# ── Envelope dataclass ─────────────────────────────────────────────────────────

@dataclass
class CreatorSovereignEnvelope:
    """Authenticated creator command envelope.

    All fields are used in the signed payload. Mutation after signing invalidates
    the signature. Use CreatorSovereignEnvelope.build() to create a pre-signed envelope.
    """
    creator_id: str                      # Must match CREATOR_ID_CANONICAL
    root_signature: str                  # HMAC-SHA256 hex of canonical_payload()
    lineage_key: str                     # Lineage binding (TOKENLESS_LINEAGE_ID or derived)
    command: str                         # Human-readable command string
    target: str                          # What is being targeted (e.g. "governance/constitutional_gate")
    scope: CreatorScope                  # Declared scope
    override_level: OverrideLevel        # Declared override authority level
    reason: str                          # Auditable intent
    nonce: str                           # One-use token (UUID or sha256-of-random)
    created_at: float                    # Unix timestamp (UTC)
    expires_at: float                    # Unix timestamp (UTC)
    constitutional_action: Optional[str] = None  # If constitutional_binding applies

    def canonical_payload(self) -> str:
        """Deterministic string that the HMAC is computed over.

        Order is fixed — changing any field changes the payload and invalidates the sig.
        """
        return json.dumps({
            "creator_id": self.creator_id,
            "lineage_key": self.lineage_key,
            "command": self.command,
            "target": self.target,
            "scope": self.scope.value,
            "override_level": self.override_level.value,
            "reason": self.reason,
            "nonce": self.nonce,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "constitutional_action": self.constitutional_action,
        }, sort_keys=True, separators=(",", ":"))

    @classmethod
    def build(
        cls,
        *,
        signing_key: bytes,
        creator_id: str = CREATOR_ID_CANONICAL,
        lineage_key: str = TOKENLESS_LINEAGE_ID,
        command: str,
        target: str,
        scope: CreatorScope,
        override_level: OverrideLevel,
        reason: str,
        nonce: str,
        created_at: float,
        expires_at: float,
        constitutional_action: Optional[str] = None,
    ) -> "CreatorSovereignEnvelope":
        """Construct and sign a CreatorSovereignEnvelope."""
        env = cls(
            creator_id=creator_id,
            root_signature="",  # will be filled in
            lineage_key=lineage_key,
            command=command,
            target=target,
            scope=scope,
            override_level=override_level,
            reason=reason,
            nonce=nonce,
            created_at=created_at,
            expires_at=expires_at,
            constitutional_action=constitutional_action,
        )
        payload = env.canonical_payload()
        env.root_signature = hmac.new(
            signing_key, payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return env


# ── Audit record ───────────────────────────────────────────────────────────────

@dataclass
class CreatorSovereignAuditRecord:
    """Immutable audit record written for every creator command attempt."""
    creator_id: str
    lineage_key: str
    command: str
    scope: str
    override_level: str
    reason: str
    nonce: str
    created_at: float
    evaluated_at: float
    verdict: CreatorSovereignVerdict
    rejection_reason: Optional[str]
    audit_hash: str = field(default="")

    def __post_init__(self) -> None:
        if not self.audit_hash:
            payload = json.dumps({
                "creator_id": self.creator_id,
                "command": self.command,
                "scope": self.scope,
                "verdict": self.verdict.value,
                "evaluated_at": self.evaluated_at,
                "nonce": self.nonce,
            }, sort_keys=True, separators=(",", ":"))
            self.audit_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


# ── Replay protection ──────────────────────────────────────────────────────────

_nonce_lock = threading.Lock()
_used_nonces: Set[str] = set()
_nonce_timestamps: Dict[str, float] = {}
_NONCE_EXPIRY_S = 86400  # 24 hours


def _check_and_consume_nonce(nonce: str, now: float) -> bool:
    """Return True if nonce is fresh and not yet used. Consumes it atomically."""
    with _nonce_lock:
        # Prune expired nonces
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
class CreatorSovereignVerifier:
    """Verifies and evaluates CreatorSovereignEnvelope commands.

    Instantiate once and reuse. The signing_key must be the same key used to build
    the envelope. In production, this key should come from a secure key store, not
    from an env var or plain-text config.
    """
    signing_key: bytes
    allowed_creator_ids: Set[str] = field(default_factory=lambda: {CREATOR_ID_CANONICAL})
    allowed_lineage_keys: Set[str] = field(default_factory=lambda: {TOKENLESS_LINEAGE_ID})

    def verify(
        self,
        envelope: CreatorSovereignEnvelope,
        *,
        now: Optional[float] = None,
    ) -> tuple[CreatorSovereignVerdict, Optional[str], CreatorSovereignAuditRecord]:
        """Verify a CreatorSovereignEnvelope and return (verdict, rejection_reason, audit_record).

        The audit record is always returned regardless of verdict — every attempt is logged.
        """
        evaluated_at = now if now is not None else time.time()
        rejection_reason: Optional[str] = None

        # 1. Creator ID
        if envelope.creator_id not in self.allowed_creator_ids:
            rejection_reason = f"creator_id not recognized: {envelope.creator_id!r}"
            verdict = CreatorSovereignVerdict.CREATOR_REJECTED_AUTH_FAILED
        # 2. Lineage binding
        elif envelope.lineage_key not in self.allowed_lineage_keys:
            rejection_reason = f"lineage_key mismatch: {envelope.lineage_key!r}"
            verdict = CreatorSovereignVerdict.CREATOR_REJECTED_LINEAGE_MISMATCH
        # 3. Expiry
        elif evaluated_at > envelope.expires_at:
            rejection_reason = f"envelope expired at {envelope.expires_at}, now={evaluated_at}"
            verdict = CreatorSovereignVerdict.CREATOR_REJECTED_EXPIRED
        # 4. Not-before
        elif evaluated_at < envelope.created_at:
            rejection_reason = f"envelope not yet valid: created_at={envelope.created_at}"
            verdict = CreatorSovereignVerdict.CREATOR_REJECTED_AUTH_FAILED
        # 5. HMAC signature
        elif not self._verify_signature(envelope):
            rejection_reason = "root_signature HMAC verification failed"
            verdict = CreatorSovereignVerdict.CREATOR_REJECTED_AUTH_FAILED
        # 6. Nonce (replay protection)
        elif not _check_and_consume_nonce(envelope.nonce, evaluated_at):
            rejection_reason = f"nonce already used or expired: {envelope.nonce!r}"
            verdict = CreatorSovereignVerdict.CREATOR_REJECTED_REPLAY
        else:
            verdict = CreatorSovereignVerdict.CREATOR_ACCEPTED
            rejection_reason = None

        audit = CreatorSovereignAuditRecord(
            creator_id=envelope.creator_id,
            lineage_key=envelope.lineage_key,
            command=envelope.command,
            scope=envelope.scope.value,
            override_level=envelope.override_level.value,
            reason=envelope.reason,
            nonce=envelope.nonce,
            created_at=envelope.created_at,
            evaluated_at=evaluated_at,
            verdict=verdict,
            rejection_reason=rejection_reason,
        )
        return verdict, rejection_reason, audit

    def _verify_signature(self, envelope: CreatorSovereignEnvelope) -> bool:
        payload = envelope.canonical_payload()
        expected = hmac.new(
            self.signing_key, payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, envelope.root_signature)


# ── Convenience: build a verifier from a hex key string ───────────────────────

def verifier_from_hex_key(hex_key: str) -> CreatorSovereignVerifier:
    """Build a CreatorSovereignVerifier from a hex-encoded signing key."""
    return CreatorSovereignVerifier(signing_key=bytes.fromhex(hex_key))


# ── Audit log (in-memory, append-only during a process lifetime) ───────────────

_audit_lock = threading.Lock()
_audit_log: list[CreatorSovereignAuditRecord] = []


def append_audit(record: CreatorSovereignAuditRecord) -> None:
    with _audit_lock:
        _audit_log.append(record)


def audit_records() -> list[CreatorSovereignAuditRecord]:
    with _audit_lock:
        return list(_audit_log)
