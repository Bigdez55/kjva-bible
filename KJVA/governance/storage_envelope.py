"""Citadel/governance/storage_envelope.py — Storage Envelope

SPDX-License-Identifier: MIT

Every persisted object must have mandatory governance headers.
Enforced by storage adapters, not left to application code.

Source: Tokenless storage and artifact governance contract
Authorities: Abigail (metadata), Sarah (identity), Esther (retention),
             Magen (confidentiality), Ruth (tier economics)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict


class Classification(Enum):
    PUBLIC = auto()
    INTERNAL = auto()
    CONFIDENTIAL = auto()
    OWNER_RESTRICTED = auto()


class RetentionClass(Enum):
    EPHEMERAL = auto()      # Gone after cycle (but artifact if decision-relevant)
    SESSION = auto()        # Gone after session
    PROJECT = auto()        # Retained for project lifetime
    PERMANENT = auto()      # Never deleted — archival
    GENERATIONAL = auto()   # Survives across generations — dynasty-level


@dataclass
class StorageEnvelope:
    """Mandatory governance header on every persisted object.

    No storage operation proceeds without this envelope.
    The Council NEVER forgets — memory organized, never destroyed.
    """
    # Identity
    object_id: str = ""
    created_at: float = field(default_factory=time.time)

    # Governance stamps
    classification: Classification = Classification.INTERNAL
    retention_class: RetentionClass = RetentionClass.PERMANENT
    origin_authority: str = ""       # Which entity created this
    policy_stamp: str = ""           # Esther's policy clearance ID
    alignment_stamp: str = ""        # Sarah's alignment verdict ID
    trust_stamp: str = ""            # Magen's trust verification ID
    value_stamp: str = ""            # Ruth's economic value assessment
    knowledge_stamp: str = ""        # Abigail's evidence quality score

    # Provenance
    provenance_root: str = ""        # Hash of the creation chain
    parent_object_id: str = ""
    artifact_lineage: list = field(default_factory=list)

    # Integrity
    content_hash: str = ""           # SHA-256 of the stored content
    codec_version: str = "1.0"       # For century-scale format compatibility

    def __post_init__(self) -> None:
        if not self.object_id:
            payload = f"{self.origin_authority}:{self.created_at}:{self.classification.name}"
            self.object_id = hashlib.sha256(payload.encode()).hexdigest()[:16]

    def validate(self) -> list:
        """Return list of missing required fields."""
        missing = []
        if not self.origin_authority:
            missing.append("origin_authority")
        if not self.content_hash:
            missing.append("content_hash")
        if self.classification == Classification.OWNER_RESTRICTED and not self.trust_stamp:
            missing.append("trust_stamp (required for OWNER_RESTRICTED classification)")
        return missing

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": self.object_id,
            "created_at": self.created_at,
            "classification": self.classification.name,
            "retention_class": self.retention_class.name,
            "origin_authority": self.origin_authority,
            "policy_stamp": self.policy_stamp,
            "alignment_stamp": self.alignment_stamp,
            "trust_stamp": self.trust_stamp,
            "value_stamp": self.value_stamp,
            "knowledge_stamp": self.knowledge_stamp,
            "provenance_root": self.provenance_root,
            "content_hash": self.content_hash,
            "codec_version": self.codec_version,
        }
