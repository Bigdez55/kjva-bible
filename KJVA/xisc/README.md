# xisc/ — XISC Cognitive Opcode Types (canonical home)

`xisc/include/xcog.h` is the canonical XCOG (cognitive bus) header. Source
code includes it via `#include "xcog.h"` (compiler `-I` resolves).

No POSIX implementation .c file ships in `ai/xmind/shim/` for XCOG — the hosted
XMIND build uses stub-level cognitive operations from `stubs.c` where needed.
Freestanding consumers supply their own xcog implementation.
