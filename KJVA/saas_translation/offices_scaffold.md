# Optional Extension Scaffold

Use this only when a consuming project needs additional model-facing services.

| Extension | Purpose | Required? |
|---|---|---|
| Evaluation worker | Batch quality checks and regression reports. | No |
| Retrieval builder | Rebuilds the wisdom/corpus index. | No |
| Feedback collector | Normalizes ratings and edited responses. | No |
| Export publisher | Promotes verified model artifacts. | No |
| UI shell | Product-specific interface over the companion bridge. | No |

Keep extension names local to the consuming project.
