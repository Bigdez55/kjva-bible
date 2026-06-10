# Runtime Domain Map - Legacy Filename

This legacy filename is retained so references do not break. The current
Tokenless repository does not define a consuming project's organization,
authority hierarchy, or product identity.

## Local Runtime Domains

| Domain | Local Contract |
|---|---|
| Training pipeline | `training/` (byte / BPE pretraining + Omni-PEFT OS) |
| Model staging | `training/` (weights, config, vocab, adapters) |
| Model serving (HTTP) | `training/scripts/serve_raw_model.py` |
| Federated runtime | `_xmind/XMindClient` + `ai/tokenless-agent/src/federation_adapter.py` |
| Governance | `governance/covenant_enforcer.py` |
| Cognitive metadata | `heptagon/harness.py` |
| Memory | `soul_manager/` |
| Materialization | `ai/xmind/` (C inference engine + LoRA loader) |
| UI bridge | `ai/companion/src/agent-bridge.ts` |

Consuming projects should write their own domain map in their own repository.
