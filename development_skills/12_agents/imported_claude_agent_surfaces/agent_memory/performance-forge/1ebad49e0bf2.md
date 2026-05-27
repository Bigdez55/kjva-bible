---
name: Docker Boot Benchmark 2026-03-29
description: 5-run Docker boot diagnostic on macOS arm64 — AetherBoot completes, kernel ELF load blocked by kern_span under double-emulation
type: project
---

## Docker Boot Benchmark (2026-03-29)

5-run diagnostic on `genos-live:latest` (1.29 GB, built 2026-03-29).

**Environment:** macOS arm64 -> Docker Desktop (Rosetta x86_64 Linux) -> QEMU TCG (x86_64 guest)
**Result:** PARTIAL BOOT — AetherBoot stages 0-3 complete, kernel ELF load fails at stage 4

### Key Findings

- **Determinism:** 5/5 runs produce identical output (except KASLR slide)
- **KASLR:** 4/5 unique slides, all 2MB-aligned, range 0xC00000-0x2600000
- **Memory:** 121 EFI regions, 505 MB usable of 512 MB allocated
- **TSC:** CPUID 0x16 zero-stall calibration (OPT-1.1 from boot-speed-wave1 confirmed working)
- **Failure:** `[ELF] kern_span out of range (must be 1B..256MB)` — double-emulation memory layout issue
- **Recovery:** Graceful fallback to recovery console with diagnostic menu

### Boot Artifacts
- xenos.elf: 1.3 MB (220 linked objects, 281 .c + 96 .h = 181,668 LOC)
- BOOTX64.EFI: 35 KB

### Image Size
- 93.8% is toolchain (1.21 GB); boot artifacts total 1.34 MB
- Ubuntu base: 78 MB

**Why:** Validates boot chain health and identifies cross-platform emulation limitations.
**How to apply:** For reliable boot benchmarking, use native x86_64 host with KVM (GitHub Codespaces). macOS arm64 hits ELF span check failure due to OVMF memory layout differences under double-emulation.
