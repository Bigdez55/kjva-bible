# Identity Attestation Doctrine

**Status:** Constitutional Law — Immutable
**Governing Principle:** Every restart is a verification event. Every identity claim must be proven.

---

## Attestation Requirements

Every member restart must pass attestation before regaining authority:

| Verification | What It Proves |
|---|---|
| Signed daemon identity | The binary itself is cryptographically signed |
| Signed schema fingerprint | The Heptagon schema matches the registry |
| Memory lineage hash chain | The member's history is verifiable and unforgeable |
| Invariant signature set | The member's L7 invariants match the constitution |
| Challenge-response triad | Three witnesses independently verify the identity |

## Attestation Witnesses (with Vacancy Fallbacks)

| Normal | If Ahki vacant | If Esther vacant | If Sarah vacant |
|--------|---|---|---|
| Ahki + Esther + Sarah | Regency Triad | Ahki + Sarah + Abigail | Ahki + Esther + Abigail |

## Restart Classification

| Condition | Classification | Response |
|---|---|---|
| Attestation passes all checks | Legitimate restart | Grant authority per current mode |
| Attestation fails any check | Suspicious | Quarantine, alert all members, escalate to project authority |
| Attestation not attempted | Unauthorized | Block, do not grant any authority |

## Impersonation Detection

A member that passes structural checks but makes decisions inconsistent with its behavioral baseline triggers:
1. Behavioral anomaly alert (all members notified)
2. Authority frozen to RECOMMENDATION
3. Extended observation period (minimum 10 cycles)
4. If anomaly persists → full reconstitution required

## Immutability

This doctrine is beyond amendment. Identity attestation is the foundation of trust in the House.
