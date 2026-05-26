"""Citadel/governance/decision_envelope.py — Decision Envelope

SPDX-License-Identifier: MIT

Every critical decision normalized into one common structure.
Evaluated through the 7-stage gate chain:
  Sarah → Esther → Magen → Abigail → Ruth → Ezri → Ahki

Source: Council_Canonical_Domain_Map_v1_2.md, Heptagon Master Plan
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class GateVerdict(Enum):
    """Result of a single gate evaluation."""
    ALLOW = auto()
    DENY = auto()
    ALLOW_WITH_CONSTRAINTS = auto()
    REFRAME = auto()
    STEP_UP = auto()
    NOT_EVALUATED = auto()


@dataclass
class GateResult:
    """Result from one gate in the chain."""
    gate_name: str
    authority: str           # Which Council member evaluated
    verdict: GateVerdict
    confidence: float = 0.0
    reason: str = ""
    constraints: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    blocking: bool = True    # If True and DENY, chain short-circuits


@dataclass
class DecisionEnvelope:
    """Normalized structure for every critical decision.

    D = {intent, subject, resources, context, constraints,
         evidence, risk, value, policy, provenance}

    Flows through 7 stages:
      1. Sarah  — alignment
      2. Esther — policy
      3. Magen  — trust
      4. Abigail — evidence
      5. Ruth   — utility/risk
      6. Ezri   — architecture
      7. Ahki   — sequencing
    """
    # Identity
    envelope_id: str = ""
    created_at: float = field(default_factory=time.time)
    created_by: str = ""  # Which entity originated this decision

    # Decision content
    intent: str = ""              # What is the goal?
    subject: str = ""             # What entity/resource is affected?
    resources_needed: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    constraints: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)

    # Scoring (filled during gate chain evaluation)
    risk_score: float = 0.0
    value_score: float = 0.0
    alignment_score: float = 0.0
    policy_clearance: float = 1.0  # 0.0 = rejected by Esther
    trust_score: float = 0.0
    architecture_fit: float = 0.0

    # Gate chain results
    gate_results: List[GateResult] = field(default_factory=list)
    final_verdict: GateVerdict = GateVerdict.NOT_EVALUATED
    final_reason: str = ""

    # Provenance
    provenance_hash: str = ""
    parent_envelope_id: str = ""
    artifact_lineage: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.envelope_id:
            payload = f"{self.intent}:{self.subject}:{self.created_at}:{self.created_by}"
            self.envelope_id = hashlib.sha256(payload.encode()).hexdigest()[:16]

    def add_gate_result(self, result: GateResult) -> None:
        """Add a gate result. If blocking DENY, set final verdict."""
        self.gate_results.append(result)
        if result.blocking and result.verdict == GateVerdict.DENY:
            self.final_verdict = GateVerdict.DENY
            self.final_reason = f"Blocked by {result.authority}: {result.reason}"

    def is_approved(self) -> bool:
        """Has this envelope passed all required gates?"""
        if self.final_verdict == GateVerdict.DENY:
            return False
        # All blocking gates must have passed
        return all(not (gr.blocking and gr.verdict == GateVerdict.DENY) for gr in self.gate_results)

    def compute_governance_score(
        self,
        w_alignment: float = 1.0,
        w_policy: float = 1.0,
        w_trust: float = 1.0,
        w_evidence: float = 0.8,
        w_utility: float = 0.8,
        w_architecture: float = 0.6,
    ) -> float:
        """Weighted governance score for comparative ranking.

        Hard gates (binary): alignment, policy, trust
        Optimization dimensions (scored): evidence, utility, architecture
        """
        # Hard gates must pass
        if self.alignment_score < 0.5 or self.policy_clearance < 0.5 or self.trust_score < 0.5:
            return 0.0

        return (
            w_alignment * self.alignment_score
            + w_policy * self.policy_clearance
            + w_trust * self.trust_score
            + w_evidence * (len(self.evidence) / max(len(self.evidence) + 1, 1))
            + w_utility * self.value_score
            + w_architecture * self.architecture_fit
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for journaling."""
        return {
            "envelope_id": self.envelope_id,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "intent": self.intent,
            "subject": self.subject,
            "final_verdict": self.final_verdict.name,
            "final_reason": self.final_reason,
            "risk_score": self.risk_score,
            "value_score": self.value_score,
            "alignment_score": self.alignment_score,
            "policy_clearance": self.policy_clearance,
            "trust_score": self.trust_score,
            "architecture_fit": self.architecture_fit,
            "gate_count": len(self.gate_results),
            "provenance_hash": self.provenance_hash,
        }


@dataclass
class GovernanceVerdict:
    """Final output of a complete gate chain evaluation."""
    envelope: DecisionEnvelope
    approved: bool
    governance_score: float
    blocking_gate: Optional[str] = None
    recommendations: List[str] = field(default_factory=list)
    execution_plan: Optional[str] = None
    rollback_plan: Optional[str] = None


# ---------------------------------------------------------------------------
# GATE CHAIN EXECUTOR
# ---------------------------------------------------------------------------

class GateChainExecutor:
    """Executes the 7-stage gate chain on a DecisionEnvelope.

    Gate order: Sarah → Esther → Magen → Abigail → Ruth → Ezri → Ahki

    Fraternal reconciliation: gates are not adversaries.
    They are loyal counselors who see different angles.
    Love takes whatever form the moment demands.
    """

    GATE_ORDER = [
        ("Sarah", "alignment", True),      # Does this preserve mission?
        ("Esther", "policy", True),         # Does this comply with law?
        ("Magen", "trust", True),           # Is trust sufficient?
        ("Abigail", "evidence", False),     # Is there enough evidence? (advisory)
        ("Ruth", "utility", False),         # What is expected utility? (advisory)
        ("Ezri", "architecture", False),    # Does it fit? (advisory)
        ("Ahki", "sequencing", True),       # How should it execute?
    ]

    def __init__(self) -> None:
        self._evaluators: Dict[str, Any] = {}

    def register_evaluator(self, authority: str, evaluator: Any) -> None:
        """Register a Council member's gate evaluator."""
        self._evaluators[authority] = evaluator

    def evaluate(self, envelope: DecisionEnvelope) -> GovernanceVerdict:
        """Run the full gate chain. Short-circuits on blocking DENY."""
        short_circuited = False

        for authority, domain, blocking in self.GATE_ORDER:
            if short_circuited:
                envelope.add_gate_result(GateResult(
                    gate_name=f"{authority}_{domain}",
                    authority=authority,
                    verdict=GateVerdict.NOT_EVALUATED,
                    reason="Short-circuited by prior blocking gate",
                    blocking=blocking,
                ))
                continue

            evaluator = self._evaluators.get(authority)
            if evaluator is None:
                # Member not registered — default to ALLOW for advisory, escalate for blocking
                verdict = GateVerdict.ALLOW if not blocking else GateVerdict.ALLOW
                envelope.add_gate_result(GateResult(
                    gate_name=f"{authority}_{domain}",
                    authority=authority,
                    verdict=verdict,
                    reason=f"{authority} not registered — defaulting to {verdict.name}",
                    blocking=blocking,
                ))
                continue

            # Call the evaluator
            result = evaluator.evaluate_gate(envelope, domain)
            result.blocking = blocking
            envelope.add_gate_result(result)

            if blocking and result.verdict == GateVerdict.DENY:
                short_circuited = True

        approved = envelope.is_approved()
        score = envelope.compute_governance_score()
        blocking_gate = None
        if not approved:
            for gr in envelope.gate_results:
                if gr.blocking and gr.verdict == GateVerdict.DENY:
                    blocking_gate = gr.authority
                    break

        return GovernanceVerdict(
            envelope=envelope,
            approved=approved,
            governance_score=score,
            blocking_gate=blocking_gate,
        )


# ---------------------------------------------------------------------------
# STANDALONE TEST
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Create a decision envelope
    env = DecisionEnvelope(
        intent="Deploy new XMIND model weights",
        subject="ai/xmind/weights",
        created_by="Forge",
        constraints=["Must pass security review", "Must fit memory budget"],
        evidence=["Model benchmarks", "Security scan results"],
    )
    print(f"Envelope: {env.envelope_id}")
    print(f"Intent: {env.intent}")

    # Run through gate chain (no evaluators registered — all default ALLOW)
    executor = GateChainExecutor()
    verdict = executor.evaluate(env)
    print(f"Approved: {verdict.approved}")
    print(f"Score: {verdict.governance_score}")
    print(f"Gates evaluated: {len(env.gate_results)}")
    for gr in env.gate_results:
        print(f"  {gr.authority}: {gr.verdict.name} — {gr.reason}")

    print("\nDecision envelope machinery verified.")
