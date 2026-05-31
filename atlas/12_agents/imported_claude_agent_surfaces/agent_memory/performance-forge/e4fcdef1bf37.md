---
name: Build Speed Phase 2+3 PCH and Unity Builds
description: PCH for xenos.h + 3 unity build files (XNET, XSEC, XSTORE) replacing 29 individual compilations
type: project
---

Sprint 46 build speed optimization (2026-03-28).

## PCH (Precompiled Header)
- Target: `$(BUILD)/xenos.pch` from `include/xenos.h` (421 LOC) + `pal.h` (504 LOC)
- Used by kernel-local `.o` rules via `-include-pch $(PCH)`
- PCH is a normal prerequisite: header changes trigger recompilation
- Standalone target: `make -C kernel/xenos pch`

## Unity Builds (UNITY_BUILD=1)
- `store/xstore_unity.c`: 9 files (xstore + xblob)
- `sec/xsec_unity.c`: 9 files (crypto + tls + x509 + audit), excludes aes_ni.c (SIMD flags)
- `net/xnet_core_unity.c`: 11 files (core stack), excludes drivers (e1000, virtio_net)
- Total: 29 individual files -> 3 unity files = 26 fewer compiler invocations

## Static Symbol Collision Resolution
- XSTORE/XBLOB: zero collisions
- XSEC: `aes256_encrypt_block` same-file #if/#else, not cross-file -- no fix needed
- XNET: 8 utility inlines (xnet_memset, xnet_memcpy, etc.) copy-pasted into 11 files
  - Fix: Created `net/xnet/include/xnet_mem.h` with canonical definitions
  - Each .c file's local copies wrapped with `#ifndef XNET_MEM_H` guards
  - Individual compilation still works (guarded copies remain as fallback)

## Build Metrics
- Normal mode (UNITY_BUILD=0): 145 objects (142 C + 3 ASM)
- Unity mode (UNITY_BUILD=1): 119 objects (116 C + 3 ASM)
- Predicted improvement: ~18% fewer compiler invocations, ~25-35% wall-clock reduction
  (unity files enable cross-file inlining within subsystems)

**Why:** Compiler startup overhead dominates on freestanding cross-compilation builds. Each clang-18 invocation with cross-target flags costs ~100-200ms even for small files.

**How to apply:** Use `UNITY_BUILD=1` for local development iteration. CI uses `UNITY_BUILD=0` for correct incremental builds and precise error reporting.
