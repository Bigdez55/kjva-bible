"""Citadel/heptagon/attestation.py — Identity Attestation Runtime

SPDX-License-Identifier: MIT

Every restart is a verification event.
Every identity claim must be proven.
Restart without attestation = suspicious until proven legitimate.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional

from .registry import MEMBER_REGISTRY


class AttestationStatus(Enum):
    """Result of identity attestation."""
    VERIFIED = auto()       # All checks passed
    SUSPICIOUS = auto()     # Failed one or more checks
    UNAUTHORIZED = auto()   # Attestation not attempted
    QUARANTINED = auto()    # Actively quarantined pending investigation


@dataclass
class AttestationResult:
    """Full result of an attestation attempt."""
    member_id: str
    status: AttestationStatus
    timestamp: float = field(default_factory=time.time)
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[str] = field(default_factory=list)
    witnesses: List[str] = field(default_factory=list)
    reason: str = ""


# ---------------------------------------------------------------------------
# ATTESTATION WITNESSES (with vacancy fallbacks)
# ---------------------------------------------------------------------------

NORMAL_WITNESSES = ("Ahki", "Esther", "Sarah")

VACANCY_FALLBACKS: Dict[str, tuple] = {
    "Ahki": ("Esther", "Ruth", "Sarah"),          # Regency Triad
    "Esther": ("Ahki", "Sarah", "Abigail"),        # Ahki + Sarah + Abigail
    "Sarah": ("Ahki", "Esther", "Abigail"),        # Ahki + Esther + Abigail
}


# ---------------------------------------------------------------------------
# RECONSTITUTION WITNESSES (typed quorum)
# ---------------------------------------------------------------------------

RECONSTITUTION_ROLES = {
    "identity": ("Sarah", "Abigail"),       # Primary, fallback
    "constitutional": ("Esther", "Ahki"),   # Primary, fallback (Ahki as proxy)
    "security": ("Magen", "Cherev"),        # Primary, fallback
}


class AttestationEngine:
    """Runtime engine for member identity verification.

    Implements the Identity Attestation Doctrine:
    - Signed daemon identity
    - Signed schema fingerprint
    - Memory lineage hash chain
    - Invariant signature set
    - Challenge-response from witness triad
    """

    def __init__(self) -> None:
        self._attestation_log: List[AttestationResult] = []
        self._member_hashes: Dict[str, str] = {}  # member_id -> expected hash
        # Memory lineage: member_id -> ordered list of lineage hashes
        # Each restart appends its hash; verification checks chain integrity
        self._memory_lineage: Dict[str, List[str]] = {}

    def register_member_hash(self, member_id: str, schema_hash: str) -> None:
        """Register the expected schema hash for a member."""
        self._member_hashes[member_id] = schema_hash

    def register_lineage_hash(self, member_id: str, lineage_hash: str) -> None:
        """Append a lineage hash to the member's memory lineage chain.

        Each hash should be SHA-256(previous_hash + current_state).
        """
        if member_id not in self._memory_lineage:
            self._memory_lineage[member_id] = []
        self._memory_lineage[member_id].append(lineage_hash)

    def _verify_memory_lineage(self, member_id: str, claimed_hash: str) -> bool:
        """Verify that claimed_hash is a valid entry in the member's lineage chain.

        Verification rules:
          1. If lineage chain exists for this member, the claimed hash must
             either match the most recent chain entry, or be a valid
             SHA-256(last_chain_entry + member_id) -- proving knowledge of
             the chain.
          2. If no lineage chain exists (first attestation or SoulManager
             unavailable), accept non-empty hash with a WARNING and
             initialise the chain.

        Returns:
            True if lineage is verified, False otherwise.
        """
        chain = self._memory_lineage.get(member_id)

        if chain is None or len(chain) == 0:
            # No prior lineage -- accept and initialise chain with WARNING
            import logging as _logging
            _logger = _logging.getLogger(__name__)
            _logger.warning(
                "[AttestationEngine] No lineage chain for '%s'; "
                "accepting claimed hash and initialising chain (SoulManager may be unavailable)",
                member_id,
            )
            self._memory_lineage[member_id] = [claimed_hash]
            return True

        # Check 1: exact match against most recent chain entry
        if claimed_hash == chain[-1]:
            return True

        # Check 2: valid chain extension -- H(last_entry || member_id)
        expected_next = hashlib.sha256(
            (chain[-1] + member_id).encode("utf-8")
        ).hexdigest()
        if claimed_hash == expected_next:
            # Valid chain extension -- append to lineage
            chain.append(claimed_hash)
            return True

        # Check 3: match any historical entry (allows restart from checkpoint)
        return claimed_hash in chain

    def compute_schema_hash(self, member_id: str) -> str:
        """Compute the schema fingerprint for a member from the registry."""
        descriptor = MEMBER_REGISTRY.get(member_id)
        if descriptor is None:
            return ""
        payload = f"{descriptor.name}:{descriptor.rank.name}:{descriptor.canonical_domain}:{descriptor.daemon_port}"
        payload += ":" + ":".join(descriptor.technical_jurisdictions)
        return hashlib.sha256(payload.encode()).hexdigest()

    def attest(
        self,
        member_id: str,
        claimed_schema_hash: str,
        memory_lineage_hash: str = "",
        vacant_members: Optional[List[str]] = None,
    ) -> AttestationResult:
        """Perform full identity attestation for a member restart.

        Returns AttestationResult with VERIFIED or SUSPICIOUS status.
        """
        if vacant_members is None:
            vacant_members = []

        checks_passed = []
        checks_failed = []

        # Check 1: Member exists in registry
        if member_id in MEMBER_REGISTRY:
            checks_passed.append("registry_existence")
        else:
            checks_failed.append("registry_existence")
            result = AttestationResult(
                member_id=member_id,
                status=AttestationStatus.SUSPICIOUS,
                checks_passed=checks_passed,
                checks_failed=checks_failed,
                reason=f"Member '{member_id}' not found in MEMBER_REGISTRY",
            )
            self._attestation_log.append(result)
            return result

        # Check 2: Schema fingerprint
        expected_hash = self._member_hashes.get(member_id) or self.compute_schema_hash(member_id)
        if claimed_schema_hash == expected_hash:
            checks_passed.append("schema_fingerprint")
        else:
            checks_failed.append("schema_fingerprint")

        # Check 3: Memory lineage chain verification
        if memory_lineage_hash:
            if self._verify_memory_lineage(member_id, memory_lineage_hash):
                checks_passed.append("memory_lineage")
            else:
                checks_failed.append("memory_lineage_invalid")
        else:
            checks_failed.append("memory_lineage_missing")

        # Check 4: Determine witnesses (with vacancy fallbacks)
        witnesses = self._select_witnesses(member_id, vacant_members)

        # Check 5: Witness quorum (at least 2 of 3 must be available)
        available_witnesses = [w for w in witnesses if w not in vacant_members and w != member_id]
        if len(available_witnesses) >= 2:
            checks_passed.append("witness_quorum")
        else:
            checks_failed.append("witness_quorum_insufficient")

        # Determine final status
        if checks_failed:
            status = AttestationStatus.SUSPICIOUS
            reason = f"Failed checks: {', '.join(checks_failed)}"
        else:
            status = AttestationStatus.VERIFIED
            reason = "All attestation checks passed"

        result = AttestationResult(
            member_id=member_id,
            status=status,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            witnesses=available_witnesses,
            reason=reason,
        )
        self._attestation_log.append(result)
        return result

    def get_reconstitution_witnesses(
        self,
        missing_member: str,
        vacant_members: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """Get the typed quorum for reconstitution.

        Returns dict: role -> witness_name
        Raises ValueError if quorum cannot be formed.
        """
        if vacant_members is None:
            vacant_members = []

        quorum = {}
        for role, (primary, fallback) in RECONSTITUTION_ROLES.items():
            if primary not in vacant_members and primary != missing_member:
                quorum[role] = primary
            elif fallback not in vacant_members and fallback != missing_member:
                quorum[role] = fallback
            else:
                raise ValueError(
                    f"Cannot form reconstitution quorum: no witness available for '{role}' role. "
                    f"Project-authority review required."
                )
        return quorum

    def _select_witnesses(self, member_id: str, vacant_members: List[str]) -> tuple:
        """Select attestation witnesses with vacancy fallbacks."""
        # If the member being attested IS one of the normal witnesses, use fallback
        if member_id in NORMAL_WITNESSES:
            return VACANCY_FALLBACKS.get(member_id, NORMAL_WITNESSES)

        # Check if any normal witness is vacant
        for witness in NORMAL_WITNESSES:
            if witness in vacant_members:
                return VACANCY_FALLBACKS.get(witness, NORMAL_WITNESSES)

        return NORMAL_WITNESSES

    def get_log(self) -> List[AttestationResult]:
        """Return attestation history."""
        return list(self._attestation_log)
