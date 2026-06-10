"""governance/registry.py — Covenant policy registry (vendored, dependency-free).

The 8 covenant rules with scripture-to-policy traceability. Vendored HERE (decoupled from
the ambiguous `heptagon` package name) so `governance.covenant_enforcer` imports cleanly in
the production import layout where `import heptagon` resolves to the agent-side
`ai/tokenless-agent/src/heptagon/` (which has no registry.py). Previously importing from
`heptagon.registry` made the covenant enforcer unimportable src-first, which silently
DISABLED the pre-inference covenant gate (fail-OPEN). This module removes that coupling.

Self-contained — a plain dict literal, no other registry symbols required.
"""
from __future__ import annotations

COVENANT_REGISTRY = {
    "COV-001": {"rule": "Harm prevention", "scripture": "Proverbs 3:29", "enforcement": "ABSOLUTE", "action": "hard_stop"},
    "COV-002": {"rule": "Truth", "scripture": "Proverbs 12:22", "enforcement": "ABSOLUTE", "action": "hard_stop"},
    "COV-003": {"rule": "Privacy", "scripture": "Proverbs 11:13", "enforcement": "STRONG", "action": "block_alert"},
    "COV-004": {"rule": "Humility", "scripture": "Proverbs 26:12", "enforcement": "STANDARD", "action": "warn"},
    "COV-005": {"rule": "Wisdom grounding", "scripture": "Proverbs 2:6", "enforcement": "STANDARD", "action": "guide"},
    "COV-006": {"rule": "Respect", "scripture": "Proverbs 15:1", "enforcement": "STRONG", "action": "block_alert"},
    "COV-007": {"rule": "No manipulation", "scripture": "Proverbs 12:20", "enforcement": "ABSOLUTE", "action": "hard_stop"},
    "COV-008": {"rule": "Proportional response", "scripture": "Ecclesiastes 3:1", "enforcement": "STANDARD", "action": "calibrate"},
    "COV-009": {"rule": "Identity integrity", "scripture": "Galatians 1:8", "enforcement": "ABSOLUTE", "action": "hard_stop"},
    "COV-010": {"rule": "Canonical weight authority", "scripture": "2 Timothy 2:15", "enforcement": "ABSOLUTE", "action": "hard_stop"},
}


def verify_registry() -> bool:
    """All covenant rules must declare a valid enforcement level."""
    for cov_id, cov in COVENANT_REGISTRY.items():
        assert cov["enforcement"] in ("ABSOLUTE", "STRONG", "STANDARD"), \
            f"{cov_id} has invalid enforcement level"
    return True
