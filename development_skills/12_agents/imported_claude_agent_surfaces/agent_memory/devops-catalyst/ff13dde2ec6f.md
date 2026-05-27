# CI Audit: Sprints 11-13 (2026-03-07)

## Scope
- .github/workflows/sprint11.yml (7 jobs + gate)
- .github/workflows/sprint12.yml (5 jobs + gate)
- .github/workflows/sprint13.yml (6 jobs + gate)

## Verdicts

| Workflow | Jobs | Runner | SHA-pin | cppcheck | libc | perms | timeout | Verdict |
|----------|------|--------|:---:|:---:|:---:|:---:|:---:|:---:|
| sprint11.yml | 8 (7+gate) | 24.04 | YES | YES | YES | YES | 5-15m | PASS |
| sprint12.yml | 6 (5+gate) | 24.04 | YES | YES | YES | YES | 5-20m | PASS* |
| sprint13.yml | 7 (6+gate) | 24.04 | YES | YES | YES | YES | 5-20m | FLAG |

## Findings

### P1 (Must Fix)

P1-01: sprint13-qemu-dry-run installs `qemu-utils` but NOT `qemu-system-x86` or `dosfstools`/`mtools`.
  - qemu-boot.sh calls `build_disk_image()` BEFORE the dry-run check (line 102).
  - build_disk_image uses `dd` (always available) + `mkfs.fat` (from dosfstools) + `mcopy` (from mtools).
  - mkfs.fat/mcopy are guarded by `command -v` so they silently skip, but `dd` will run.
  - The OVMF package installs to /usr/share/OVMF/OVMF_CODE.fd on ubuntu-24.04 -- this IS installed.
  - However the script will FAIL with exit 1 if OVMF is not found. The `ovmf` package IS installed
    so find_ovmf() should succeed via /usr/share/OVMF/OVMF_CODE.fd.
  - VERDICT: Script will succeed in dry-run mode because:
    (a) ovmf package is installed -> find_ovmf returns a path
    (b) build_disk_image runs dd (always available), mkfs.fat/mcopy gracefully skip
    (c) dry-run exits before calling qemu-system-x86_64
  - BUT: the `Prerequisites` comment says `qemu-system-x86` which is NOT an ubuntu-24.04 package.
    The correct package is `qemu-system-x86`. Actually on ubuntu-24.04 the package IS named
    `qemu-system-x86` (not qemu-system-x86-64). This is fine for the comment but not installed in CI.
  - REVISED: The dry-run path does NOT need qemu-system-x86_64 binary. It only needs OVMF.
    The job installs `ovmf qemu-utils`. This is SUFFICIENT for dry-run. NOT a P1.

P1-01 DOWNGRADED TO P3: sprint13 prerequisites comment mentions `qemu-system-x86` which is correct
  ubuntu-24.04 package name, but not installed. Dry-run does not need it. Cosmetic only.

### P2 (Should Fix)

P2-01: sprint12-kernel-full-compile job name says "all 20 C sources" and step says "(20 files)"
  but the loop actually contains 21 files (13 kernel + 7 gensd + 1 pal = 21), and the tally
  line says "PASS/21". The job name and step name are stale -- should say 21.
  File: sprint12.yml lines 105, 118.

P2-02: sprint12-full-link does NOT verify `readelf` availability. The `readelf` command is used
  in the "Verify ELF entry point and key symbols" step but is NOT explicitly installed. On
  ubuntu-24.04, `binutils` (which provides readelf) is pre-installed on GitHub runners, so this
  will work in practice. But the explicit dependency on `readelf` should be documented or installed.
  Low risk since binutils is always present on ubuntu runners.

P2-03: sprint13-libc-scan only checks 3 files (vmm.c, main.c, test_sprint13.c) but does NOT
  scan the AetherBoot sources (aetherboot/src/aetherboot.c, tpm.c, capability_init.c). AetherBoot
  is UEFI and intentionally uses UEFI types not libc, but the scan gap means a libc sneak-in
  would not be caught.

P2-04: sprint13-qemu-dry-run installs `qemu-utils` but does not install `dosfstools` or `mtools`.
  The qemu-boot.sh script uses `mkfs.fat` (from dosfstools) and `mcopy` (from mtools) inside
  build_disk_image(). These are guarded with `command -v` checks so they silently skip, meaning
  the FAT32 image will be created as a raw zero-filled file without a filesystem. The dry-run
  will still succeed, but the disk image is not properly formatted. For a future non-dry-run
  CI job, `dosfstools` and `mtools` would be required.

### P3 (Advisory)

P3-01: sprint11/12/13 do not upload artifacts. Consistent with sprint3-9 pattern (DC-CI-03 open).

P3-02: sprint12 cppcheck includes hpet.c, lapic.c, pci.c from Sprint 9 drivers in addition to
  Sprint 12 focus files. This is good practice (regression catch) but worth noting the scope creep.

P3-03: sprint11 paths trigger does not include kernel/xenos/include/xenos.h even though
  sprint11-kernel compiles main.c which includes xenos.h. A change to xenos.h alone would NOT
  trigger the sprint11 workflow. sprint13 DOES include xenos.h in paths. Sprint 12 does NOT.

P3-04: sprint12 paths trigger does not include kernel/xenos/include/boot_handoff.h even though
  boot_handoff.h is included by several compiled files. Same pattern as P3-03.

P3-05: init/gensd/include/ directory does not exist (Glob returned no files). The -Iinit/gensd/include
  flag is harmless (clang silently ignores nonexistent include paths) but is misleading.

## Checklist Summary

| Check | sprint11 | sprint12 | sprint13 |
|-------|:---:|:---:|:---:|
| actions/checkout SHA-pinned @11bd719 | YES | YES | YES |
| ubuntu-24.04 | YES | YES | YES |
| timeout-minutes all jobs | YES (5-15m) | YES (5-20m) | YES (5-20m) |
| permissions: contents: read | YES | YES | YES |
| --no-install-recommends | YES | YES | YES |
| cppcheck job | YES | YES | YES |
| libc-scan job | YES | YES | YES (partial) |
| clang-18 versioned | YES | YES | YES |
| freestanding flags correct | YES | YES | YES |
| UEFI target (--target=x86_64-unknown-windows) | N/A | N/A | YES |
| ld.lld-18 available | N/A | YES (installed) | YES (installed) |
| readelf available | N/A | YES (pre-installed) | N/A |
| OVMF findable | N/A | N/A | YES |
| qemu-boot.sh --dry-run works | N/A | N/A | YES |

## Source File Coverage

Sprint 11 (4 C files + 3 headers + 1 test = 8 paths):
  kernel/xenos/core/main.c, init/gensd/main.c, init/gensd/boot_chain.c, pal/src/pal_aether.c
  Headers: xenos.h, xkabi_rights.h, boot_handoff.h
  Test: test_sprint11.c
  ALL EXIST: YES

Sprint 12 (13+7+1=21 C files + 3 ASM + 1 linker script + 1 test):
  Full kernel: 13 C (core/main, mm/{pmm,vmm,heap}, sched/contra_rotation, cap/xkabi_capabilities,
    drv/{intel_igpu,nvme,xacpi,hpet,lapic,pci,elitebook_x360})
  GENSD: 7 C (main, service, supervisor, journal, splash, boot_chain, boot_sequence)
  PAL: pal_aether.c
  ASM: entry.asm, isr.asm, syscall.asm
  Linker: xenos.ld
  Test: test_sprint12.c
  ALL EXIST: YES

Sprint 13 (3 AetherBoot + 2 kernel + 1 test + 1 script):
  AetherBoot: aetherboot.c, tpm.c, capability_init.c
  Kernel: vmm.c, main.c
  Test: test_sprint13.c
  Script: scripts/qemu-boot.sh
  ALL EXIST: YES
