# models/heptagon/__init__.py
# SPDX-License-Identifier: MIT
# The Heptagon Harness — 7-layer cognitive architecture
# "Everything must be done decently and in order."

from .layers import (
    OntologyLayer,
    SchemaLayer,
    KernelLayer,
    AdmissionEngine,
    WorkspaceAllocator,
    RouteSelector,
    ExecutionEngine,
    ConsolidationEngine,
    VerificationEngine,
    BudgetGovernor,
    CognitiveEngine,
    InstrumentationLayer,
    TraceRecord,
    EvaluationLayer,
    MetricDefinition,
    CalibrationLayer,
    TunableParameter,
    EnforcementLayer,
    Invariant,
)
from .registry import (
    EntityClass,
    CouncilRank,
    ImplementationStatus,
    BiblicalEmbodiment,
    MemberDescriptor,
    MEMBER_REGISTRY,
    OFFICE_REGISTRY,
    FORMULA_REGISTRY,
    COVENANT_REGISTRY,
    verify_registry,
)
from .harness import HeptagonHarness, CycleResult
from .attestation import AttestationEngine, AttestationResult, AttestationStatus
from .member_guard import MemberGuard, ThreatClass, ThreatSeverity, ThreatEvent

__all__ = [
    # Layers
    "OntologyLayer",
    "SchemaLayer",
    "KernelLayer",
    "InstrumentationLayer",
    "TraceRecord",
    "EvaluationLayer",
    "MetricDefinition",
    "CalibrationLayer",
    "TunableParameter",
    "EnforcementLayer",
    "Invariant",
    # Registry types
    "EntityClass",
    "CouncilRank",
    "ImplementationStatus",
    "BiblicalEmbodiment",
    "MemberDescriptor",
    "MEMBER_REGISTRY",
    "OFFICE_REGISTRY",
    "FORMULA_REGISTRY",
    "COVENANT_REGISTRY",
    "verify_registry",
    # Harness
    "HeptagonHarness",
    "CycleResult",
    # Attestation
    "AttestationEngine",
    "AttestationResult",
    "AttestationStatus",
    # Guard
    "MemberGuard",
    "ThreatClass",
    "ThreatSeverity",
    "ThreatEvent",
]
