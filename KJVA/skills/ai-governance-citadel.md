# AI Governance & Heptagon Pattern Notes

This file records reusable governance and safety patterns for Tokenless Models.
It is not a pointer to an external project tree.

## Runtime Patterns

- Sequential governance pipelines should fail closed when a required gate is missing.
- Decision envelopes should carry intent, subject, risk score, alignment score, gate results, verdict, and provenance hash.
- Heptagon cycles should preserve traceability across admission, routing, generation, verification, calibration, and enforcement.
- Covenant checks should run before model generation and again before response delivery.
- Source trust checks should use explicit allowlists and suspicious-pattern detection.
- Response verification should check safety, relevance, coherence, and completeness before release.
- Drift monitoring should track goal divergence, policy override, mode mismatch, reversal, artifact quality, and covenant violations.
- Write-back should be staged: hot memory first, journal second, archive only when learning is retained and admissible.

## Local Surfaces

- `governance/covenant_enforcer.py`
- `governance/decision_envelope.py`
- `governance/interceptors.py`
- `governance/drift_signal.py`
- `heptagon/registry.py`
- `heptagon/layers.py`
- `heptagon/attestation.py`
- `ai/tokenless-agent/src/heptagon/`
- `ai/companion/src/avatar.ts`

## Replication Rule

When a consuming project needs domain-specific governance, create that project
locally in the consuming repo. Keep this file as the portable pattern ledger for
the Tokenless blueprint.
