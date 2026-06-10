# ADR-S49-02 — TokenlessAgentWithHeptagon ↔ GenesysAgentWithHeptagon Name Reconciliation

## Status
Accepted (2026-05-30).

## Context
`UNIFIED_MASTER_TECH_PACK.md` Part 0.2 item #10 lists
`GenesysAgentWithHeptagon` as the active-taxonomy class for the Python
agent wrapping the base agent lifecycle, Omni-PEFT OS, and R1_PER. The
actual code class is `TokenlessAgentWithHeptagon` (per the Tokenless
rebranding documented in `TOKENLESS_DECLARATION.md`). Both names must
resolve so that:

1. Master-spec contract checks for `GenesysAgentWithHeptagon` succeed,
   preserving the canonical taxonomy from the seven source documents
   (Apex §1, Sovereignty LOCK-001, Spec §11 Layer 2).
2. Existing imports of `TokenlessAgentWithHeptagon` continue to work
   unchanged.

## Decision
Provide a module-scope alias in
`ai/tokenless-agent/src/agent.py`:

```python
GenesysAgentWithHeptagon = TokenlessAgentWithHeptagon  # type: ignore[misc]
```

Add `GenesysAgentWithHeptagon` to `__all__` so it is part of the package's
public surface.

## Consequences
- Master Part 0.2 active-taxonomy item #10 is satisfied
  (`from agent import GenesysAgentWithHeptagon` works).
- Existing code using `TokenlessAgentWithHeptagon` is unaffected (same
  class object).
- New code SHOULD use `TokenlessAgentWithHeptagon` (the rebranded name)
  to stay aligned with `TOKENLESS_DECLARATION.md`. The `Genesys*` alias
  exists solely for master-spec contract conformance and legacy import
  compatibility.
- Zero runtime behavior change.
- The alias is a one-line wire, NOT a duplicate class — so the alias
  cannot drift apart from the code class.

## References
- `UNIFIED_MASTER_TECH_PACK.md` Part 0.2 (active taxonomy item #10)
- `UNIFIED_MASTER_TECH_PACK.md` Part 0.5 (reconciliation notes)
- `TOKENLESS_DECLARATION.md` (rebranding charter)
- `adr/ADR-S49-01-COGNITIVE-ARCHITECTURE-DOCTRINE.md` (four pillars)
