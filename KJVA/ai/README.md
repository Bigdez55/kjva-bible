# AI Runtime Subsystem

This directory contains reusable AI runtime pieces for Tokenless Models.

## Components

| Path | Role |
|---|---|
| `xmind/` | C inference engine + LoRA loader + POSIX shim + Makefile. |
| `tokenless-agent/` | Python agent/runtime API surface (FastAPI-style + federation adapter). |
| `companion/` | TypeScript client bridge and UI components. |
| `tts/` | Optional local text-to-speech implementation. |

## Runtime Boundary

The runtime reads model artefacts staged into `training/` (the consolidated
training pipeline lives there):

- `training/weights.safetensors`
- `training/model_config.json`
- `training/byte_vocab.json`
- `training/adapters/<member>/adapter.safetensors`

For raw model serving over HTTP, use the substrate's generic server:

```bash
python3 training/scripts/serve_raw_model.py \
  --export training \
  --port 8088
```

XMIND is the C-runtime path used by the per-member federation
(`_xmind.XMindClient`) and by any consuming project that needs lower-latency,
zero-Python inference.

Keep this directory model-neutral. Consuming projects should supply their own
names, UI shell, and deployment policy.

## Platform contracts (top-level dirs)

The substrate exposes 5 platform-layer contracts as canonical top-level dirs.
The real headers live there; the XMIND POSIX-build implementations live under
`ai/xmind/shim/`:

| Header | Canonical location | POSIX impl |
|---|---|---|
| `pal.h` | `models/pal/include/pal.h` | `ai/xmind/shim/pal_posix.c` |
| `xnet.h` | `models/net/xnet/include/xnet.h` | `ai/xmind/shim/xnet_posix.c` |
| `xsec.h` | `models/sec/xsec/include/xsec.h` | `ai/xmind/shim/stubs.c` |
| `causal_log_cog.h` | `models/sec/xsec/include/causal_log_cog.h` | `ai/xmind/shim/stubs.c` |
| `xcog.h` | `models/xisc/include/xcog.h` | (no shim impl yet) |
| `xstore.h` | `models/xstore/include/xstore.h` | `ai/xmind/shim/stubs.c` |

Source code uses unqualified `#include "pal.h"` (etc.) — the XMIND Makefile
adds the top-level dirs to its `-I` search path.
