# ROOT `heptagon/` — consuming-project (Citadel/Council) reference, NOT neutral-substrate-active

> **Status (2026-06-04): reference-only.** The live, neutral **Cognitive Control System**
> (ADR-0002 §3) is `ai/tokenless-agent/src/heptagon/`. `import heptagon` resolves src-first to
> that neutral package; the runtime never imports this ROOT one.

This directory is the **Citadel/Council** project's Cognitive Control implementation
(named-member governance: `registry.py`, `member_guard.py`, `vacancy_matrix.py`,
`attestation.py`, `registry_nexus_saas.py`, `harness.py`, `layers.py`) — **project-specific
content** (174 named-member references), which **ADR-0001 §1 bars from the neutral substrate**.

## Kept (not deleted), not wired (no redundancy) — owner directive 2026-06-04

*"Neutralize and absorb the generalizable parts, but without redundancy."* An audit found ROOT
heptagon's neutral engine concepts are **already implemented non-redundantly in the agent-side
package**: `layers.py` BudgetGovernor→`budget.py`, ConsolidationEngine→`consolidation.py`,
CalibrationLayer→`calibration.py`, VerificationEngine→`verification.py`,
EnforcementLayer/`harness.py`→`enforcement.py` + the agent loop, RouteSelector→`route_engine.py`.
So absorbing `layers.py`/`harness.py` would be redundant (and they encode a different
Citadel-specific taxonomy, not the ADR-0001 seven-layer model).

The **one** genuinely generalizable, non-redundant capability — the identity-**continuity hash
chain** from `attestation.py` — was **neutralized and absorbed** into
`ai/tokenless-agent/src/heptagon/attestation.py` (`ContinuityAttestation`, no named members).

The remainder is nothing but named-member specifics; its home is the consuming Citadel/Council
project, not this neutral base. Kept here as reference (git history); do **not** import into the
neutral runtime.

---

(Original note) Keep the cognitive cycle portable. Agent names and product-specific policy
should be injected by the consuming project or server configuration.
