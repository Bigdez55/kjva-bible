# Deployment Translation Template

This historical planning file is now a neutral template for moving a Tokenless
model stack into a consuming project.

## Inputs To Define Per Project

| Decision | Example |
|---|---|
| Model export | `$TOKENLESS_HOME/exports/<model_id>` |
| Runtime server | Python/MLX, C/XMIND, managed inference, or hybrid |
| API surface | `/healthz`, `/v1/chat`, `/v1/chat/stream`, `/v1/cite` |
| Memory backend | local JSONL, encrypted file store, database, or object storage |
| Governance policy | covenant rules and hard-stop behavior |
| Signal logs | local JSONL, event stream, database, or observability pipeline |
| UI bridge | companion bridge, app-native client, or project-specific UI |

## Preserved Wiring Pattern

```text
client -> cognitive server -> model export
       -> retrieval index
       -> covenant checks
       -> Heptagon cycle metadata
       -> signal log
```

Do not encode product identity, cloud provider, or personal machine paths in
this template.
