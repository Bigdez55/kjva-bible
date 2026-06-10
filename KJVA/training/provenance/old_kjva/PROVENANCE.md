# PROVENANCE.md - Local Ownership and Replication Policy

This file no longer tracks an external source tree. Tokenless Models owns its
runtime contracts, training scripts, and documentation locally.

## Status Model

| Status | Meaning |
|---|---|
| Contract | Stable architectural surface. Change only with tests and audit notes. |
| Runtime | Working implementation that may evolve with model needs. |
| Template | Portable starting point for consuming projects. |
| Historical | Kept for compatibility with old paths or export manifests. |

## Local Contract Inventory

| Area | Status | Notes |
|---|---|---|
| `heptagon/` | Contract | 7-layer cognitive cycle and trace envelope. |
| `governance/` | Contract | Covenant checks and decision envelopes. |
| `soul_manager/` | Contract | Memory, continuity, and encryption boundary. |
| `ai/xmind/include/` | Contract | XMIND type and materialization surface. |
| `ai/xmind/src/` | Runtime | C implementation path; may need platform shims for C deployment. |
| `ai/xmind/superc/` | Runtime | SUPER C smoke and materialization artifacts. |
| `ai/companion/` | Template | Client bridge for the local cognitive server. |
| `training/` | Runtime | Corpus, tokenizer, train, export, serve, eval. |
| `saas_translation/` | Historical | Older deployment planning docs; use only as notes, not repo identity. |

## Replication Rule

Consuming projects should select the pieces they need and define their own:

- product or agent name
- model export ID
- ports and deployment target
- operator authority model
- corpus and evaluation policy

This repository should stay neutral and reusable.

## External Artifact Rule

Model exports, corpora, and logs are machine-local artifacts. Prefer:

```bash
$TOKENLESS_HOME/exports/<model_id>
$TOKENLESS_HOME/corpus
$TOKENLESS_HOME/signals
```

Do not hard-code sibling repositories or absolute user paths in new code.
