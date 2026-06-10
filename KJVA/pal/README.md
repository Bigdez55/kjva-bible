# pal/ — Platform Abstraction Layer (canonical home)

`pal/include/pal.h` is the canonical platform abstraction layer header for the
substrate. Code in `ai/xmind/` (and any other consumer) includes it via
`#include "pal.h"` — the compiler `-I` search path resolves to this file.

The POSIX implementation backing PAL with libc (mmap, pthread, sockets, stdio)
lives at `ai/xmind/shim/pal_posix.c` and is compiled into the hosted XMIND
build under `-DXMIND_POSIX_BUILD=1`. The freestanding XMIND build supplies its
own PAL implementation and never touches the POSIX shim.

A consuming project that supplies its own freestanding PAL replaces
`pal/include/pal.h` with their freestanding header (matching the same status
codes, handle types, function signatures). Source code that `#include "pal.h"`
stays unchanged.
