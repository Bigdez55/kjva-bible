---
name: ARM64 Boot Matrix Fix (2026-04-06)
description: Root cause analysis and fix for ARM64 PARTIAL boot — 3 root causes found and fixed
type: project
---

## ARM64 Boot Matrix: PARTIAL -> PASS Fix

**Root Cause 1: BUILD — Only 3 of 9 source files compiled**
- boot-matrix-md.sh `build_arm64_kernel()` compiled: entry.S, exception_table.S, kmain_aarch64.c
- MISSING: fault_aarch64.c, vmm_aarch64.c, syscall_aarch64.c, context_aarch64.c, gicv3.c, arm_timer.c
- kmain_aarch64.c calls extern functions in all 6 missing files
- Link either fails (producing stale ELF from prior run) or resolves to weak stubs that crash

**Why:** build_arm64_kernel() was written for Sprint 37 minimal boot test (3 files). The subsystem C files were added later but never wired into the build.

**How to apply:** boot-matrix-md.sh now compiles all 9 objects (2 ASM + 7 C) with `-DXENOS_FLAT_MODE`.

**Root Cause 2: HHDM_BASE in gicv3.c — crash on MMIO access**
- `gicv3.c` line 123: `g_gicv3.gicd_base = (volatile uint32_t *)(gicd_phys + HHDM_BASE)`
- HHDM_BASE = 0xFFFF888000000000 (x86-64 direct map, PML4 index 273)
- In flat mode (MMU off), accessing 0xFFFF888008000000 causes immediate data abort
- Fix: `#if defined(XENOS_FLAT_MODE)` guard uses physical addresses directly

**Why:** gicv3.c was written assuming MMU-on HHDM mapping (like x86-64 drivers use). Flat mode boot runs with MMU off.

**Root Cause 3: QEMU serial capture — monitor output mixed with kernel output**
- ALREADY FIXED in working tree (not by this session)
- Original: `-serial stdio` with `-nographic` muxes monitor+serial onto stdout
- Fix: `-serial file:$serial -monitor none` separates channels
- Also: `-machine virt,gic-version=3` required for GICv3 (kernel expects GICv3, not GICv2)

**Entry sentinel:** Added `X` character output to PL011 UART directly from entry_aarch64_flat.S before calling kmain. This proves CPU reached our code even if C init crashes.

**Files changed:**
- `kernel/xenos/drv/gicv3.c` — XENOS_FLAT_MODE guard for MMIO base addresses
- `kernel/xenos/arch/aarch64/entry_aarch64_flat.S` — immediate UART sentinel before kmain
- `tests/hardware/boot-matrix-md.sh` — compile all 9 ARM64 source files
- `.github/workflows/sprint37.yml` — compile-check all ARM64 C files
- `.github/workflows/kernel-link.yml` — add -DXENOS_FLAT_MODE to ARM64 compile flags
