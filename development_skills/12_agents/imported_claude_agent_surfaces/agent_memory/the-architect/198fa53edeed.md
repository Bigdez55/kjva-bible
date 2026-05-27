# Production Gap Analysis — GEN.OS vs Production OS (2026-03-29)

Source: direct code audit of kernel, drivers, VFS, net, display, scheduler.

## Key Finding: Ring-3 Is More Complete Than Assumed

- XK_SYS_EXEC (syscall 29) is a real ELF64 loader with PT_LOAD mapping, guard pages,
  e_entry validation, and process PML4 isolation. The ring-3 boundary is real.
- syscall.asm: LSTAR handler is production-quality (SWAPGS, percpu stack, CVE-2012-0217
  canonical RIP check, MDS VERW mitigation).
- xenos_fiber_switch() is a correct cooperative context switch with CR3 reload.
- The claim "everything in ring 0" is outdated — the mechanism is built; the gap is
  fork(), dynamic linker, and filesystem-backed execve().

## Gap 1: Process Model

Critical missing pieces:
- PROC_MAX = 16 (fatal for real session — must be dynamic)
- No fork() / copy-on-write (Node.js child_process.spawn() fails)
- No ET_DYN ELF loader (Electron is dynamically linked — ADR-S23-01 defers this)
- name_va in kern_process_create() is not validated as a user-space address (security gap)
- No filesystem-backed execve() — exec only works from physical ELF address

Estimated must-have LOC: 2,200-4,250

## Gap 2: Storage

Critical missing pieces:
- XSTORE xstore_open() takes I/O callbacks — they are NEVER wired to nvme_read/write
  (this is the P0 blocker; approximately 80-120 LOC to fix)
- No GPT partition parser — cannot find GENOS partition on real NVMe
- XVFS max file size = 4,064 bytes (XSTORE_MAX_VAL_LEN - XVFS_META_SIZE) —
  fatal for any real file; must use XBLOB for data blobs
- No NVMe namespace provisioning / superblock discovery on boot
- vDRAM NVMe spill is conditional on weak symbol resolving (unverified on HW)

Estimated must-have LOC: 730-1,070

## Gap 3: Networking

State: virtio_net.c and e1000.c are real, functional drivers (QEMU only).

Critical missing pieces:
- No DHCP client anywhere in net/xnet (grep returns zero results)
- wifi.c stub: s_iwl_base = NULL, all CSR functions are no-ops
  HP EliteBook x360 has NO Ethernet — only Intel AC 9560 Wi-Fi (PCI 8086:A370)
  This makes wifi.c the P0 bare-hardware network blocker
- No WPA2/WPA3 supplicant
- e1000.c targets 82540EM; real EliteBook has I219-LM (8086:15E3) = different driver

Estimated must-have LOC (QEMU): 400-600 (DHCP only)
Estimated must-have LOC (bare HW): 5,600-9,300

## Gap 4: Display

State: GOP framebuffer path (HHDM + write-combining) works end-to-end.
DPIPE-001..003 pipeline is wired and P0 audit verified.

Critical missing pieces:
- drm.c calls open("/dev/dri/card0") — XVFS has no device node concept.
  DRM path is dead until devfs or direct i915 register access.
- No vsync / page flip — LAPIC display interrupt not wired; tearing guaranteed
- No double-buffer mechanism in pipeline.c
- No hardware GPU compositing (all software ARGB blending)

GOP framebuffer fallback (igpu.c HHDM path) is the correct initial deployment path.
Focus: wire vsync interrupt + double-buffer. Defer DRM until devfs exists.

Estimated must-have LOC: 700-1,200

## Gap 5: SMP

README.md §Known Issues explicitly: "SMP wakeup sequence (SIPI broadcast) not yet
implemented; single-CPU boot only."

Critical missing pieces:
- No AP trampoline (real-mode → 64-bit) — no SIPI
- preempt_disable/enable hardcoded to g_percpu[0] — must index by APIC ID
- No per-CPU run queues — scheduler is flat 16-slot array
- No MADT parsing for AP APIC ID discovery

Not a boot blocker. Contra-rotation scheduler manages single-core contention via
thermal phase staggering. SMP enables XMIND inference + compositor to run in parallel.

Estimated must-have LOC for SMP: 1,200-1,900

## Deployment Sequence Recommendation

Phase A (QEMU to Desktop):
1. XSTORE ↔ NVMe callback bridge (80-120 LOC) — P0
2. GPT parser + XSTORE mount on boot (350-500 LOC)
3. DHCP client (400-600 LOC)
4. PROC_MAX dynamic table + fork/COW (1,000-1,900 LOC)
5. Double-buffer + vsync interrupt (700-1,200 LOC)
6. User-VA validation in syscalls (100-150 LOC)

Phase B (Bare Hardware):
7. Intel AC 9560 Wi-Fi firmware loader + TX/RX queues (3,500-5,500 LOC)
8. WPA2/WPA3 (1,000-2,000 LOC)
9. ET_DYN ELF loader (600-1,000 LOC)
10. XVFS large-file via XBLOB (500-800 LOC)

Phase C (Production Quality):
11. SMP: AP trampoline + per-CPU queues (1,200-1,900 LOC)
12. Hardware GPU compositing (1,500-2,500 LOC)
13. NVMe MSI-X interrupt mode (400-600 LOC)

## Critical Architecture Invariants to Preserve

- xstore_open() I/O callback abstraction is correct — DO NOT embed nvme_read()
  directly in xstore.c. Implement thin callback shim in a new file (e.g.,
  store/xstore/backends/nvme_backend.c)
- XVFS metadata (XSTORE) vs data (XBLOB) split must be preserved when raising file size limit
- The cooperative scheduler + lazy preemption design is intentional and compatible
  with the contra-rotation thermal scheduler. Do not replace with a full CFS-style
  preemptive scheduler without auditing all spinlock sites.
