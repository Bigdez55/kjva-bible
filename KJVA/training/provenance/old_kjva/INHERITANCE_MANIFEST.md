# CORE_CONTRACT_MANIFEST.md

This legacy filename now describes the local Tokenless Models contract set. It
is not an inheritance or source-sync record.

## Preserved Contracts

| Contract | Purpose | Portability Boundary |
|---|---|---|
| Heptagon | 7-layer cognitive cycle, trace, evaluation, enforcement envelope. | Keep the cycle shape; consuming projects choose identity and policy. |
| XMIND | Materialization and inference contract for C/SUPER C paths. | Keep type surfaces; deployment may use Python/MLX, C, or managed inference. |
| Citadel/Covenant | Governance checks, hard stops, soft warnings, decision envelopes. | Keep enforcement hooks; consuming projects define their rule text. |
| SoulManager | Continuity and memory storage boundary. | Keep encrypted persistence semantics; storage backend is configurable. |

## What Belongs Here

- reusable model-serving code
- portable training/export scripts
- local smoke tests
- model-neutral runtime contracts
- audit notes that explain wiring and verification

## What Does Not Belong Here

- consuming-project brand identity
- one-off product names
- hard-coded sibling repository paths
- fixed cloud provider decisions
- deployment secrets or personal machine assumptions

## Change Policy

Contract changes need:

1. a focused explanation in the relevant doc or audit note
2. a smoke test for the affected runtime path
3. no silent renaming of working model classes or export formats

The current working model class/export names may remain until a tested migration
renames them.
