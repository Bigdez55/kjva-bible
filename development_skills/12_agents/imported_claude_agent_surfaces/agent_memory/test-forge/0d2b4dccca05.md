---
name: GEN.OS Benchmark Baseline 2026-03-31
description: Comprehensive benchmark baseline -- LOC, compile rates, test pass rates, security features, crypto KAT, codebase metrics
type: project
---

## GEN.OS Benchmark Baseline -- 2026-03-31

### Codebase Metrics
- Total LOC: 422,866 (C: 237,500 / H: 28,183 / Py: 134,314 / ASM: 966 / TS: 21,903)
- Total files: 1,113 (C: 425 / H: 122 / Py: 447 / ASM: 5 / TS: 114)
- Production C files: 292

### Test Results
- Python test suite: 1,227 passed / 882 failed / 71 errors / 2 skipped (56.2% pass rate)
- Crypto KAT: 17/17 PASS, 5x deterministic
- C compile (-Werror -fsyntax-only): 237/292 PASS (81.2%)
- Python syntax: 447/447 PASS (100%)
- JSON validation: 94/101 PASS (93.1%)
- Council gates: 9/9 PASS (100%)
- Frozen headers (XCOG/R1_PER): 9/9 PASS (100%)
- Compile determinism: 3/3 (100%)

### Security
- Security features active: 15/16 (93.8%)
- Missing: TPM 2.0 not wired into kmain (driver exists)

### Infrastructure
- CI workflows: 64
- ADRs: 53
- Runbooks: 8
- Test files: 136 (59 Python + 77 C)

### C Compile Failures (55 files)
- Display (xcomp/xdisp): missing cross-include paths
- XJIT: needs -mavx2 for AVX2 intrinsics
- Firmware: HP-specific UEFI headers
- XEMU: needs hosted target
- XISC linux personality: needs POSIX headers
- FFI: needs hosted (not freestanding) target

**Why:** Establishes the first comprehensive quality baseline for GEN.OS.
**How to apply:** Compare future benchmarks against these numbers. Coverage can only go up.
