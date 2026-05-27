# Toolchain Dual-Architecture Audit: x86-64 + ARM64 (2026-04-04)

## Summary
- **Total LOC for ARM64 parity: ~1,870**
- **New files needed: 4** (codegen_aarch64.c, neon_dot.c, neon_matmul.c, xas_encode_aarch64.c)
- **Files needing modification: 7** (xjit.h, xcc_irgen.h, xcc_typeck.c, xcc_irgen.c, xas.c, xisc_xjit_bridge.c, xjit.c)
- **Already dual-arch: PAL (pal.h), XISC bytecode (xisc.h), XKABI (xkabi_arch.h), ARM64 kernel (7 files)**

## Critical x86-64 Hardcoded Items

### XCC Compiler
- `xcc_irgen.h` line 50: `XCC_IRGEN_MAX_PARAMS 6u` (SysV ABI) -> ARM64: 8 (AAPCS64)
- `xcc_irgen.h` lines 109-110: RBP vreg naming -> rename to FP
- `xcc_typeck.c` line 238: `long double = 8 bytes` -> ARM64: 16 bytes (IEEE quad)

### XJIT Backend (BIGGEST EFFORT)
- `xjit.h` lines 142-196: Entire x86-64 register set, HW encoding, alloc order
- `codegen.c`: 600+ lines of pure x86-64 machine code -> needs `codegen_aarch64.c` (~550 LOC)
- `avx2_dot.c`: AVX2/FMA intrinsics -> needs `neon_dot.c` (~250 LOC)
- `avx2_matmul.c`: AVX2 VEX JIT codegen + CPUID -> needs `neon_matmul.c` (~300 LOC)

### XAS Assembler
- `xas.c`: 100% x86-64 (register map, instruction encoders, ELF machine type)
- Needs `xas_encode_aarch64.c` (~400 LOC) + refactor (~80 LOC)

### XISC
- `xisc.h`: CLEAN (bytecode format is architecture-neutral, 32-bit fixed-width encoding)
- `xisc_xjit_bridge.c`: Comments only (5 LOC)

## ARM64 Kernel Infrastructure (ALREADY EXISTS)
- entry_aarch64.S, entry_aarch64_flat.S, exception_table.S, kmain_aarch64.c
- vmm_aarch64.c (TTBR0/TTBR1 page tables), link_aarch64.ld, link_aarch64_flat.ld

## Implementation Order
1. Phase 1 (Foundation): xjit.h register defs, XCC params (~260 LOC)
2. Phase 2 (Codegen): codegen_aarch64.c (~550 LOC)
3. Phase 3 (SIMD): neon_dot.c + neon_matmul.c (~550 LOC)
4. Phase 4 (Assembler): xas_encode_aarch64.c + xas.c refactor (~480 LOC)

## Key ARM64 Differences from x86-64
- 31 GP registers (x0-x30) vs 16; x29=FP, x30=LR, SP is separate
- 8 integer arg registers (x0-x7) vs 6 (RDI,RSI,RDX,RCX,R8,R9)
- Fixed 32-bit instruction encoding (no variable-length, no REX, no ModRM)
- 64-bit immediate requires MOVZ+MOVK sequence (up to 4 instructions)
- No PUSH/POP; use STP/LDP pairs
- NEON = 128-bit SIMD (mandatory on ARMv8) vs AVX2 = 256-bit (optional)
- long double = 16 bytes (IEEE quad) vs x86-64 = 16 bytes (80-bit extended, padded)
