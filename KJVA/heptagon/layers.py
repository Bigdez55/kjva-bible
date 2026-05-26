"""Citadel/heptagon/layers.py — The 7 Layers of the Heptagon Harness

SPDX-License-Identifier: MIT

Each Council member instantiates all 7 layers with different specializations.
Same skeleton, radically different mind.

Source: heptagon_unified_model_spec.json
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# L1: ONTOLOGY — What the entity IS
# ---------------------------------------------------------------------------

@dataclass
class OntologyLayer:
    """L1: Identity, knowledge base, foundational commitments."""
    member_id: str
    identity_statement: str = ""
    knowledge_domains: List[str] = field(default_factory=list)
    foundational_commitments: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# L2: SCHEMA — How the entity is addressed
# ---------------------------------------------------------------------------

@dataclass
class SchemaLayer:
    """L2: Node addressing, type system, region structure."""
    member_id: str
    region_id: str = ""           # e.g., "R3.MEM" for Abigail
    sub_regions: List[str] = field(default_factory=list)  # up to 7
    node_contract_fields: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# L3: KERNEL — How the entity RUNS (7 sub-engines)
# ---------------------------------------------------------------------------

@dataclass
class AdmissionEngine:
    """L3.1: What signals get admitted into awareness."""
    security_penalty_weight: float = 1.0
    policy_clearance_required: bool = True

@dataclass
class WorkspaceAllocator:
    """L3.2: What stays focused vs dormant."""
    max_focused_nodes: int = 7

@dataclass
class RouteSelector:
    """L3.3: How work is routed."""
    route_types: List[str] = field(default_factory=lambda: [
        "DIRECT", "RESEARCHED", "CREATIVE", "ANALYTICAL",
        "EXECUTIVE", "DELEGATED", "ESCALATED",
    ])

@dataclass
class ExecutionEngine:
    """L3.4: How actions are performed."""
    max_actions_per_cycle: int = 10

@dataclass
class ConsolidationEngine:
    """L3.5: How memory is organized (Event→Episode→Semantic→Archive).
    NOTHING is ever deleted. Only reorganized by retrieval priority.
    """
    promotion_threshold: float = 0.80
    revision_pressure_threshold: float = 0.50
    consolidation_window_cycles: int = 50

@dataclass
class VerificationEngine:
    """L3.6: When to halt and verify."""
    coverage_threshold: float = 0.85
    contradiction_tolerance: int = 2
    coherence_threshold: float = 0.80

@dataclass
class BudgetGovernor:
    """L3.7: Resource allocation (3-6-9 normalized).
    route = 3/18 (16.7%), structure = 6/18 (33.3%), memory = 9/18 (50.0%)
    """
    route_weight: float = 3.0 / 18.0
    structure_weight: float = 6.0 / 18.0
    memory_weight: float = 9.0 / 18.0
    degradation_threshold: float = 0.85

@dataclass
class CognitiveEngine:
    """L3.8: R1_PER perception pipeline monitoring.

    Monitors the fidelity of the R1_PER semantic encoder — the component
    that converts natural language input to typed XCOG binary opcodes.

    The framing is load-bearing: R1_PER performs LOSSLESS semantic encoding.
    Any quality degradation is a BUG, not a tradeoff.  The fidelity check
    compares deterministic C parser output against neural encoder output;
    divergence triggers L5.2 escalation, not silent degradation.
    """
    fidelity_check_enabled: bool = True
    fidelity_check_interval: int = 50    # every N inference cycles
    fallback_threshold: float = 0.60     # confidence below this → raw text
    escalation_threshold: float = 0.15   # L5.2 correlation deviation tolerance
    default_intent: str = "QUERY"        # safe default on parse failure (never COMMAND)

@dataclass
class KernelLayer:
    """L3: The 7+1 sub-engines that drive cognitive processing."""
    member_id: str
    admission: AdmissionEngine = field(default_factory=AdmissionEngine)
    workspace: WorkspaceAllocator = field(default_factory=WorkspaceAllocator)
    route_selector: RouteSelector = field(default_factory=RouteSelector)
    execution: ExecutionEngine = field(default_factory=ExecutionEngine)
    consolidation: ConsolidationEngine = field(default_factory=ConsolidationEngine)
    verification: VerificationEngine = field(default_factory=VerificationEngine)
    budget: BudgetGovernor = field(default_factory=BudgetGovernor)
    cognitive: CognitiveEngine = field(default_factory=CognitiveEngine)


# ---------------------------------------------------------------------------
# L4: INSTRUMENTATION — What gets recorded
# ---------------------------------------------------------------------------

@dataclass
class TraceRecord:
    """A single trace entry emitted during a cognitive cycle."""
    cycle_number: int = 0
    phase: str = ""
    member_id: str = ""
    action: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    state_snapshot_hash: str = ""

@dataclass
class InstrumentationLayer:
    """L4: Trace emission. Every action produces a conforming trace."""
    traces: List[TraceRecord] = field(default_factory=list)
    completeness_rule: str = "every admission, route, expansion, consolidation, and halt must produce a trace"

    def emit(self, record: TraceRecord) -> None:
        self.traces.append(record)


# ---------------------------------------------------------------------------
# L5: EVALUATION — What measurements mean
# ---------------------------------------------------------------------------

@dataclass
class MetricDefinition:
    """A single metric with its target and anti-Goodhart pair."""
    name: str
    target: float
    current: float = 0.0
    anti_goodhart_pair: str = ""  # Which other metric to check for divergence

@dataclass
class EvaluationLayer:
    """L5: Metrics and anti-Goodhart divergence detection."""
    metrics: List[MetricDefinition] = field(default_factory=list)

    def check_divergence(self) -> List[str]:
        """Return list of metric pairs where divergence is detected."""
        warnings = []
        for m in self.metrics:
            if m.anti_goodhart_pair:
                pair = next((p for p in self.metrics if p.name == m.anti_goodhart_pair), None)
                if pair and m.current >= m.target and pair.current < pair.target:
                    warnings.append(
                        f"DIVERGENCE: {m.name} looks good ({m.current:.2f}) "
                        f"but {pair.name} is poor ({pair.current:.2f})"
                    )
        return warnings


# ---------------------------------------------------------------------------
# L6: CALIBRATION — How parameters adjust
# ---------------------------------------------------------------------------

@dataclass
class TunableParameter:
    """A parameter that can be adjusted within bounds."""
    name: str
    current: float
    floor: float
    ceiling: float
    category: str = "BOUNDED"  # BOUNDED, FREE, IMMUTABLE

    def adjust(self, delta: float) -> bool:
        """Adjust parameter by delta. Returns False if out of bounds."""
        new_value = self.current + delta
        if self.category == "IMMUTABLE":
            return False
        if self.category == "BOUNDED" and not (self.floor <= new_value <= self.ceiling):
            return False
        self.current = new_value
        return True

@dataclass
class CalibrationLayer:
    """L6: Tunables with bounds. The ONLY layer that writes back into L3."""
    tunables: List[TunableParameter] = field(default_factory=list)
    max_swing_per_cycle: float = 0.05  # Cannot change more than 5% per cycle
    stabilization_window: int = 3      # Cycles between adjustments


# ---------------------------------------------------------------------------
# L7: ENFORCEMENT — What invariants must hold
# ---------------------------------------------------------------------------

@dataclass
class Invariant:
    """A single invariant with enforcement behavior."""
    invariant_id: str
    description: str
    enforcement: str = "hard_stop"  # hard_stop, warn, kill, block_alert
    last_check_passed: bool = True

@dataclass
class EnforcementLayer:
    """L7: Invariant registry with enforcement. If violated, system responds."""
    invariants: List[Invariant] = field(default_factory=list)

    def check_all(self) -> List[Invariant]:
        """Return list of violated invariants."""
        return [inv for inv in self.invariants if not inv.last_check_passed]
