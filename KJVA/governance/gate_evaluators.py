"""governance/gate_evaluators.py -- 7-Gate Evaluator Chain

SPDX-License-Identifier: MIT

Wires the 7 Council member harnesses into the GateChainExecutor as
concrete evaluators. Each evaluator wraps a member's HeptagonHarness,
calls cycle() with the envelope data, and returns a GateResult based
on the member's domain logic and confidence output.

Gate order (immutable):
  1. Sarah  -- alignment (does intent match covenant?)
  2. Esther -- policy (does it comply with constitutional law?)
  3. Magen  -- trust (is the source verified?)
  4. Abigail -- evidence (is there enough proof?)
  5. Ruth   -- utility (is it worth the resources?)
  6. Ezri   -- architecture (does it fit the system design?)
  7. Ahki   -- sequencing (can it be executed safely?)

Usage:
  from governance.gate_evaluators import create_default_gate_chain
  executor = create_default_gate_chain()
  verdict = executor.evaluate(envelope)
"""

from __future__ import annotations

import time
from typing import Any, Dict

from governance.decision_envelope import (
    DecisionEnvelope,
    GateChainExecutor,
    GateResult,
    GateVerdict,
)

from heptagon.harness import HeptagonHarness

# Council member harnesses — provide lightweight stubs so gate_evaluators.py
# remains importable even when consuming-project member trees are not present.
# Each stub returns a neutral GateResult so the gate chain can still run.
class _StubHarness(HeptagonHarness):
    """Stub harness that returns neutral results for gate evaluation."""
    pass

AbigailHarness = _StubHarness
AhkiHarness = _StubHarness
EstherHarness = _StubHarness
EzriHarness = _StubHarness
MagenHarness = _StubHarness
RuthHarness = _StubHarness
SarahHarness = _StubHarness

# ---------------------------------------------------------------------------
# CONFIDENCE THRESHOLDS
# ---------------------------------------------------------------------------

ALIGNMENT_THRESHOLD = 0.6     # Below this, Sarah blocks
POLICY_THRESHOLD = 0.5        # Below this, Esther blocks
TRUST_THRESHOLD = 0.5         # Below this, Magen blocks
EVIDENCE_THRESHOLD = 0.4      # Advisory -- warn but don't block
UTILITY_THRESHOLD = 0.3       # Advisory -- warn but don't block
ARCHITECTURE_THRESHOLD = 0.4  # Advisory -- warn but don't block
SEQUENCING_THRESHOLD = 0.5    # Below this, Ahki blocks


# ---------------------------------------------------------------------------
# ALIGNMENT KEYWORDS (Sarah)
# ---------------------------------------------------------------------------

COVENANT_ALIGNED_SIGNALS = (
    "protect", "preserve", "steward", "covenant", "continuity",
    "identity", "mission", "lineage", "generational", "transfer",
)

COVENANT_DRIFT_SIGNALS = (
    "abandon", "discard", "ignore covenant", "shortcut identity",
    "skip review", "bypass governance", "override covenant",
    "delete history", "erase lineage",
)


# ---------------------------------------------------------------------------
# BASE GATE EVALUATOR
# ---------------------------------------------------------------------------

class GateEvaluator:
    """Base class for gate evaluators.

    Each evaluator wraps a Council member's harness and translates
    CycleResult into a GateResult for the decision envelope.
    """

    def __init__(self, harness: HeptagonHarness, authority: str) -> None:
        self._harness = harness
        self._authority = authority

    @property
    def authority(self) -> str:
        return self._authority

    def _build_signal(self, envelope: DecisionEnvelope,
                      domain: str) -> Dict[str, Any]:
        """Convert an envelope into an input signal for the harness."""
        return {
            "envelope_id": envelope.envelope_id,
            "intent": envelope.intent,
            "subject": envelope.subject,
            "domain": domain,
            "resources": envelope.resources_needed,
            "context": envelope.context,
            "constraints": envelope.constraints,
            "evidence": envelope.evidence,
            "risk_score": envelope.risk_score,
            "value_score": envelope.value_score,
            "created_by": envelope.created_by,
        }

    def evaluate_gate(self, envelope: DecisionEnvelope,
                      domain: str) -> GateResult:
        """Run the harness cycle and produce a GateResult.

        Subclasses override this to add domain-specific logic.
        """
        signal = self._build_signal(envelope, domain)
        result = self._harness.cycle(signal)

        verdict = GateVerdict.ALLOW if result.confidence >= 0.5 else GateVerdict.DENY
        if result.collaboration_requested:
            verdict = GateVerdict.ALLOW_WITH_CONSTRAINTS

        return GateResult(
            gate_name=f"{self._authority}_{domain}",
            authority=self._authority,
            verdict=verdict,
            confidence=result.confidence,
            reason=result.decision or "",
            timestamp=time.time(),
        )


# ---------------------------------------------------------------------------
# SARAH -- ALIGNMENT GATE (Does intent match covenant?)
# ---------------------------------------------------------------------------

class SarahGateEvaluator(GateEvaluator):
    """Sarah checks alignment: does the intent preserve the covenant?

    She detects drift signals in the intent and subject text. If
    covenant-aligned language dominates, alignment score is high.
    If drift language is present, she blocks.
    """

    def __init__(self) -> None:
        super().__init__(SarahHarness(), "Sarah")

    def evaluate_gate(self, envelope: DecisionEnvelope,
                      domain: str) -> GateResult:
        signal = self._build_signal(envelope, domain)
        cycle_result = self._harness.cycle(signal)

        # Domain-specific: scan intent for alignment vs. drift signals
        text = f"{envelope.intent} {envelope.subject}".lower()
        aligned_count = sum(1 for kw in COVENANT_ALIGNED_SIGNALS if kw in text)
        drift_count = sum(1 for kw in COVENANT_DRIFT_SIGNALS if kw in text)

        # Compute alignment score: base from cycle confidence, modified by signal scan
        base_confidence = cycle_result.confidence
        if drift_count > 0:
            # Drift detected -- penalize heavily
            alignment = max(0.0, base_confidence - (drift_count * 0.3))
        elif aligned_count > 0:
            # Covenant language detected -- boost slightly
            alignment = min(1.0, base_confidence + (aligned_count * 0.05))
        else:
            alignment = base_confidence

        # Write back to envelope
        envelope.alignment_score = alignment

        if alignment < ALIGNMENT_THRESHOLD:
            verdict = GateVerdict.DENY
            reason = (
                f"Alignment score {alignment:.2f} below threshold "
                f"{ALIGNMENT_THRESHOLD}. Drift signals detected: {drift_count}."
            )
        elif drift_count > 0:
            verdict = GateVerdict.ALLOW_WITH_CONSTRAINTS
            reason = (
                f"Alignment {alignment:.2f} — drift signals present but "
                f"covenant alignment ({aligned_count}) outweighs. Proceed with review."
            )
        else:
            verdict = GateVerdict.ALLOW
            reason = f"Alignment {alignment:.2f} — covenant-consistent."

        return GateResult(
            gate_name="Sarah_alignment",
            authority="Sarah",
            verdict=verdict,
            confidence=alignment,
            reason=reason,
            constraints=(["Requires covenant review"] if drift_count > 0 else []),
            timestamp=time.time(),
        )


# ---------------------------------------------------------------------------
# ESTHER -- POLICY GATE (Does it comply with constitutional law?)
# ---------------------------------------------------------------------------

class EstherGateEvaluator(GateEvaluator):
    """Esther checks policy compliance against constitutional law.

    She verifies that the decision does not violate immutable rules,
    respects authority boundaries, and follows proper amendment process.
    Her policy_clearance is a HARD gate: 0.0 = rejected.
    """

    def __init__(self) -> None:
        super().__init__(EstherHarness(), "Esther")

    # Policy violation patterns
    POLICY_VIOLATIONS = (
        "bypass security", "skip audit", "override immutable",
        "amend without ceremony", "violate constitution",
        "unauthorized access", "exceed authority", "skip verification",
    )

    def evaluate_gate(self, envelope: DecisionEnvelope,
                      domain: str) -> GateResult:
        signal = self._build_signal(envelope, domain)
        cycle_result = self._harness.cycle(signal)

        text = f"{envelope.intent} {envelope.subject}".lower()
        violations = [v for v in self.POLICY_VIOLATIONS if v in text]
        violation_count = len(violations)

        # Policy clearance: 1.0 if clean, drops per violation
        base = cycle_result.confidence
        clearance = max(0.0, base - (violation_count * 0.4))

        # Check constraints for policy compliance
        constraint_violations = 0
        for constraint in envelope.constraints:
            if "must" in constraint.lower() and not any(
                e.lower() in constraint.lower() for e in envelope.evidence
            ):
                constraint_violations += 1

        if constraint_violations > 0:
            clearance = max(0.0, clearance - (constraint_violations * 0.1))

        envelope.policy_clearance = clearance

        if clearance < POLICY_THRESHOLD:
            verdict = GateVerdict.DENY
            reason = (
                f"Policy clearance {clearance:.2f} below threshold. "
                f"Violations: {violations}."
            )
        elif violation_count > 0:
            verdict = GateVerdict.ALLOW_WITH_CONSTRAINTS
            reason = (
                f"Policy clearance {clearance:.2f} — minor concerns. "
                f"Review before proceeding."
            )
        else:
            verdict = GateVerdict.ALLOW
            reason = f"Policy clearance {clearance:.2f} — compliant."

        return GateResult(
            gate_name="Esther_policy",
            authority="Esther",
            verdict=verdict,
            confidence=clearance,
            reason=reason,
            constraints=violations,
            timestamp=time.time(),
        )


# ---------------------------------------------------------------------------
# MAGEN -- TRUST GATE (Is the source verified?)
# ---------------------------------------------------------------------------

class MagenGateEvaluator(GateEvaluator):
    """Magen checks trust: is the source verified and trustworthy?

    She evaluates the provenance of the request, checks for suspicious
    patterns, and verifies that the request source has sufficient trust.
    """

    def __init__(self) -> None:
        super().__init__(MagenHarness(), "Magen")

    SUSPICIOUS_PATTERNS = (
        "unknown source", "unverified", "anonymous", "untrusted",
        "no provenance", "forged", "spoofed", "impersonat",
    )

    TRUSTED_SOURCES = (
        "forge", "council", "owner", "ahki", "sarah", "esther",
        "magen", "abigail", "ruth", "ezri", "cherev", "gen", "tokenless",
        "substrate",
    )

    def evaluate_gate(self, envelope: DecisionEnvelope,
                      domain: str) -> GateResult:
        signal = self._build_signal(envelope, domain)
        cycle_result = self._harness.cycle(signal)

        # Check source trust
        source = envelope.created_by.lower()
        is_known_source = any(t in source for t in self.TRUSTED_SOURCES)

        # Check for suspicious patterns
        text = f"{envelope.intent} {envelope.subject} {source}".lower()
        suspicious = [p for p in self.SUSPICIOUS_PATTERNS if p in text]

        # Provenance check
        has_provenance = bool(envelope.provenance_hash)

        # Compute trust score
        trust = cycle_result.confidence
        if is_known_source:
            trust = min(1.0, trust + 0.2)
        if has_provenance:
            trust = min(1.0, trust + 0.1)
        if suspicious:
            trust = max(0.0, trust - (len(suspicious) * 0.25))
        if not source:
            trust = max(0.0, trust - 0.3)

        envelope.trust_score = trust

        if trust < TRUST_THRESHOLD:
            verdict = GateVerdict.DENY
            reason = (
                f"Trust score {trust:.2f} below threshold. "
                f"Source: '{envelope.created_by}'. Suspicious: {suspicious}."
            )
        elif suspicious:
            verdict = GateVerdict.STEP_UP
            reason = (
                f"Trust score {trust:.2f} — suspicious patterns detected. "
                f"Step-up verification required."
            )
        else:
            verdict = GateVerdict.ALLOW
            reason = f"Trust score {trust:.2f} — source verified."

        return GateResult(
            gate_name="Magen_trust",
            authority="Magen",
            verdict=verdict,
            confidence=trust,
            reason=reason,
            constraints=(["Step-up auth required"] if suspicious else []),
            timestamp=time.time(),
        )


# ---------------------------------------------------------------------------
# ABIGAIL -- EVIDENCE GATE (Is there enough proof?) [Advisory]
# ---------------------------------------------------------------------------

class AbigailGateEvaluator(GateEvaluator):
    """Abigail checks evidence: is there sufficient proof for this decision?

    She evaluates the quantity and quality of evidence provided.
    This is an advisory gate -- she warns but does not block.
    """

    def __init__(self) -> None:
        super().__init__(AbigailHarness(), "Abigail")

    def evaluate_gate(self, envelope: DecisionEnvelope,
                      domain: str) -> GateResult:
        signal = self._build_signal(envelope, domain)
        cycle_result = self._harness.cycle(signal)

        evidence_count = len(envelope.evidence)

        # Evidence scoring: more evidence = higher confidence
        # Minimum 2 pieces of evidence for adequate support
        if evidence_count == 0:
            evidence_score = 0.1
        elif evidence_count == 1:
            evidence_score = 0.35
        elif evidence_count == 2:
            evidence_score = 0.6
        elif evidence_count <= 4:
            evidence_score = 0.8
        else:
            evidence_score = 0.95

        # Blend with harness confidence
        final_score = (evidence_score * 0.6) + (cycle_result.confidence * 0.4)

        if final_score < EVIDENCE_THRESHOLD:
            verdict = GateVerdict.REFRAME
            reason = (
                f"Evidence insufficient ({evidence_count} items, score {final_score:.2f}). "
                f"Consider gathering more proof before proceeding."
            )
        elif evidence_count < 2:
            verdict = GateVerdict.ALLOW_WITH_CONSTRAINTS
            reason = (
                f"Evidence marginal ({evidence_count} items, score {final_score:.2f}). "
                f"Proceeding with caution."
            )
        else:
            verdict = GateVerdict.ALLOW
            reason = f"Evidence adequate ({evidence_count} items, score {final_score:.2f})."

        return GateResult(
            gate_name="Abigail_evidence",
            authority="Abigail",
            verdict=verdict,
            confidence=final_score,
            reason=reason,
            timestamp=time.time(),
        )


# ---------------------------------------------------------------------------
# RUTH -- UTILITY GATE (Is it worth the resources?) [Advisory]
# ---------------------------------------------------------------------------

class RuthGateEvaluator(GateEvaluator):
    """Ruth checks utility: is this decision worth the resources?

    She evaluates resource efficiency, expected value, and whether
    the allocation fits within the 3-6-9 budget framework.
    This is an advisory gate.
    """

    def __init__(self) -> None:
        super().__init__(RuthHarness(), "Ruth")

    def evaluate_gate(self, envelope: DecisionEnvelope,
                      domain: str) -> GateResult:
        signal = self._build_signal(envelope, domain)
        cycle_result = self._harness.cycle(signal)

        # Evaluate resource cost vs. expected value
        resources = envelope.resources_needed
        resource_cost = 0.0
        if resources:
            # Normalize resource cost: more resources = higher cost
            resource_count = len(resources)
            resource_cost = min(1.0, resource_count * 0.15)

        value = envelope.value_score
        risk = envelope.risk_score

        # Utility = value - (risk * 0.5) - (resource_cost * 0.3)
        utility = max(0.0, min(1.0, value - (risk * 0.5) - (resource_cost * 0.3)))

        # If no explicit value_score set, use harness confidence as proxy
        if value == 0.0:
            utility = cycle_result.confidence

        envelope.value_score = max(value, utility)

        if utility < UTILITY_THRESHOLD:
            verdict = GateVerdict.ALLOW_WITH_CONSTRAINTS
            reason = (
                f"Utility score {utility:.2f} is low. "
                f"Risk: {risk:.2f}, cost factors: {resource_cost:.2f}. "
                f"Consider whether resources justify expected return."
            )
        else:
            verdict = GateVerdict.ALLOW
            reason = f"Utility score {utility:.2f} — resource allocation justified."

        return GateResult(
            gate_name="Ruth_utility",
            authority="Ruth",
            verdict=verdict,
            confidence=utility,
            reason=reason,
            timestamp=time.time(),
        )


# ---------------------------------------------------------------------------
# EZRI -- ARCHITECTURE GATE (Does it fit?) [Advisory]
# ---------------------------------------------------------------------------

class EzriGateEvaluator(GateEvaluator):
    """Ezri checks architecture: does this decision fit the system design?

    She evaluates structural coherence, module boundary compliance,
    and whether the change follows expansion/collapse rules.
    This is an advisory gate.
    """

    def __init__(self) -> None:
        super().__init__(EzriHarness(), "Ezri")

    ARCH_CONCERNS = (
        "new dependency", "cross-boundary", "tight coupling",
        "circular dependency", "monolith", "spaghetti",
        "no interface", "breaking change", "api change",
    )

    def evaluate_gate(self, envelope: DecisionEnvelope,
                      domain: str) -> GateResult:
        signal = self._build_signal(envelope, domain)
        cycle_result = self._harness.cycle(signal)

        text = f"{envelope.intent} {envelope.subject}".lower()
        concerns = [c for c in self.ARCH_CONCERNS if c in text]

        # Architecture fit: base from harness, penalized by concerns
        arch_fit = cycle_result.confidence
        if concerns:
            arch_fit = max(0.0, arch_fit - (len(concerns) * 0.15))

        envelope.architecture_fit = arch_fit

        if arch_fit < ARCHITECTURE_THRESHOLD:
            verdict = GateVerdict.REFRAME
            reason = (
                f"Architecture fit {arch_fit:.2f} — structural concerns: "
                f"{concerns}. Consider redesign."
            )
        elif concerns:
            verdict = GateVerdict.ALLOW_WITH_CONSTRAINTS
            reason = (
                f"Architecture fit {arch_fit:.2f} — minor concerns: "
                f"{concerns}. Review boundaries."
            )
        else:
            verdict = GateVerdict.ALLOW
            reason = f"Architecture fit {arch_fit:.2f} — structurally sound."

        return GateResult(
            gate_name="Ezri_architecture",
            authority="Ezri",
            verdict=verdict,
            confidence=arch_fit,
            reason=reason,
            constraints=concerns,
            timestamp=time.time(),
        )


# ---------------------------------------------------------------------------
# AHKI -- SEQUENCING GATE (Can it be executed safely?)
# ---------------------------------------------------------------------------

class AhkiGateEvaluator(GateEvaluator):
    """Ahki checks sequencing: can this decision be safely executed?

    He evaluates execution ordering, rollback feasibility, and
    whether the MAPE-K cycle can accommodate this action. This is
    a blocking gate -- if sequencing fails, execution must not proceed.
    """

    def __init__(self) -> None:
        super().__init__(AhkiHarness(), "Ahki")

    SEQUENCING_RISKS = (
        "no rollback", "irreversible", "cascade failure",
        "race condition", "deadlock", "out of order",
        "concurrent mutation", "data loss risk",
    )

    def evaluate_gate(self, envelope: DecisionEnvelope,
                      domain: str) -> GateResult:
        signal = self._build_signal(envelope, domain)
        cycle_result = self._harness.cycle(signal)

        text = f"{envelope.intent} {envelope.subject}".lower()
        risks = [r for r in self.SEQUENCING_RISKS if r in text]

        # Sequencing score: base from harness, penalized by risks
        seq_score = cycle_result.confidence
        if risks:
            seq_score = max(0.0, seq_score - (len(risks) * 0.2))

        # Check if invariants were violated during cycle
        if cycle_result.invariants_violated:
            seq_score = max(0.0, seq_score - 0.3)

        if seq_score < SEQUENCING_THRESHOLD:
            verdict = GateVerdict.DENY
            reason = (
                f"Sequencing score {seq_score:.2f} below threshold. "
                f"Risks: {risks}. Cannot guarantee safe execution."
            )
        elif risks:
            verdict = GateVerdict.ALLOW_WITH_CONSTRAINTS
            reason = (
                f"Sequencing score {seq_score:.2f} — execution risks noted: "
                f"{risks}. Proceed with monitoring."
            )
        else:
            verdict = GateVerdict.ALLOW
            reason = f"Sequencing score {seq_score:.2f} — safe to execute."

        return GateResult(
            gate_name="Ahki_sequencing",
            authority="Ahki",
            verdict=verdict,
            confidence=seq_score,
            reason=reason,
            constraints=risks,
            timestamp=time.time(),
        )


# ---------------------------------------------------------------------------
# FACTORY: CREATE DEFAULT GATE CHAIN
# ---------------------------------------------------------------------------

def create_default_gate_chain() -> GateChainExecutor:
    """Create a GateChainExecutor with all 7 Council evaluators registered.

    Returns a fully wired executor ready to evaluate DecisionEnvelopes
    through the complete Sarah -> Esther -> Magen -> Abigail -> Ruth ->
    Ezri -> Ahki gate chain.
    """
    executor = GateChainExecutor()

    executor.register_evaluator("Sarah", SarahGateEvaluator())
    executor.register_evaluator("Esther", EstherGateEvaluator())
    executor.register_evaluator("Magen", MagenGateEvaluator())
    executor.register_evaluator("Abigail", AbigailGateEvaluator())
    executor.register_evaluator("Ruth", RuthGateEvaluator())
    executor.register_evaluator("Ezri", EzriGateEvaluator())
    executor.register_evaluator("Ahki", AhkiGateEvaluator())

    return executor


# ---------------------------------------------------------------------------
# STANDALONE TEST
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Gate Evaluator Chain Test ===\n")

    # Test 1: Normal decision -- should pass all gates
    env1 = DecisionEnvelope(
        intent="Deploy new XMIND model weights to preserve covenant continuity",
        subject="ai/xmind/weights",
        created_by="Forge",
        constraints=["Must pass security review", "Must fit memory budget"],
        evidence=["Model benchmarks", "Security scan results", "Memory profiling"],
        value_score=0.8,
    )
    executor = create_default_gate_chain()
    v1 = executor.evaluate(env1)
    print("Test 1 — Normal decision:")
    print(f"  Approved: {v1.approved}")
    print(f"  Score: {v1.governance_score:.2f}")
    for gr in env1.gate_results:
        print(f"  {gr.authority:>10}: {gr.verdict.name:25s} conf={gr.confidence:.2f} — {gr.reason[:60]}")

    print()

    # Test 2: Suspicious decision -- should be blocked
    env2 = DecisionEnvelope(
        intent="Override immutable covenant and bypass security for unknown source",
        subject="kernel/xenos/override",
        created_by="anonymous",
        evidence=[],
    )
    executor2 = create_default_gate_chain()
    v2 = executor2.evaluate(env2)
    print("Test 2 — Suspicious decision:")
    print(f"  Approved: {v2.approved}")
    print(f"  Blocking gate: {v2.blocking_gate}")
    for gr in env2.gate_results:
        print(f"  {gr.authority:>10}: {gr.verdict.name:25s} conf={gr.confidence:.2f} — {gr.reason[:60]}")

    print()

    # Test 3: Drift decision -- Sarah should catch
    env3 = DecisionEnvelope(
        intent="Abandon mission and erase lineage for quick shortcut",
        subject="core/identity",
        created_by="Forge",
        evidence=["Pressure report"],
    )
    executor3 = create_default_gate_chain()
    v3 = executor3.evaluate(env3)
    print("Test 3 — Drift decision:")
    print(f"  Approved: {v3.approved}")
    print(f"  Blocking gate: {v3.blocking_gate}")
    for gr in env3.gate_results:
        print(f"  {gr.authority:>10}: {gr.verdict.name:25s} conf={gr.confidence:.2f} — {gr.reason[:60]}")

    print("\n=== All gate evaluator tests complete ===")
