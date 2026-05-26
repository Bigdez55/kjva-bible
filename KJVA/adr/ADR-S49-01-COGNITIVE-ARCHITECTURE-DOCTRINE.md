# ADR-S49-01 - Tokenless Cognitive Architecture Doctrine

## Status

Accepted as the local architecture reference for Tokenless Models.

## Decision

Tokenless model runtimes preserve four contracts:

1. Heptagon for cognitive cycle structure and metadata.
2. XMIND for materialization and low-level inference boundaries.
3. Citadel/Covenant for governance checks and response boundaries.
4. SoulManager for continuity and memory persistence.

## Consequences

- The active local server may use Python/MLX while XMIND remains the
  materialization target.
- Consuming projects define identity, deployment policy, and product-specific
  authority outside this repository.
- Contract changes require focused verification.
