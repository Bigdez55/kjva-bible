# ai/xmind/shim — POSIX Build Implementations

This directory provides the POSIX-host implementations of the substrate's
platform-layer contracts. These `.c` files are compiled into the XMIND
hosted-build under `-DXMIND_POSIX_BUILD=1` and link against libc for
mmap/pthread/sockets/stdio/etc.

The contract **headers** themselves now live at the substrate top-level
(`pal/`, `net/`, `sec/`, `xisc/`, `xstore/`). This directory only holds the
hosted-build `.c` implementations — no headers.

## Files

| File | Provides |
|---|---|
| `pal_posix.c`  | mmap / pthread / stdio backing for PAL (`pal.h`) |
| `xnet_posix.c` | Berkeley-sockets backing for XNET (`xnet.h`) |
| `stubs.c`      | stub impls of XSEC (`xsec.h`), XSTORE (`xstore.h`), causal logging (`causal_log_cog.h`), and XNET completion stubs |

## How it's wired

The XMIND Makefile's POSIX build adds the substrate top-level dirs to the
include search path and pulls these `.c` files into `CORE_SRC`:

```
CFLAGS += -Iinclude \
          -I../../pal/include \
          -I../../net/xnet/include \
          -I../../sec/xsec/include \
          -I../../xisc/include \
          -I../../xstore/include

CORE_SRC += shim/pal_posix.c shim/xnet_posix.c shim/stubs.c
```

The freestanding XMIND build uses its own canonical implementations and never
touches this directory.

## Portability rule

This shim layer must NEVER be imported by freestanding code paths. It is a
hosted-build adapter only. The contract surfaces it implements (`pal.h`,
`xnet.h`, `xsec.h`, `xstore.h`, etc., now at substrate top-level) MUST match
the real freestanding contracts exactly — same status codes, same handle
types, same function signatures — so source code is identical between
freestanding and POSIX builds.
