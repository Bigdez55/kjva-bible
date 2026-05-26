"""Tokenless Models runtime contracts and training substrate.

Connection chain:
  heptagon/harness.py (HeptagonHarness base class)
      ->
  governance/covenant_enforcer.py (action gating)
      ->
  governance/decision_envelope.py (wraps all decisions)
      ->
  soul_manager/soul_manager.py (continuity/memory)
      ->
  ai/tokenless-agent/src/agent.py (main AI agent)
      ->
  ai/tokenless-agent/src/api.py (FastAPI endpoints)
"""
from __future__ import annotations

__version__ = "0.3.0"
__author__ = "Desmond Early"
__entity__ = "Tokenless_Models"

# ---------------------------------------------------------------------------
# Path bootstrap - ensure subpackages (heptagon/, governance/, soul_manager/)
# are importable regardless of how this package is loaded.
# ---------------------------------------------------------------------------
import os as _os
import sys as _sys

_PACKAGE_ROOT = _os.path.dirname(_os.path.abspath(__file__))
if _PACKAGE_ROOT not in _sys.path:
    _sys.path.insert(0, _PACKAGE_ROOT)


# ---------------------------------------------------------------------------
# Lazy imports to avoid circular dependency at module load time
# ---------------------------------------------------------------------------

def get_registry():
    """Return the legacy project registry, when available."""
    from heptagon.registry_nexus_saas import NEXUS_REGISTRY, verify_registry
    return NEXUS_REGISTRY, verify_registry


def get_formation_grammar():
    """Return local registry dataclasses and enums."""
    from heptagon.registry import (
        BiblicalEmbodiment,
        CouncilRank,
        EntityClass,
        ImplementationStatus,
        MemberDescriptor,
        COVENANT_REGISTRY,
        verify_registry as verify_tokenless_registry,
    )
    return {
        "BiblicalEmbodiment": BiblicalEmbodiment,
        "CouncilRank": CouncilRank,
        "EntityClass": EntityClass,
        "ImplementationStatus": ImplementationStatus,
        "MemberDescriptor": MemberDescriptor,
        "COVENANT_REGISTRY": COVENANT_REGISTRY,
        "verify_registry": verify_tokenless_registry,
    }


def get_harness():
    """Return HeptagonHarness base class."""
    from heptagon.harness import HeptagonHarness
    return HeptagonHarness


def get_layers():
    """Return the 7 Heptagon layer classes."""
    from heptagon.layers import (
        OntologyLayer, SchemaLayer, KernelLayer, InstrumentationLayer,
        EvaluationLayer, CalibrationLayer, EnforcementLayer,
    )
    return {
        "OntologyLayer": OntologyLayer,
        "SchemaLayer": SchemaLayer,
        "KernelLayer": KernelLayer,
        "InstrumentationLayer": InstrumentationLayer,
        "EvaluationLayer": EvaluationLayer,
        "CalibrationLayer": CalibrationLayer,
        "EnforcementLayer": EnforcementLayer,
    }


def get_covenant_enforcer():
    """Return CovenantEnforcer and related types."""
    from governance.covenant_enforcer import (
        CovenantEnforcer, EnforcementAction, EnforcementResult, CovenantViolation,
    )
    return CovenantEnforcer, EnforcementAction, EnforcementResult, CovenantViolation


def get_decision_envelope():
    """Return DecisionEnvelope and GateChainExecutor."""
    from governance.decision_envelope import (
        DecisionEnvelope, GateChainExecutor, GateResult, GateVerdict, GovernanceVerdict,
    )
    return DecisionEnvelope, GateChainExecutor, GateResult, GateVerdict, GovernanceVerdict


def get_soul_manager():
    """Return SoulManager class."""
    from soul_manager.soul_manager import SoulManager
    return SoulManager


def get_governance():
    """Return the full governance package."""
    import governance
    return governance
