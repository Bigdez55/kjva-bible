# xstore/ — XSTORE Storage Layer (canonical home)

XSTORE is the substrate's persistent-storage contract. Header + default
implementation both live in this directory:

| File | Role |
|---|---|
| `include/xstore.h` | Canonical contract header. Consumers `#include "xstore.h"` (compiler `-I` resolves). |
| `xstore_stubs.c`   | Default no-op implementation. `xstore_get` returns `XSTORE_ERR_NOT_FOUND`; `xstore_put` / `xstore_delete` return `XSTORE_OK` without side effects. |

Real deployments replace `xstore_stubs.c` with a backing store (key-value DB,
filesystem, block device) matching the XSTORE contract in `xstore.h`.
