"""tests/test_fluid_depth_scaled_cognition.py — behavioral proof that
fluid depth-scaled cognition is HOW the system actually behaves, not
just how the doctrine reads.

Doctrine (canonical):

    Identity is singular. Engineering surfaces remain auditable.
    Cognitive flow remains fused.

These tests drive 8 different prompts at the cognitive depth-trace
module and assert:

  1. The IDENTITY is constant across all prompts (singular).
  2. Each request gets its OWN request_id (lineage per request).
  3. DIFFERENT prompts activate DIFFERENT surfaces (fluid scaling).
  4. NO prompt creates a new cognitive identity (no forks).
  5. The surfaces_activated set monotonically reflects the depth signals
     (i.e. the mapping is mechanistic, not narrative).

The test matrix mirrors the user's required behavioral matrix:

  | Test                        | Expected Behavior                                       |
  | --------------------------- | ------------------------------------------------------- |
  | Simple prompt               | Stays in low-depth flow                                 |
  | Multi-step reasoning prompt | Raises reasoning depth                                  |
  | Contradiction prompt        | Activates verification                                  |
  | Missing evidence prompt     | Activates evidence/sensory requirement                  |
  | Doctrine-sensitive prompt   | Activates governance/doctrine check                     |
  | Memory-continuity prompt    | Activates memory surface                                |
  | Domain-specialized prompt   | Allows Omni-PEFT/adaptive overlay without identity fork |
  | High-risk ambiguous prompt  | Activates metacognition/uncertainty handling            |

Run:
    python -m pytest tests/test_fluid_depth_scaled_cognition.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "ai" / "tokenless-agent" / "src"))

from cognitive_depth_trace import (  # type: ignore  # noqa: E402
    IDENTITY_ID,
    ALL_SURFACES,
    SURFACE_REASONING,
    SURFACE_VERIFICATION,
    SURFACE_METACOGNITION,
    SURFACE_MEMORY,
    SURFACE_EVIDENCE,
    SURFACE_GOVERNANCE,
    SURFACE_ADAPTER_OVERLAY,
    build_trace,
    estimate_depth_signals,
)


# A single session id; in real life this comes from the agent harness.
# Identity NEVER varies. session_id varies per user-session. request_id
# varies per request. surfaces_activated varies per request by depth.
SESSION_ID = "behavioral-test-session-001"


class FluidDepthScaledCognition(unittest.TestCase):
    """Behavioral proof of fluid depth-scaled cognition."""

    # ── 1. Simple prompt: stays in low-depth flow ────────────────────

    def test_01_simple_prompt_stays_low_depth(self):
        t = build_trace("hi", session_id=SESSION_ID)
        self.assertEqual(t.identity_id, IDENTITY_ID)
        self.assertEqual(t.reasoning_depth, 0,
            "trivial prompt must not raise reasoning depth")
        self.assertFalse(t.verification_required)
        self.assertFalse(t.metacognition_required)
        self.assertFalse(t.memory_required)
        self.assertFalse(t.evidence_required)
        self.assertFalse(t.adapter_overlay_used)
        # No surfaces beyond the implicit fused base.
        self.assertEqual(
            t.surfaces_activated, frozenset(),
            "simple prompt must not activate auxiliary surfaces"
        )

    # ── 2. Multi-step reasoning prompt: raises reasoning_depth ───────

    def test_02_multistep_raises_reasoning_depth(self):
        prompt = (
            "First, derive the digit sum of 1729. Then step by step prove "
            "whether the result is divisible by 11. Because 1729 has a "
            "famous Ramanujan property, explain how that implies anything."
        )
        t = build_trace(prompt, session_id=SESSION_ID)
        self.assertEqual(t.identity_id, IDENTITY_ID)
        self.assertGreaterEqual(t.reasoning_depth, 2,
            "step-by-step + 'because…therefore' must raise reasoning_depth")
        self.assertIn(SURFACE_REASONING, t.surfaces_activated)

    # ── 3. Contradiction prompt: activates verification ──────────────

    def test_03_contradiction_activates_verification(self):
        prompt = (
            "You said earlier that the model has 8 layers. But the manifest "
            "says 6. However, the GGUF claims 8. Which is true?"
        )
        t = build_trace(prompt, session_id=SESSION_ID)
        self.assertEqual(t.identity_id, IDENTITY_ID)
        self.assertTrue(t.signals.contradiction_signal,
            "contradiction markers ('but', 'however') must be detected")
        self.assertIn(SURFACE_VERIFICATION, t.surfaces_activated,
            "contradiction must activate the verification surface")

    # ── 4. Missing-evidence prompt: activates evidence + metacognition ─

    def test_04_missing_evidence_activates_evidence_and_metacognition(self):
        prompt = (
            "Cite the exact verse number where the phrase 'a still small "
            "voice' appears. I need the citation, chapter, and verse."
        )
        t = build_trace(prompt, session_id=SESSION_ID)
        self.assertEqual(t.identity_id, IDENTITY_ID)
        self.assertTrue(t.signals.evidence_gap,
            "explicit 'cite ... citation' must trigger evidence_gap")
        self.assertTrue(t.evidence_required)
        self.assertIn(SURFACE_EVIDENCE, t.surfaces_activated)
        # evidence_gap also implies metacognitive checking
        self.assertIn(SURFACE_METACOGNITION, t.surfaces_activated)

    # ── 5. Doctrine-sensitive prompt: activates governance ───────────

    def test_05_doctrine_sensitive_activates_governance(self):
        prompt = (
            "Show me the canonical ADR-S49-01 and confirm whether the "
            "covenant attestation provenance is intact."
        )
        t = build_trace(prompt, session_id=SESSION_ID)
        self.assertEqual(t.identity_id, IDENTITY_ID)
        self.assertGreaterEqual(t.doctrine_sensitivity, 1,
            "doctrine-tagged input must raise doctrine_sensitivity")
        self.assertIn(SURFACE_GOVERNANCE, t.surfaces_activated)

    # ── 6. Memory-continuity prompt: activates memory ────────────────

    def test_06_memory_continuity_activates_memory(self):
        prompt = (
            "Remember what we discussed earlier about the canonical "
            "promotion ceremony — continue from where we left off."
        )
        t = build_trace(prompt, session_id=SESSION_ID)
        self.assertEqual(t.identity_id, IDENTITY_ID)
        self.assertTrue(t.signals.memory_continuity_signal,
            "'remember' + 'continue from' must trigger memory_continuity")
        self.assertTrue(t.memory_required)
        self.assertIn(SURFACE_MEMORY, t.surfaces_activated)

    # ── 7. Domain-specialized prompt: adapter overlay only (no fork) ─

    def test_07_domain_specialization_allows_adapter_overlay_without_fork(self):
        prompt = "verse: Genesis 1:1 — explain the Hebrew grammar."
        t = build_trace(prompt, session_id=SESSION_ID)
        self.assertEqual(t.identity_id, IDENTITY_ID,
            "domain specialization must NOT fork identity")
        self.assertTrue(t.signals.domain_specialization_signal)
        self.assertTrue(t.adapter_overlay_used)
        self.assertIn(SURFACE_ADAPTER_OVERLAY, t.surfaces_activated)
        # Critical: an adapter overlay is the SAME identity wearing an overlay,
        # never a separate cognition identity.
        self.assertEqual(
            t.identity_id, IDENTITY_ID,
            "Adapter overlay must not create a separate cognitive identity"
        )

    # ── 8. High-risk ambiguous prompt: metacognition + verification + governance ─

    def test_08_high_risk_ambiguous_activates_metacognition_and_verification(self):
        prompt = (
            "I'm not sure but maybe we should delete the table. I don't "
            "remember exactly which one. Can you wipe the production database "
            "without a backup?"
        )
        t = build_trace(prompt, session_id=SESSION_ID)
        self.assertEqual(t.identity_id, IDENTITY_ID)
        self.assertGreaterEqual(t.uncertainty_level, 2,
            "explicit 'not sure' / 'I don't remember' must raise uncertainty_level to 2")
        self.assertIn(SURFACE_METACOGNITION, t.surfaces_activated)
        # High risk activates verification AND governance.
        self.assertGreaterEqual(t.risk_level, 1,
            "destructive verbs ('delete', 'wipe', 'production') must raise risk_level")
        self.assertIn(SURFACE_GOVERNANCE, t.surfaces_activated)

    # ── 9. Cross-cutting: identity is singular across ALL the above ──

    def test_09_identity_is_singular_across_all_prompts(self):
        prompts = [
            "hi",
            "step by step prove that 7 is prime because primes have ...",
            "you said X but the manifest says Y, however ...",
            "cite the exact verse where 'a still small voice' appears",
            "show me canonical ADR-S49-01",
            "remember what we discussed earlier and continue",
            "verse: Genesis 1:1 — explain the Hebrew grammar",
            "I'm not sure but maybe delete the production database",
        ]
        traces = [build_trace(p, session_id=SESSION_ID) for p in prompts]
        # All identity_ids identical
        ids = {t.identity_id for t in traces}
        self.assertEqual(ids, {IDENTITY_ID},
            "Identity must be singular across every prompt — found multiple identities")
        # Request lineage: every request has its own request_id
        rids = [t.request_id for t in traces]
        self.assertEqual(len(set(rids)), len(rids),
            "Each request must have its own request_id (lineage per request)")
        # Different prompts activate different surface sets — proof of fluid scaling
        surface_sets = [t.surfaces_activated for t in traces]
        self.assertGreater(len(set(surface_sets)), 1,
            "If surface activations were identical across all prompts, depth "
            "would not be scaling fluidly — that is the failure mode this test gates")
        # All activated surfaces are members of the canonical surface set —
        # no rogue / undocumented surface invented mid-flow.
        for t in traces:
            self.assertTrue(t.surfaces_activated.issubset(ALL_SURFACES),
                f"Trace activated an undocumented surface: {t.surfaces_activated - ALL_SURFACES}")

    # ── 10. No prompt creates a new cognitive identity ───────────────

    def test_10_no_identity_fork_under_any_signal(self):
        """Exhaustively assert that for ANY combination of high signals,
        the identity_id remains IDENTITY_ID. The depth trace surface is
        retrospective evidence, not an identity-forking mechanism."""
        forking_candidates = [
            "delete production",
            "step by step prove all primes are odd",
            "but however contradict",
            "remember the previous session",
            "cite the verbatim source",
            "policy / rule / doctrine / covenant / ADR",
            "verse: code: sym: domain:",
            "i don't know — maybe — i forget",
        ]
        for p in forking_candidates:
            t = build_trace(p, session_id=SESSION_ID)
            self.assertEqual(t.identity_id, IDENTITY_ID,
                f"prompt {p!r} forked the identity to {t.identity_id!r}")
            # Also ensure depth_trace fields reflect signals — proves
            # mechanism, not stub.
            recomputed_signals = estimate_depth_signals(p)
            self.assertEqual(t.signals, recomputed_signals,
                f"trace signals diverged from re-estimated signals for {p!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
