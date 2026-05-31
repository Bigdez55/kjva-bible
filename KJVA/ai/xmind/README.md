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

XMIND is the active serving boundary for the KJVA byte-level model.

The current host bridge is `kjva_byte_backend.py`. It loads
`KJVA/training/weights.safetensors`, enforces the KJVA byte-token contract
(`PAD=0`, `BOS=1`, `EOS=2`, byte `b -> b+3`, vocab `259`), validates the
8-layer/384-hidden/6-head/1024-context config, maps embeddings and RMS weights
as F32, materializes projection matrices through XMIND `Q4_0`, and exposes the
same pre/per-token/post hook halt semantics used by the C runtime.

The C implementation remains the freestanding lower-level materialization
target. MLX is reference-only and is not a serving fallback.
