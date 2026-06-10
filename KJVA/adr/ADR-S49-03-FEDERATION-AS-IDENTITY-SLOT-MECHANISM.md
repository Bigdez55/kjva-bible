# ADR-S49-03 — Federation Is the Identity-Slot Mechanism, Not a Doctrinal Deviation

## Status
Accepted (2026-05-30, per user ruling).

## Context
`UNIFIED_MASTER_TECH_PACK.md` Part II §1 (Apex Taxonomy Lock) is explicit:

> The Model is a single Python process. It has no name, no persona, no
> domain allegiance, and no constitutional identity. It is purely
> functional.

The existing `models v7/_xmind/client.py` requires `MEMBER_NAME` (env or
constructor argument), loads `_xmind/personas/<MEMBER_NAME>.txt`, and
exposes a federated multi-member surface. On its face this looks like
a federated multi-member paradigm at odds with the single-neutral-process
doctrine.

## Decision
Per user ruling 2026-05-30:

> The naming and person will be given when the model will be determined.
> these are pre-wired models that only need identities and training.

The federated `XMindClient` infrastructure IS the pre-wired
identity-binding mechanism the master spec implies. Each `XMindClient`
instance, when given an identity at deployment time, becomes one neutral
cognitive process realizing the Apex §1 single-process doctrine.
Identity is therefore a **runtime input**, not a property baked into
the cognitive runtime itself.

For test harnesses that exercise the canonical neutral path BEFORE any
identity has been assigned (`tests/validate_apex.py` and the Apex §22
9/9 acceptance sweep), use the placeholder identity `apex-singleton`
with the neutral-aligned persona file at
`_xmind/personas/apex-singleton.txt`.

## Consequences
- The Apex §1 single-neutral-process invariant holds per pre-binding
  `XMindClient` instance.
- No code change to `_xmind/client.py` — federation API preserved.
- `_xmind/personas/apex-singleton.txt` is the test-time neutral identity.
- Production deployments bind real identities at runtime via the
  existing federation API; each is one neutral cognitive process by
  construction.
- ADR-S49-02 (class-name reconciliation) is independent of this ADR.

## References
- `UNIFIED_MASTER_TECH_PACK.md` Part II §1 (Apex Taxonomy Lock)
- `_xmind/client.py` (federated XMindClient implementation)
- `_xmind/personas/apex-singleton.txt` (neutral placeholder persona)
- `adr/ADR-S49-01-COGNITIVE-ARCHITECTURE-DOCTRINE.md` (four pillars)
