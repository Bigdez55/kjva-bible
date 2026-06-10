# net/ — XNET Network Layer (canonical home)

`net/xnet/include/xnet.h` is the canonical XNET header. Source code that needs
network I/O includes it via `#include "xnet.h"` (resolved by the compiler `-I`
search path).

The POSIX Berkeley-sockets implementation lives at `ai/xmind/shim/xnet_posix.c`
and is compiled into the hosted XMIND build only. Freestanding consumers
supply their own xnet implementation matching the same contract.
