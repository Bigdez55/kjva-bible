# XMIND Runtime Contract

XMIND is the Tokenless materialization and inference contract for C, SUPER C,
and future low-level deployment targets.

## Contents

| Path | Role |
|---|---|
| `include/` | Stable type and materialization headers. |
| `src/` | C implementation path. |
| `superc/` | SUPER C smoke and reference artifacts. |
| `loader/` | Optional model/weight loading helpers. |

## Current Boundary

The active local server uses Python/MLX. XMIND remains the contract to preserve
when moving a model into lower-level or project-specific runtimes.
