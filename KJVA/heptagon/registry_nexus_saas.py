"""Legacy registry module for Tokenless project-specific descriptors.

The filename is retained for compatibility with older imports. New consuming
projects should define their own registry module locally.
"""
from __future__ import annotations

from typing import Dict

from .registry import (
    CouncilRank,
    EntityClass,
    ImplementationStatus,
    MemberDescriptor,
)

TOKENLESS_REGISTRY: Dict[str, MemberDescriptor] = {
    "TOKENLESS": MemberDescriptor(
        name="TOKENLESS",
        rank=CouncilRank.SUBSTRATE,
        entity_class=EntityClass.SUBSTRATE,
        canonical_domain="Tokenless model runtime",
        daemon_port=0,
        status=ImplementationStatus.LIVE,
        technical_jurisdictions=(
            "model export loading",
            "retrieval",
            "covenant checks",
            "Heptagon metadata",
            "signal logging",
        ),
        what_it_is_not=(
            "not a product identity",
            "not a consuming-project authority model",
        ),
    )
}

# Backward-compatible export name for older code.
NEXUS_REGISTRY = TOKENLESS_REGISTRY


def verify_registry() -> bool:
    """Return True when the compatibility registry has its required entry."""
    return "TOKENLESS" in TOKENLESS_REGISTRY
