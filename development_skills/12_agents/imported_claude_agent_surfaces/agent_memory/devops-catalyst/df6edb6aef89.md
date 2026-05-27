---
name: GEN.OS Build System Skills Catalog
description: 40+ distinct build/CI/Docker skills extracted from Makefile, boot-test.sh, Dockerfiles, workflows, unity builds, and linker scripts
type: reference
---

# GEN.OS Build System Skills Catalog

Extracted 2026-03-31 from the full production codebase.

---

## SKILL 01: Two-PCH Architecture (NOSSE vs SSE)

**Category:** makefile, pch
**The Problem:** A freestanding OS kernel has two incompatible ABIs in one binary -- kernel core code uses `-mno-mmx -mno-sse -mno-sse2` (integer-only), while display/AI/UI subsystems use SSE/AVX2 for float math. A single PCH compiled with one flag set produces type mismatches when used with the other.
**The Solution:** Build TWO precompiled headers from the same source (`include/xenos.h`), each with different SIMD flags:
- `$(BUILD)/xenos_nosse.pch` -- built with `$(CFLAGS)` (NOSSE)
- `$(BUILD)/xenos_sse.pch` -- built with `$(CFLAGS_XMIND)` (SSE-enabled)
Each `.o` rule has an order-only prerequisite (`|`) on the matching PCH variant.
**Performance Impact:** PCH eliminates re-parsing the 2000+ line xenos.h/pal.h chain for every TU. ~30% compile time reduction across 160+ objects.
**Gotchas:** Order-only prerequisites (`| $(PCH_NOSSE)`) ensure the PCH is built before any `.o` but do NOT trigger recompilation when the PCH changes. The `$(PCH_DEPS)` normal prerequisite on the PCH rule itself handles header change tracking.
**File:Line Reference:** `kernel/xenos/Makefile:99-118`

---

## SKILL 02: Per-File CFLAGS Overrides (AESNI / AVX2 / SSE)

**Category:** makefile, compiler-flags
**The Problem:** In a monolithic kernel image, different files need different SIMD instruction sets. `aes_ni.c` needs AES-NI + PCLMUL. `tensor.c` + `transformer.c` need AVX2+FMA. `math_stubs.c` needs SSE for `sqrtf`. The rest must NOT use SSE (kernel ABI).
**The Solution:** Define multiple CFLAGS variants and use Make's most-specific-rule-wins:
```
CFLAGS       = ... -mno-mmx -mno-sse -mno-sse2          # kernel default
CFLAGS_AESNI = ... -msse2 -msse4.1 -maes -mpclmul       # crypto
CFLAGS_XMIND = ... -msse -msse2                          # AI/display
CFLAGS_XMIND_AVX2 = ... -msse -msse2 -mavx2 -mfma       # hot paths
```
Specific files get explicit rules BEFORE the `%` pattern rules so Make's specificity precedence applies.
**Performance Impact:** tensor.c and transformer.c compiled with AVX2+FMA see 4-8x throughput for dot products and matrix multiplications vs scalar.
**Gotchas:** Files compiled with SIMD flags that differ from their PCH variant must either use the matching PCH (SSE PCH) or compile WITHOUT PCH entirely. `aes_ni.c` has NO PCH at all (`-maes -mpclmul` features are incompatible with both PCH variants). See Makefile:631-634.
**File:Line Reference:** `kernel/xenos/Makefile:74-84, 631-634, 650-658, 668-671`

---

## SKILL 03: Unity Build Pattern (29 Files to 3 TUs)

**Category:** unity, makefile
**The Problem:** Compiling 29 individual C files incurs 29x compiler startup overhead (clang process spawn, PCH load, system header parse). For the network, security, and storage subsystems, these files share extensive common includes.
**The Solution:** Three unity files that `#include` the `.c` sources directly:
- `net/xnet_core_unity.c` -- 11 XNET files (core/link/inet/transport/api/app/mesh)
- `sec/xsec_unity.c` -- 9 XSEC files (crypto + TLS + x509 + audit)
- `store/xstore_unity.c` -- 9 XSTORE+XBLOB files
Toggled by `UNITY_BUILD ?= 0` (default off, opt-in).
**Performance Impact:** Eliminates 26 compiler invocations. Also enables cross-file inlining within each subsystem (e.g., sha256 called from tls13 can inline without LTO).
**Gotchas:** Symbol collisions are the #1 problem. XNET had `g_initialized` in both `netif.c` and `gossip.c` -- renamed to `g_netif_initialized` / `g_gossip_initialized`. Route fallback functions duplicated between `netif.c` and `ip4.c` -- excluded via `XNET_UNITY_EXCLUDE_ROUTE_FALLBACK` define.
**File:Line Reference:** `kernel/xenos/Makefile:121-128, 190-252`, `net/xnet_core_unity.c`, `sec/xsec_unity.c`, `store/xstore_unity.c`

---

## SKILL 04: Shared Inline Extraction for Unity Compatibility

**Category:** unity, header-design
**The Problem:** Each XNET `.c` file had its own copy of `xnet_memset`, `xnet_memcpy`, etc. as `static` functions. When compiled individually, no conflict. In unity mode, multiple definitions in the same TU cause "redefinition" errors.
**The Solution:** Extract shared utilities into `xnet_mem.h` with `#ifndef XNET_MEM_H` guard. Each original `.c` file wraps its local copies with `#ifndef XNET_MEM_H` so they are skipped when the header (or unity build) provides them. Unity file includes `xnet_mem.h` first. Individual `.c` files continue to compile standalone because their guarded copies remain as fallback.
**Performance Impact:** Zero runtime impact -- same code, just deduped at compile time.
**Gotchas:** Must use `#ifndef XNET_MEM_H` (the include guard), NOT `#ifdef XNET_UNITY_BUILD`. This way the dedup works for both unity and normal builds that happen to include the header.
**File:Line Reference:** `net/xnet/include/xnet_mem.h`, `net/xnet_core_unity.c:21`

---

## SKILL 05: Ccache Integration in Toolchain

**Category:** docker, caching
**The Problem:** Rebuilding 160+ C objects from scratch on every Docker build or CI run wastes minutes. Object files are deterministic given the same source + flags.
**The Solution:** `CC = ccache clang-18` in the Makefile. The toolchain Docker image sets `ENV CCACHE_DIR=/tmp/ccache` and `ENV CCACHE_MAXSIZE=500M` and adds `/usr/lib/ccache` to PATH. ccache hashes the preprocessed source + compiler flags and returns cached `.o` if hit.
**Performance Impact:** Warm rebuild (e.g., single file change) drops from ~45s to ~5s. Full clean build populates cache for next run.
**Gotchas:** ccache must be listed BEFORE clang-18 in PATH, not after. The `CC = ccache clang-18` syntax works because Make passes the entire value to the shell, which runs `ccache` with `clang-18` as the argument.
**File:Line Reference:** `kernel/xenos/Makefile:21`, `tools/docker/Dockerfile.toolchain:58-61`

---

## SKILL 06: Self-Hosted Toolchain Docker Image

**Category:** docker, reproducibility
**The Problem:** CI runners do `apt-get install` every run, depending on Ubuntu mirror availability, GPG key freshness, and package version stability. Docker Desktop on macOS corrupts GPG signatures during amd64 emulation.
**The Solution:** Build a single toolchain image (`Dockerfile.toolchain`) with ALL tools pre-installed: clang-18, lld-18, nasm, make, ccache, cppcheck, qemu-system-x86, ovmf, novnc, dosfstools, mtools, xorriso, debootstrap, squashfs-tools, grub-efi-amd64-bin. Push to GHCR. All subsequent builds use `FROM ${TOOLCHAIN_IMAGE}` with zero apt-get calls.
**Performance Impact:** Eliminates 30-60s apt-get overhead per build. Also eliminates mirror/GPG transient failures.
**Gotchas:** The toolchain Dockerfile uses `AllowInsecureRepositories` + `AllowUnauthenticated` to work around Docker Desktop GPG corruption. This is acceptable ONLY for the one-time image build -- the resulting image is content-addressed by Docker SHA-256 digest. A version manifest is written to `/toolchain-manifest.txt` and verified in a final RUN step.
**File:Line Reference:** `tools/docker/Dockerfile.toolchain`, `tools/docker/build-toolchain.sh`

---

## SKILL 07: Multi-Stage Docker Build (Toolchain -> Builder -> Runtime)

**Category:** docker, image-optimization
**The Problem:** A Docker image containing both the build toolchain AND the runtime artifacts would be enormous (2+ GB). Source code should not ship in the runtime image.
**The Solution:** Three-stage build:
1. **toolchain** (FROM pre-built GHCR image): All compilers/tools, zero apt-get
2. **builder** (FROM toolchain): COPY source code, run `boot-test.sh`, produces xenos.elf + BOOTX64.EFI
3. **runtime** (FROM toolchain): COPY only 2 artifacts from builder + entrypoint script. QEMU + noVNC for browser-based boot.
**Performance Impact:** Each subsystem is a separate COPY layer, so only changed subsystems invalidate their layer.
**Gotchas:** The `COPY aetherboo[t]/ /genos/aetherboot/` uses a glob bracket to silently succeed even if the directory does not exist (legacy symlink path). Without the bracket, COPY would fail if the directory is absent.
**File:Line Reference:** `tools/launch/Dockerfile:24-97`

---

## SKILL 08: Subsystem-Ordered COPY Layers

**Category:** docker, caching
**The Problem:** `COPY . /genos/` invalidates the entire build cache on ANY file change. You want to only rebuild when the files that matter change.
**The Solution:** Order COPY commands by change frequency (least to most):
1. `COPY tools/boot/` (build infrastructure -- rarely changes)
2. `COPY kernel/ pal/ init/` (core boot chain -- moderate)
3. `COPY devices/desktop/aetherboot/` (bootloader)
4. `COPY net/ sec/ store/ pkg/ ai/ ...` (subsystems -- frequent changes)
Each COPY is a separate Docker layer. A change to `devices/desktop/shell/` only invalidates that layer and below.
**Performance Impact:** Typical development only changes 1-2 subsystems, so most layers are cached. Saves 30-60s on incremental Docker builds.
**Gotchas:** The layer ordering must match the Makefile dependency graph. If you put `kernel/` after `net/`, changing a kernel header would NOT trigger a net/ rebuild because Docker does not understand Make dependencies.
**File:Line Reference:** `tools/launch/Dockerfile:39-69`

---

## SKILL 09: FAT32 Superfloppy Disk Image (No GPT)

**Category:** boot, disk-image
**The Problem:** OVMF's PartitionDxe driver silently fails on certain GPT disk images, leaving no EFI_SIMPLE_FILE_SYSTEM_PROTOCOL anywhere in the system. AetherBoot's `li->DeviceHandle` then points to nothing.
**The Solution:** Create a raw FAT32 "superfloppy" -- no partition table, just a bare FAT32 filesystem on the raw device:
```bash
dd if=/dev/zero of=$DISK bs=1M count=64 status=none
mkfs.fat -F 32 -n "GENOS_EFI" $DISK
mmd  -i $DISK ::/EFI ::/EFI/BOOT ::/EFI/GENOS
mcopy -i $DISK BOOTX64.EFI ::/EFI/BOOT/BOOTX64.EFI
mcopy -i $DISK xenos.elf   ::/EFI/GENOS/xenos.elf
```
OVMF treats a superfloppy FAT32 as a single filesystem volume and installs EFI_SIMPLE_FILE_SYSTEM_PROTOCOL directly on the disk handle.
**Performance Impact:** Boot reliability goes from flaky to 100%. Zero performance cost.
**Gotchas:** Must use `mtools` (`mmd`, `mcopy` with `-i`) for host-side manipulation without mounting. The `-i $DISK` flag tells mtools to treat the file as a disk image.
**File:Line Reference:** `tools/boot/boot-test.sh:115-134`

---

## SKILL 10: PE32+ UEFI Linking with lld-link

**Category:** linking, uefi
**The Problem:** UEFI applications must be PE32+ (Windows executable format), not ELF. The UEFI firmware's image loader only understands PE/COFF.
**The Solution:** Use `lld-link-18` (the LLVM Windows linker) in UEFI mode:
```
lld-link-18 -subsystem:efi_application -entry:_abi_entry -nodefaultlib \
  -out:BOOTX64.EFI stage1.o aetherboot.o tpm.o capability_init.o sha256.o dev_fingerprint.o
```
Compile with `--target=x86_64-unknown-windows` (not `x86_64-unknown-none-elf`).
ASM with `nasm -f win64` (not `-f elf64`).
**Performance Impact:** N/A -- this is a correctness requirement.
**Gotchas:** The entry point is `_abi_entry` (from stage1.asm), NOT `efi_main`. stage1.asm performs the ABI transition then calls `efi_main`. Earlier sprints used `-entry:efi_main` which skipped the ABI setup. `-nodefaultlib` is essential -- there is no Windows CRT.
**File:Line Reference:** `tools/boot/boot-test.sh:105-110`

---

## SKILL 11: ELF64 Freestanding Linking with ld.lld

**Category:** linking, kernel
**The Problem:** Linking a kernel at VMA=0xFFFFFFFF80000000 (higher half) but LMA=0x100000 (physical 1MB) requires a split-address linker script.
**The Solution:** Use `ld.lld-18 -T link.ld --no-dynamic-linker -static`:
- `link.ld` defines `KERNEL_BASE = 0xFFFFFFFF80000000` and `KERN_LMA = 0x100000`
- `.text KERNEL_BASE : AT(KERN_LMA)` sets VMA and LMA independently
- `KEEP(*(.text.entry))` anchors `_xenos_start` at byte 0 of .text
- `--no-dynamic-linker -static` eliminates dynamic linking metadata
**Performance Impact:** N/A -- correctness.
**Gotchas:** `-mcmodel=kernel` is REQUIRED in CFLAGS. Without it, clang uses the small code model (32-bit) and cannot generate relocations for symbols at 0xFFFFFFFF80000000. The `AT(KERN_LMA)` only needs to appear on the FIRST section; ld tracks the LMA cursor implicitly thereafter.
**File:Line Reference:** `kernel/xenos/link.ld:1-248`, `kernel/xenos/Makefile:89`

---

## SKILL 12: QEMU Boot Testing in CI

**Category:** ci, testing
**The Problem:** You cannot run bare-metal code on CI runners. You need to verify the full boot chain (OVMF -> AetherBoot -> kernel -> kmain) without physical hardware.
**The Solution:** QEMU with OVMF firmware, serial output to file, grep for sentinel:
```bash
timeout $TIMEOUT qemu-system-x86_64 \
  -machine q35 -smp 4 -m 512M \
  -drive if=pflash,format=raw,readonly=on,file=$OVMF_CODE \
  -drive if=pflash,format=raw,file=$OVMF_VARS \
  -device qemu-xhci,id=xhci -device usb-storage,bus=xhci.0,drive=usb0 \
  -drive format=raw,file=$DISK,if=none,id=usb0 \
  -display none -nographic -serial file:$SERIAL -no-reboot -no-shutdown
```
Then: `grep -q '\[XENOS\]' $SERIAL`
**Performance Impact:** Full boot test in <30s with KVM, <180s with TCG (software emulation).
**Gotchas:** KVM detection is critical: `-enable-kvm -cpu host` if `/dev/kvm` exists, otherwise `-cpu Broadwell`. USB mass storage is mandatory -- AHCI+GPT causes PartitionDxe failures. OVMF_VARS must be COPIED (not used in-place) because QEMU writes to it.
**File:Line Reference:** `tools/boot/boot-test.sh:136-173`, `.github/workflows/qemu-boot-test.yml`

---

## SKILL 13: Boot Diagnostic Byte Analysis

**Category:** testing, debugging
**The Problem:** When a kernel fails to boot, "no output" is not actionable. You need to know WHERE in the boot chain the failure occurred.
**The Solution:** Progressive serial sentinel characters emitted at each boot stage:
- `X` -- entry point reached (`_xenos_start`)
- `S` -- BSS zeroing + stack switch complete
- `K` -- `kmain()` reached
- `[XENOS]` -- kernel banner printed, full boot success
The boot-test script checks for each sentinel and reports which stage failed.
**Performance Impact:** Zero runtime cost (single byte writes to serial port 0x3F8).
**Gotchas:** Earlier stages write single characters (not strings) to minimize the code required before the full serial driver is initialized. `grep -qP 'XS'` uses Perl regex which may not be available -- fall back to `grep -q 'S'`.
**File:Line Reference:** `tools/boot/boot-test.sh:184-210`

---

## SKILL 14: Dynamic Dev Fingerprint Generation

**Category:** build, security
**The Problem:** AetherBoot verifies the kernel hash against `XPKG_ROOT_FINGERPRINT[32]`. For dev/CI builds, this hash must match the actual kernel that was just compiled. Hardcoding a hash breaks every rebuild.
**The Solution:** Generate the fingerprint at build time:
```bash
KERN_HASH=$(sha256sum $BUILD/xenos.elf | awk '{print $1}')
HASH_ARRAY=$(echo "$KERN_HASH" | sed 's/../0x&, /g' | sed 's/, $//')
cat > dev_fingerprint.c << EOF
const UINT8 XPKG_ROOT_FINGERPRINT[32] = { $HASH_ARRAY };
EOF
clang-18 $CFLAGS_EFI -c dev_fingerprint.c -o dev_fingerprint.o
```
This auto-generated file is linked into BOOTX64.EFI.
**Performance Impact:** Negligible -- one sha256sum + one compile.
**Gotchas:** The fingerprint file is generated AFTER xenos.elf is built but BEFORE BOOTX64.EFI is linked. Order matters. For production ISO builds, a pre-provisioned hash replaces this dev sentinel.
**File:Line Reference:** `tools/boot/boot-test.sh:92-102`

---

## SKILL 15: -fsyntax-only vs Real Compilation (The CI Gap)

**Category:** ci, testing
**The Problem:** Many CI workflows use `clang -fsyntax-only` to check C code. This validates syntax, types, and includes but does NOT generate object code. It misses linker errors (undefined symbols, duplicate symbols, section attribute conflicts).
**The Solution:** Use a tiered approach:
- Sprint CI gates: `-fsyntax-only` for fast feedback (< 5s per file)
- Sprint CI gates: `-c -o /dev/null` for compile-to-object without linking
- Makefile `compile-check` target: compiles all objects but skips link
- Makefile `link` target: full compile + link -> xenos.elf
- QEMU boot test: full compile + link + boot verification
**Performance Impact:** `-fsyntax-only` is ~3x faster than `-c`. But it misses real bugs.
**Gotchas:** The sprint42.yml workflow uses BOTH: `-c -Werror` for test files and `-fsyntax-only` for source files. The former catches more issues. Always prefer `-c` over `-fsyntax-only` when CI time permits.
**File:Line Reference:** `.github/workflows/sprint42.yml:51-58, 77-83`

---

## SKILL 16: Boot-Kernel Size Reduction via -D Overrides

**Category:** makefile, optimization
**The Problem:** Subsystem compile-time constants (WAL ring size, cache pages, blob slots) default to large values for development. In the kernel image, memory is constrained.
**The Solution:** Override constants via `-D` flags in CFLAGS_BASE:
```
-DXSTORE_WAL_RING_SIZE=64u -DXSTORE_CACHE_PAGES=16u
-DXPKG_MAX_INSTALLED=32u -DXSEC_AUDIT_RING_SIZE=64u
-DXBLOB_INDEX_SLOTS=4096u -DORANGE_BLOB_REGION_SIZE='(512u*1024u)'
-DTCP_TCB_MAX=16u -DXFRAME_FB_MAX_W=1280u -DXFRAME_FB_MAX_H=800u
-DXMIND_VOCAB_SIZE=128256u -DXSHEET_MAX_ROWS=64u -DXSHEET_MAX_COLS=16u
```
**Performance Impact:** Reduces BSS by megabytes. The linker script asserts `__bss_size < 512MB` as a budget guard.
**Gotchas:** Source files must use `#ifndef MACRO` / `#define MACRO default` pattern so that -D overrides take precedence. If a file uses `#define MACRO value` without the guard, the -D flag causes a macro redefinition warning (promoted to error by -Werror).
**File:Line Reference:** `kernel/xenos/Makefile:38-48`, `kernel/xenos/link.ld:247`

---

## SKILL 17: #ifndef Guards for Makefile -D Override Compatibility

**Category:** c-patterns, makefile
**The Problem:** When the Makefile passes `-DXSTORE_WAL_RING_SIZE=64u` and the source file also does `#define XSTORE_WAL_RING_SIZE 256u`, clang emits a macro redefinition warning (fatal with -Werror).
**The Solution:** Every overridable constant in source uses:
```c
#ifndef XSTORE_WAL_RING_SIZE
#define XSTORE_WAL_RING_SIZE 256u  /* default for userspace / tests */
#endif
```
The Makefile's `-D` flag wins because it is defined before the source file's `#ifndef` check.
**Performance Impact:** Zero. Purely a compile-time pattern.
**Gotchas:** Must also handle `PAL_FREESTANDING` guard. Many source files check `#ifdef PAL_FREESTANDING` to switch between freestanding and hosted implementations. The Makefile sets `-DGENOS_BOOT_KERNEL` (not PAL_FREESTANDING directly), and `pal.h` defines `PAL_FREESTANDING` when `GENOS_BOOT_KERNEL` is set.
**File:Line Reference:** Pattern used across all subsystem headers

---

## SKILL 18: Order-Only Prerequisites for PCH

**Category:** makefile
**The Problem:** You want the PCH to be built BEFORE any `.o` file, but you do NOT want every `.o` to rebuild when the PCH changes (that is handled by the PCH's own prerequisite on `$(PCH_DEPS)`).
**The Solution:** Use Make's order-only prerequisite syntax:
```make
$(BUILD)/kernel/%.o: %.c | $(PCH_NOSSE)
```
The `|` separates normal prerequisites (before `|`) from order-only (after). Order-only prerequisites must exist but their timestamp is NOT checked for rebuild decisions.
**Performance Impact:** Prevents unnecessary full rebuilds. Without `|`, changing xenos.h would rebuild all 160+ objects TWICE (once for the PCH rebuild, once for the timestamp propagation).
**Gotchas:** The PCH_DEPS list (`include/xenos.h` and `../../pal/include/pal.h`) is a NORMAL prerequisite of the PCH target itself, so header changes DO rebuild the PCH. The order-only connection just prevents the rebuild cascade to .o files.
**File:Line Reference:** `kernel/xenos/Makefile:590-593`

---

## SKILL 19: Pattern Substitution for Output Directory Mapping

**Category:** makefile
**The Problem:** Source files live in deeply nested directories (`../../net/xnet/core/netif.c`). Object files need to go into a flat-ish build directory (`$(BUILD)/xnet/core/netif.o`). Manual enumeration is error-prone.
**The Solution:** Use Make's `$(patsubst)` to rewrite paths:
```make
XNET_CORE_OBJS = $(patsubst ../../net/xnet/%.c,$(BUILD)/xnet/%.o,$(XNET_CORE_SRCS))
```
Combined with `$(filter)` to split source lists by directory:
```make
XNET_CORE_SRCS = $(filter-out ../../net/xnet/drv/%,$(XNET_SRCS))
XNET_DRV_SRCS  = $(filter ../../net/xnet/drv/%,$(XNET_SRCS))
```
**Performance Impact:** Maintenance -- adding a new file requires only adding to SRCS list.
**Gotchas:** XPKG has files in multiple subdirectories (`format/`, `verify/`, `solver/`, etc.) that flatten to `$(BUILD)/xpkg/` -- these require explicit rules because the depth varies. patsubst only replaces one prefix pattern.
**File:Line Reference:** `kernel/xenos/Makefile:446-529`

---

## SKILL 20: SHA-Pinned GitHub Actions

**Category:** ci, security
**The Problem:** Using `actions/checkout@v4` (mutable tag) means a compromised action can inject code into your CI pipeline. Tags can be force-pushed.
**The Solution:** Pin actions to full commit SHA:
```yaml
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
- uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02  # v4.6.2
- uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
```
Comment the version tag for readability.
**Performance Impact:** Zero. Same action, just immutable reference.
**Gotchas:** Older workflows (sprint47) still use `@v4` tag -- technical debt. New workflows must use SHA. Exception: `persist-credentials: false` should always be set on checkout.
**File:Line Reference:** `.github/workflows/foundation.yml:40,76`, `.github/workflows/e2e-tests.yml:56`

---

## SKILL 21: Path-Filtered CI Triggers

**Category:** ci, efficiency
**The Problem:** Running all CI jobs on every push wastes runner minutes. A change to `net/xnet/` should not trigger the XSTORE CI gate.
**The Solution:** Use `paths:` filter on both `push` and `pull_request` triggers:
```yaml
on:
  push:
    paths:
      - 'store/xstore/**'
      - 'tests/sprint42/**'
      - '.github/workflows/sprint42.yml'
```
**Performance Impact:** Reduces CI runner usage by 80%+ for focused changes.
**Gotchas:** Always include the workflow file itself in the paths filter. Otherwise, changes to the workflow are not tested. Also include test directories -- test changes should trigger the gate they test.
**File:Line Reference:** `.github/workflows/sprint42.yml:12-29`

---

## SKILL 22: Gate Job Pattern (Fan-In Merge Gate)

**Category:** ci, workflow-design
**The Problem:** GitHub branch protection requires a SINGLE status check to pass. But CI has multiple parallel jobs (compile, lint, test, cppcheck). You need one "did everything pass?" check.
**The Solution:** A lightweight gate job that depends on all others:
```yaml
gate:
  name: Sprint 42 Gate
  runs-on: ubuntu-24.04
  needs: [c-compile, c-syntax, python-e2e]
  steps:
    - run: echo "SPRINT 42 — ALL PASS"
```
Branch protection requires only the `gate` job, which implicitly requires all dependencies.
**Performance Impact:** Zero cost (gate job is ~2s).
**Gotchas:** Without `if: always()`, the gate job is skipped if any dependency fails (which is the default behavior you want for a required check -- skipped = not success). With `if: always()`, you must manually check each dependency result (see e2e-tests.yml:224-235).
**File:Line Reference:** `.github/workflows/sprint42.yml:120-136`, `.github/workflows/e2e-tests.yml:219-240`

---

## SKILL 23: -DGENOS_BOOT_KERNEL Guard

**Category:** makefile, c-patterns
**The Problem:** Source files must compile in two contexts: (1) standalone testing/hosted and (2) linked into the kernel monolith. In kernel context, many functions need stubs, reduced buffer sizes, or different implementations.
**The Solution:** The Makefile sets `-DGENOS_BOOT_KERNEL` in CFLAGS_BASE. Source files check:
```c
#ifdef GENOS_BOOT_KERNEL
  // reduced-size buffers, stub I/O, etc.
#else
  // full-size hosted implementation
#endif
```
**Performance Impact:** Enables the boot-kernel size reduction (Skill 16) to coexist with full-featured test builds.
**Gotchas:** This is different from `PAL_FREESTANDING` which controls the PAL abstraction layer. `GENOS_BOOT_KERNEL` is broader -- it means "this code is being linked into the kernel image."
**File:Line Reference:** `kernel/xenos/Makefile:37`

---

## SKILL 24: Linker Script Section Ordering with KEEP

**Category:** linking
**The Problem:** The kernel entry point `_xenos_start` MUST be at the very first byte of the `.text` section (VMA = KERNEL_BASE exactly). The linker may reorder input sections.
**The Solution:** `KEEP(*(.text.entry))` in the linker script anchors the entry section first. In assembly, `_xenos_start` is placed in `.section .text.entry`. KEEP prevents garbage collection. The wildcard `*(.text .text.*)` follows.
**Performance Impact:** Correctness -- without this, AetherBoot jumps to `e_entry = KERNEL_BASE` and lands on whatever the linker put first (possibly a random function).
**Gotchas:** The section name `.text.entry` is a convention, not a standard. It must match between the assembly source and the linker script.
**File:Line Reference:** `kernel/xenos/link.ld:124-131`

---

## SKILL 25: LMA/VMA Split in Linker Script

**Category:** linking, kernel
**The Problem:** Kernel executes at VMA 0xFFFFFFFF80000000 (higher half) but UEFI loads it at LMA 0x100000 (physical 1MB). The ELF must encode both addresses.
**The Solution:** `.text KERNEL_BASE : AT(KERN_LMA)` sets VMA to KERNEL_BASE and LMA to KERN_LMA. Subsequent sections (`AT()` omitted) automatically track the LMA cursor. AetherBoot reads `p_paddr` from PT_LOAD headers, allocates physical memory there, copies segments, builds PML4 mapping physical to virtual, then jumps to `e_entry` (VMA).
**Performance Impact:** Correctness.
**Gotchas:** `load_min` across all PT_LOAD segments must equal KERN_LMA. If a section's `AT()` breaks the LMA sequence, AetherBoot's `(p_paddr - load_min)` offset calculation produces wrong results.
**File:Line Reference:** `kernel/xenos/link.ld:107-131`

---

## SKILL 26: BSS Size Budget Assertion

**Category:** linking, safety
**The Problem:** Static arrays in a monolithic kernel can silently grow BSS to enormous sizes. AetherBoot maps up to 256MB for the kernel span. Exceeding this causes a boot failure with no error message.
**The Solution:** Linker script assertion:
```
ASSERT(__bss_size < 512 * 1024 * 1024, "BSS exceeds 512 MB budget — reduce static arrays")
```
This catches BSS bloat at link time, before it reaches QEMU or hardware.
**Performance Impact:** Zero runtime cost. Build-time safety net.
**Gotchas:** The 512MB limit is generous (AetherBoot only maps 256MB). The extra headroom allows BSS growth during development. Tighten for production.
**File:Line Reference:** `kernel/xenos/link.ld:247`

---

## SKILL 27: Discard Section in Linker Script

**Category:** linking
**The Problem:** Clang generates `.eh_frame`, `.eh_frame_hdr`, `.comment`, `.note.GNU-stack`, and `.gnu*` sections even for freestanding C code. These waste space in the kernel image.
**The Solution:** `/DISCARD/` section in the linker script:
```
/DISCARD/ : {
    *(.eh_frame) *(.eh_frame_hdr) *(.comment)
    *(.gnu*) *(.note.GNU-stack) *(.multiboot2) *(.multiboot)
}
```
**Performance Impact:** Saves ~10-50KB in the kernel image.
**Gotchas:** Do NOT discard `.note.xenos` (custom metadata section). It carries the XENOS magic number and build timestamp.
**File:Line Reference:** `kernel/xenos/link.ld:214-223`

---

## SKILL 28: OVMF Firmware Path Auto-Detection

**Category:** boot, portability
**The Problem:** OVMF firmware files are installed at different paths on different distros: Ubuntu (`/usr/share/OVMF/`), Fedora (`/usr/share/edk2/ovmf/`), and the filename varies (`OVMF_CODE_4M.fd` vs `OVMF_CODE.fd`).
**The Solution:** Iterate through known paths and use the first hit:
```bash
for p in /usr/share/OVMF/OVMF_CODE_4M.fd /usr/share/OVMF/OVMF_CODE.fd \
         /usr/share/edk2/ovmf/OVMF_CODE.4m.fd; do
  [ -f "$p" ] && { OVMF_CODE="$p"; break; }
done
```
**Performance Impact:** Portability -- same script works on Ubuntu, Fedora, Arch.
**Gotchas:** Must also auto-detect OVMF_VARS and COPY it before use (QEMU writes to the vars file).
**File:Line Reference:** `tools/boot/boot-test.sh:37-51`

---

## SKILL 29: KVM Auto-Detection with Timeout Adjustment

**Category:** boot, ci
**The Problem:** QEMU with TCG (software emulation) is 10-50x slower than KVM. CI runners may or may not have KVM available. A fixed timeout that works for KVM fails for TCG.
**The Solution:** Check for `/dev/kvm` and adjust both acceleration and timeout:
```bash
if [ -e /dev/kvm ]; then
    ACCEL="-enable-kvm -cpu host"
    QEMU_TIMEOUT=30    # KVM: boot completes in <10s
else
    ACCEL="-cpu Broadwell"
    QEMU_TIMEOUT=180   # TCG: needs longer timeout
fi
```
**Performance Impact:** 6x timeout difference prevents CI failures on runners without KVM.
**Gotchas:** GitHub Codespaces provide KVM. Standard GitHub Actions runners do NOT. `-cpu Broadwell` is used for TCG because it provides a reasonable x86_64 feature set without requiring KVM.
**File:Line Reference:** `tools/boot/boot-test.sh:142-150`

---

## SKILL 30: Toolchain Version Tagging

**Category:** docker, versioning
**The Problem:** When the toolchain image changes (e.g., clang-18 -> clang-19), you need to be able to roll back to the previous version.
**The Solution:** `build-toolchain.sh` reads a version from `TOOLCHAIN_VERSION` file and tags the image with both the version and `latest`:
```bash
VERSION="$(cat "$SCRIPT_DIR/TOOLCHAIN_VERSION" 2>/dev/null || echo "v1")"
docker build ... -t "$FULL_TAG:$VERSION" -t "$FULL_TAG:latest" -t "genos-toolchain:local"
```
A manifest file inside the image records build date + tool versions.
**Performance Impact:** Enables rollback and audit.
**Gotchas:** Always tag with `genos-toolchain:local` for local development use via `--build-arg TOOLCHAIN_IMAGE=genos-toolchain:local`.
**File:Line Reference:** `tools/docker/build-toolchain.sh:14-38`

---

## SKILL 31: Compile-Check vs Link Target Separation

**Category:** makefile
**The Problem:** Some CI environments install `clang-18` but not `ld.lld-18`. You want to verify all files compile without requiring the linker.
**The Solution:** Separate targets:
```make
all: link           # Full build (compile + link)
link: $(ALL_OBJS)   # Produces xenos.elf
compile-check: $(ALL_OBJS)  # Compile only, no link
```
**Performance Impact:** `compile-check` is ~10s faster than `link` (linker adds overhead for 160+ objects).
**Gotchas:** `compile-check` misses linker-level errors: undefined symbols, duplicate symbols, section attribute conflicts. Use `link` for definitive CI gates.
**File:Line Reference:** `kernel/xenos/Makefile:557-570`

---

## SKILL 32: .DEFAULT_GOAL Declaration

**Category:** makefile
**The Problem:** Without `.DEFAULT_GOAL`, Make uses the first target it encounters. In this Makefile, the PCH targets are defined before `all`, so `make` would just build the PCH and exit.
**The Solution:** `.DEFAULT_GOAL := all` at line 96, before any target rules.
**Performance Impact:** Prevents developer confusion.
**Gotchas:** Must appear BEFORE the PCH rules (which are targets). If placed after, Make may already have chosen a default.
**File:Line Reference:** `kernel/xenos/Makefile:96`

---

## SKILL 33: Single-TU Inclusion Pattern (text_input.c)

**Category:** c-patterns, linking
**The Problem:** `text_input.c` is needed by both `notes.c` and `mail.c`. If compiled as a separate `.o`, its symbols are available to both but you get ONE copy. If each file needs its own static state, you want per-file inclusion.
**The Solution:** `#include "text_input.c"` directly inside `notes.c` and `mail.c`. text_input.c is NOT listed in the Makefile source list to avoid duplicate symbols.
**Performance Impact:** Zero -- same code, different compilation model.
**Gotchas:** Comment in Makefile is critical: "text_input.c is #included directly into notes.c and mail.c (single-TU inclusion pattern) and must NOT appear here to avoid duplicate symbols at link time." If someone adds it to the source list, the build breaks with duplicate symbols.
**File:Line Reference:** `kernel/xenos/Makefile:302-304`

---

## SKILL 34: Driver Exclusion from Unity Builds

**Category:** unity, makefile
**The Problem:** Network drivers (`e1000.c`, `virtio_net.c`) have hardware-specific static variables (MMIO base addresses, ring buffer pointers) that would collide in a unity TU.
**The Solution:** Drivers are explicitly excluded from unity files and always compiled individually. In unity mode, the XNET source list contains ONLY the drivers:
```make
ifeq ($(UNITY_BUILD),1)
XNET_SRCS = \
    ../../net/xnet/drv/virtio_net.c \
    ../../net/xnet/drv/e1000.c
XNET_UNITY_SRC = ../../net/xnet_core_unity.c
```
Similarly, `aes_ni.c` is excluded from `xsec_unity.c` because it requires different SIMD flags.
**Performance Impact:** Correctness -- prevents false unification of hardware-specific state.
**Gotchas:** Any file with hardware-specific MMIO statics, interrupt handler statics, or different CFLAGS requirements must be excluded from unity builds.
**File:Line Reference:** `kernel/xenos/Makefile:190-206`, `sec/xsec_unity.c:10-12`

---

## SKILL 35: cppcheck in CI Pipeline

**Category:** ci, static-analysis
**The Problem:** Clang warnings catch many issues, but cppcheck finds different classes of bugs: use-after-free, null pointer dereference, buffer overflows, portability issues.
**The Solution:** Run cppcheck as a separate CI job:
```yaml
cppcheck --error-exitcode=1 --enable=warning,style \
  --suppress=missingInclude --suppress=unusedFunction \
  --force FILE1.c FILE2.c ...
```
**Performance Impact:** Adds ~30s to CI but catches bugs clang misses.
**Gotchas:** `--suppress=missingInclude` is essential for freestanding code (no system headers). `--suppress=unusedFunction` avoids false positives for test helper functions. `--force` checks all `#ifdef` branches.
**File:Line Reference:** `.github/workflows/e2e-tests.yml:184-214`, `.github/workflows/foundation.yml:48-59`

---

## SKILL 36: ISO Build Pipeline Orchestration

**Category:** ci, iso
**The Problem:** Building a bootable ISO requires: compile kernel, boot-verify, assemble rootfs, create EFI partition, generate ISO image. These stages have strict ordering dependencies.
**The Solution:** The iso-build workflow chains:
1. Install dependencies (xorriso, mtools, dosfstools, debootstrap, grub-efi-amd64-bin)
2. Build kernel via `boot-test.sh` (reuses the same script as QEMU boot test)
3. Verify `[XENOS]` sentinel in serial output
4. Assemble ISO via `build/iso-assemble.py` (if rootfs available)
**Performance Impact:** 30-minute timeout for full ISO build.
**Gotchas:** ISO assembly requires `grub-mkstandalone` + `/usr/lib/grub/x86_64-efi` modules. The workflow verifies both exist before proceeding. Rootfs may not be available in CI (debootstrap requires root), so ISO assembly is conditional.
**File:Line Reference:** `.github/workflows/iso-build.yml`

---

## SKILL 37: Semantic CI Wiring Checks (grep for API presence)

**Category:** ci, verification
**The Problem:** Source code may compile clean but not actually wire up critical functions. For example, `boot_sequence.c` might compile without calling `tpm2_tis_init()`.
**The Solution:** CI jobs that grep for required function calls:
```yaml
- name: Verify TPM measurement wiring present
  run: |
    grep -q "tpm2_tis_init"    init/gensd/boot_sequence.c || exit 1
    grep -q "tpm2_self_test"   init/gensd/boot_sequence.c || exit 1
    grep -q "tpm2_pcr_extend"  init/gensd/boot_sequence.c || exit 1
```
**Performance Impact:** ~1s per check. Catches "compiles but doesn't work" bugs.
**Gotchas:** grep-based checks are brittle -- they match comments and strings too. For production, use AST-level analysis. But for a freestanding OS where the function call IS the critical path, grep is pragmatically correct.
**File:Line Reference:** `.github/workflows/sprint47-boot-hardening.yml:116-127`

---

## SKILL 38: Constant-Time Comparison Verification in CI

**Category:** ci, security
**The Problem:** Hash comparison in boot chain security code must use constant-time comparison (no early exit on first mismatch). A timing side-channel could leak hash bytes.
**The Solution:** CI job greps for the constant-time pattern:
```yaml
- name: Verify constant-time comparison is used
  run: |
    grep -q "diff |=" init/gensd/boot_chain.c || exit 1
```
The `diff |=` pattern (OR-accumulate differences) is the standard constant-time compare idiom.
**Performance Impact:** Zero runtime cost (the comparison itself). CI check is <1s.
**Gotchas:** This is a heuristic check. A more robust approach would use a clang plugin or annotation. But for a known codebase, the pattern check works.
**File:Line Reference:** `.github/workflows/sprint47-boot-hardening.yml:162-168`

---

## SKILL 39: Production ISO Gate (Non-Zero Hash Enforcement)

**Category:** ci, release
**The Problem:** Dev builds use an all-zeros XSTORE_ROOT_HASH sentinel for convenience. Production ISO builds must have a real hash.
**The Solution:** CI job extracts the hash bytes and counts non-zero values:
```yaml
if: github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/')
steps:
  - run: |
      HASH_BYTES=$(grep -A 4 "XSTORE_ROOT_HASH" boot_chain.c | grep -oE '0x[0-9a-fA-F]{2}')
      NONZERO=$(echo "${HASH_BYTES}" | grep -v "0x00" | wc -l)
      [ "${NONZERO}" -eq 0 ] && exit 1
```
Only runs on main branch or tags (not feature branches).
**Performance Impact:** Prevents shipping a dev build to production.
**Gotchas:** The `if:` condition is critical. Feature branches should be allowed to have the all-zeros sentinel for development.
**File:Line Reference:** `.github/workflows/sprint47-boot-hardening.yml:184-215`

---

## SKILL 40: -pipe Compiler Flag

**Category:** makefile, optimization
**The Problem:** By default, clang writes intermediate files to disk between compilation stages (preprocess -> compile -> assemble). On slow I/O (networked filesystems, Docker overlayfs), this adds latency.
**The Solution:** `-pipe` in CFLAGS_BASE tells clang to use OS pipes between stages instead of temporary files.
**Performance Impact:** 5-15% compile time reduction on Docker/overlayfs builds. Negligible on fast SSDs.
**Gotchas:** Slightly increases memory usage (pipe buffers). Not relevant for this codebase size.
**File:Line Reference:** `kernel/xenos/Makefile:36`

---

## SKILL 41: -fvisibility=hidden for Faster Linking

**Category:** makefile, optimization
**The Problem:** By default, all symbols in C files are globally visible (ELF visibility "default"). This creates a large symbol table that the linker must process.
**The Solution:** `-fvisibility=hidden` in CFLAGS_BASE. Only symbols explicitly marked `__attribute__((visibility("default")))` are exported. For a monolithic kernel with no dynamic linking, this is pure win.
**Performance Impact:** Reduces symbol table size -> faster link time. Also enables more aggressive compiler optimizations (no need to preserve ABI for hidden symbols).
**Gotchas:** Not applicable if you need to `dlopen` kernel modules. XENOS is monolithic, so this is safe.
**File:Line Reference:** `kernel/xenos/Makefile:36`

---

## SKILL 42: Intentional -fno-stack-protector with Manual Canaries

**Category:** security, makefile
**The Problem:** `-fno-stack-protector` looks like a security bug. But in a freestanding kernel, the compiler-inserted `__stack_chk_fail` requires a CRT that does not exist.
**The Solution:** Disable compiler stack protector but implement manual canary checks via `stack_guard.c` which provides `__stack_chk_guard` for per-function manual canary checks. Documented in Makefile comment (lines 29-33).
**Performance Impact:** Manual canaries are applied selectively to high-risk functions, not universally. Lower overhead than compiler-inserted checks on every function.
**Gotchas:** If you enable `-fstack-protector` without providing `__stack_chk_fail`, the linker fails with undefined symbol. The Makefile comment is essential documentation for auditors.
**File:Line Reference:** `kernel/xenos/Makefile:29-33`

---

## SKILL 43: USB-Storage QEMU Device (Avoiding AHCI)

**Category:** boot, qemu
**The Problem:** OVMF's AHCI driver combined with GPT partition tables triggers PartitionDxe failures, leaving no EFI_SIMPLE_FILE_SYSTEM_PROTOCOL.
**The Solution:** Use USB mass storage via XHCI:
```
-device qemu-xhci,id=xhci
-device usb-storage,bus=xhci.0,drive=usb0
-drive format=raw,file=$DISK,if=none,id=usb0
```
Combined with the FAT32 superfloppy (Skill 09), OVMF installs SimpleFileSystem directly on the USB disk handle.
**Performance Impact:** Reliability -- 100% boot success rate vs ~50% with AHCI+GPT.
**Gotchas:** The `if=none` and separate `-device` syntax is required. Using `-drive if=usb` does not work with XHCI.
**File:Line Reference:** `tools/boot/boot-test.sh:157-173`

---

## SKILL 44: Permissions Lockdown in CI Workflows

**Category:** ci, security
**The Problem:** GitHub Actions workflows get `write` permissions by default in some contexts. A compromised step could modify repository contents.
**The Solution:** Set minimal permissions at workflow level:
```yaml
permissions:
  contents: read
```
Every GEN.OS workflow uses this pattern. No workflow requests write permissions unless it needs to upload artifacts (which uses a separate token).
**Performance Impact:** Zero.
**Gotchas:** `actions/upload-artifact` does NOT need `contents: write` -- it uses a separate API. Only `git push` or release creation needs write permissions.
**File:Line Reference:** Every workflow file, e.g., `.github/workflows/qemu-boot-test.yml:16-17`

---

## SKILL 45: Workflow File Self-Inclusion in Path Triggers

**Category:** ci
**The Problem:** If you change a workflow file but the path trigger does not include the workflow file itself, the change is not tested.
**The Solution:** Always include the workflow file in its own paths trigger:
```yaml
paths:
  - 'store/xstore/**'
  - '.github/workflows/sprint42.yml'  # self-inclusion
```
**Performance Impact:** Ensures workflow changes are tested.
**Gotchas:** This is easy to forget. Every workflow audit should verify self-inclusion.
**File:Line Reference:** `.github/workflows/sprint42.yml:22`
