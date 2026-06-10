# sec/ — XSEC Security Layer (canonical home)

Holds the substrate's security contract headers:

- `sec/xsec/include/xsec.h` — XSEC API (audit events, capability checks, etc.)
- `sec/xsec/include/causal_log_cog.h` — causal logging cognitive overlay

Source code includes them via `#include "xsec.h"` / `#include
"causal_log_cog.h"` (compiler `-I` resolves). The POSIX shim implementation
(routes audit events to stderr, no-ops capability gates) lives in
`ai/xmind/shim/stubs.c` and is compiled into the hosted XMIND build only.
Freestanding consumers supply real implementations.
