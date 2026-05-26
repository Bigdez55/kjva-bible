# Runtime Domain Map - Legacy Filename

This legacy filename is retained so references do not break. The current
Tokenless repository does not define a consuming project's organization,
authority hierarchy, or product identity.

## Local Runtime Domains

| Domain | Local Contract |
|---|---|
| Model serving | `ml-training/scripts/serve_kjv_bundle.py` |
| Retrieval | `KJVRetriever` and KJV bundle artifacts |
| Governance | `governance/covenant_enforcer.py` |
| Cognitive metadata | `heptagon/harness.py` |
| Memory | `soul_manager/` |
| Materialization | `ai/xmind/` |
| UI bridge | `ai/companion/src/agent-bridge.ts` |

Consuming projects should write their own domain map in their own repository.
