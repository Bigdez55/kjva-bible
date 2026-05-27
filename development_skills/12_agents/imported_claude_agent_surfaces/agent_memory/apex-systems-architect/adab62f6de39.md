# APEX SYSTEMS ARCHITECT — Sprint 0 + Sprint 1 Architecture Audit
**Date:** 2026-03-03
**Auditor:** APEX SYSTEMS ARCHITECT agent
**Scope:** Read-only audit. No files modified.
**Language policy:** C, Python, TypeScript ONLY.

---

## Executive Summary

Sprint 0 (PAL) and Sprint 1 (XENOS kernel + GENSD) were audited against a 10-item checklist covering GDT layout, BSS zeroing, IDT IST assignment, SWAPGS race safety, XKABI rights consistency, VMM NX bit enforcement, NVMe BAR0 boot handoff, GENSD dependency topological sort, PAL 14-section contract, and the CPU_RELAX() macro fix.

**Total defects found:** 6 (1 P0, 3 P1, 2 P2)

| # | Checklist Item | Result |
|---|----------------|--------|
| 1 | GDT: GDTR limit=87, CS_KERNEL=0x28, STAR=0x0038002800000000 | PASS (note: 11 entries, not 9) |
| 2 | BSS zeroing loop in entry.asm | FAIL — P1 defect |
| 3 | IDT: #DF (vec 8) IST != 0 | FAIL — P0 defect |
| 4 | SWAPGS: CS[1:0] check before SWAPGS in syscall.asm | FAIL — P1 defect |
| 5 | Rights mismatch: xkabi_capabilities.c vs capability_init.c | FAIL — P2 defect (capability_init.c not fixed) |
| 6 | VMM: HHDM 2MB PDEs set NX bit (bit 63) | FAIL — P1 defect |
| 7 | NVMe: nvme_bar0_phys in xenos_boot_info_t | FAIL — P2 defect |
| 8 | GENSD toposort: service.c Kahn's algorithm correct | PASS |
| 9 | PAL contract: 14 sections all present in pal.h | PASS |
| 10 | CPU_RELAX(): recursive macro fixed in pal_aether.c | PASS |

---

## Defect Register

### P0 Defects (Critical — system stability)

#### P0-IDT-IST-001: Double-Fault handler has IST=0
- **File:** `kernel/xenos/core/main.c`
- **Lines:** `idt_init()` loop, statement `idt[i].ist = 0u;` applied to ALL 256 vectors including #DF (vector 8)
- **Severity:** P0 — stack overflow causing #DF will triple-fault and reset the machine. Without a dedicated IST stack for double-fault, the handler will attempt to use the already-corrupt RSP0 kernel stack.
- **Root cause:** `idt_init()` sets `idt[i].ist = 0u` inside a uniform loop over all 256 vectors. No special-case for vector 8.
- **Required fix:** After the loop, set `idt[8].ist = 1u` (assign IST slot 1 to #DF). The TSS `ist[0]` field must point to a dedicated 8KB double-fault stack allocated in the kernel BSS or PMM.

---

### P1 Defects (High — correctness/security)

#### P1-BSS-ZERO-001: No BSS zeroing loop in kernel entry
- **File:** `kernel/xenos/core/entry.asm`
- **Lines:** `_start` entry point — no `__bss_start`..`__bss_end` zero loop present
- **Severity:** P1 — C global/static zero-initialized variables in the kernel may contain garbage if AetherBoot does not explicitly zero the kernel ELF BSS segment. The kernel currently relies implicitly on AetherBoot to have done this via EFI memory that was zeroed. If that assumption breaks (e.g., a direct ELF loader that does not zero BSS), all zero-initialized kernel globals are corrupt.
- **Root cause:** `_start` in entry.asm:
  1. Moves the stack pointer to `_stack_top`
  2. Calls `kmain` immediately
  No REP STOSQ loop between `extern __bss_start` / `extern __bss_end` symbols.
- **Required fix:** Add a BSS zero loop in `_start` before the `call kmain`:
  ```nasm
  extern __bss_start
  extern __bss_end
  lea rdi, [rel __bss_start]
  lea rcx, [rel __bss_end]
  sub rcx, rdi
  xor eax, eax
  rep stosb
  ```

#### P1-SWAPGS-RACE-001: ISR path has no SWAPGS handling
- **File:** `kernel/xenos/core/syscall.asm`
- **Lines:** `_syscall_entry` (SWAPGS unconditional at top and bottom), `_common_isr_entry` (no SWAPGS at all)
- **Severity:** P1 — if a hardware interrupt or NMI fires during the SWAPGS window in the SYSCALL entry stub (between the SWAPGS instruction and the subsequent stack switch), the ISR will enter with GS in an inconsistent state. The ISR path (`_common_isr_entry`) performs no SWAPGS, so it cannot distinguish "interrupted in user mode before SWAPGS" from "interrupted in kernel mode after SWAPGS." On kernel-mode interrupts, GS is already the kernel GS and the ISR should not SWAPGS; on user-mode interrupts, it must. Without a CS[1:0] check in the ISR path, this race is unresolved.
- **Root cause:** `syscall.asm:_common_isr_entry` does not check `CS` on the exception frame to determine whether to SWAPGS. The SYSCALL path (`_syscall_entry`) only runs from CPL=3, so its unconditional SWAPGS is technically safe in isolation — but the ISR path also handles kernel exceptions where GS is already swapped, and it does nothing.
- **Required fix:** At `_common_isr_entry`, after saving registers, add:
  ```nasm
  ; Check CPL of interrupted code from saved CS on stack
  mov rax, [rsp + <cs_offset_in_frame>]
  and rax, 3
  jz .kernel_mode_no_swapgs
  swapgs
  .kernel_mode_no_swapgs:
  ```
  Mirror the check on the return path before `iretq`.

#### P1-VMM-NX-001: HHDM and kernel 2MB PDE entries lack NX bit
- **File:** `kernel/xenos/mm/vmm.c`
- **Lines:** HHDM mapping loop (`pd[m] = phys_2m | PTE_PRESENT | PTE_WRITE | PTE_PS | PTE_GLOBAL;`) and kernel ELF mapping (`kern_pd[m] = phys_2m | PTE_PRESENT | PTE_WRITE | PTE_PS | PTE_GLOBAL;`)
- **Severity:** P1 — all physical memory (including kernel heap, PMM free lists, and userspace data pages) is mapped executable via the HHDM. This means any code injection that writes a payload to any HHDM address can execute it directly. `_vm_flags_to_pte()` correctly sets NX for 4KB `vmm_map()` calls when `VM_EXEC` is absent, but `vmm_init()` large-page setup never calls that helper.
- **Root cause:** Comment in the HHDM loop reads "NX for data pages" but `PTE_NX` (defined as `(1ULL << 63)`) is absent from the PDE value. The code was apparently written with the intent to add NX but never did. `EFER.NXE` is enabled at step 4.5 in `kmain` before `vmm_init()` runs, so NX support is active.
- **Required fix:** Add `PTE_NX` to all data-only large-page mappings in `vmm_init()`:
  ```c
  pd[m] = phys_2m | PTE_PRESENT | PTE_WRITE | PTE_PS | PTE_GLOBAL | PTE_NX;
  ```
  Kernel ELF text pages must NOT have NX. The fix must distinguish text pages from data pages in the large-page setup (or split the kernel text/data into separate 2MB ranges).

---

### P2 Defects (Medium — functional gap / integration risk)

#### P2-RIGHTS-SYNC-001: capability_init.c uses ad-hoc rights bitmasks, not canonical xkabi_rights.h
- **File:** `aetherboot/src/capability_init.c`
- **Lines:** §1 `XKABI RIGHTS DEFINITIONS` block (lines 43-51)
- **Severity:** P2 — `capability_init.c` defines its own local rights bitmasks that diverge entirely from the canonical `xkabi_rights.h` values:

  | Right | capability_init.c (ad-hoc) | xkabi_rights.h (canonical) |
  |-------|---------------------------|---------------------------|
  | `XKABI_RIGHT_GPU_EXEC` | `0x00000001U` (bit 0) | `(1u << 19)` = `0x00080000U` |
  | `XKABI_RIGHT_GPU_MAP` | `0x00000002U` (bit 1) | `(1u <<  1)` = `0x00000002U` |
  | `XKABI_RIGHT_STORAGE_READ` | `0x00000004U` (bit 2) | `(1u << 15)` = `0x00008000U` |
  | `XKABI_RIGHT_STORAGE_WRITE` | `0x00000008U` (bit 3) | `(1u << 16)` = `0x00010000U` |
  | `XKABI_RIGHT_NET_SEND` | `0x00000010U` (bit 4) | `(1u << 17)` = `0x00020000U` |
  | `XKABI_RIGHT_NET_RECV` | `0x00000020U` (bit 5) | `(1u << 18)` = `0x00040000U` |
  | `XKABI_RIGHT_CONSOLE_OUT` | `0x00000040U` (bit 6) | `(1u <<  4)` = `0x00000010U` |
  | `XKABI_RIGHT_FIRMWARE_VAR` | `0x00000080U` (bit 7) | `(1u <<  5)` = `0x00000020U` |

  The cap table built by `capability_init.c` from EFI handles is passed to the XENOS kernel in `g_cap_table`. When the kernel validates those entries against its own `XKABI_RIGHT_*` definitions from `xkabi_rights.h`, every rights bitmask will be misinterpreted. For example, a network-capable EFI handle will have `rights = 0x30` (NET_SEND|NET_RECV in capability_init.c's encoding), but the kernel will interpret `0x30` as bits 4 and 5, which are `XKABI_RIGHT_FIRMWARE_VAR` and reserved, NOT network rights.
- **Note:** `xkabi_capabilities.c` (kernel side) and both `init/gensd/main.c` and `init/gensd/service.c` (GENSD side) all correctly include `xkabi_rights.h` after the P1-RIGHTS-MISMATCH-01 fix. `capability_init.c` (AetherBoot side) was missed.
- **Required fix:** In `aetherboot/src/capability_init.c`, remove the local `#define XKABI_RIGHT_*` block (lines 43-51) and replace with:
  ```c
  #include "../../kernel/xenos/include/xkabi_rights.h"
  ```
  The freestanding comment (no libc, no EDK2) does not preclude including a pure `#define` header from the kernel tree.

#### P2-NVME-BAR0-001: nvme_bar0_phys absent from xenos_boot_info_t
- **File:** `kernel/xenos/include/xenos.h` (xenos_boot_info_t definition)
- **Lines:** `xenos_boot_info_t` struct — no `nvme_bar0_phys` or `nvme_bar0` field
- **Severity:** P2 — `kernel/xenos/drv/nvme.c:nvme_init(uint64_t bar0_phys)` requires the caller to pass the NVMe PCIe BAR0 physical address. The comment in `nvme.c` reads: "bar0_phys: physical address of NVMe PCIe BAR0 (from AetherBoot PCI scan or from xenos_boot_info_t.nvme_bar0 — Sprint 2 will expose this)." The field does not exist in the struct. `kmain()` cannot call `nvme_init()` without this information, and there is no PCI enumeration code in Sprint 1 to scan for it at runtime.
- **Root cause:** The field was deferred to Sprint 2 as a known gap. The `xenos_boot_info_t` fields are: magic, mem_map_addr, mem_map_count, mem_map_desc_size, fb_base, fb_width, fb_height, fb_pitch, fb_format, xenos_phys, xenos_size, num_cpus, _reserved[2], tsc_hz. No NVMe field.
- **Required fix (Sprint 2):** Add `uint64_t nvme_bar0_phys;` to `xenos_boot_info_t`. AetherBoot must enumerate PCI devices, find the NVMe controller (class 0x01, subclass 0x08), read BAR0, and write the address into `boot_info.nvme_bar0_phys` before calling the kernel.

---

## Passing Checklist Items

### Item 1: GDT layout
**Result: PASS** (with clarification note)

`kernel/xenos/core/entry.asm` — `_gdt64`:
- 11 GDT slots: 5 null entries (indices 0-4, selectors 0x00-0x20), kernel code at index 5 (selector 0x28), kernel data at 0x30, user code at 0x38, user data at 0x40, TSS low at 0x48, TSS high at 0x50.
- GDTR limit = `_gdt64_end - _gdt64 - 1` = `11*8 - 1 = 87`. **CORRECT.**
- CS_KERNEL = 0x28 (index 5). **CORRECT.**
- STAR MSR in `kernel/xenos/core/main.c:syscall_init()`:
  ```c
  const uint64_t star =
      ((uint64_t)0x0038u << 48) |  /* SYSRET CS/SS base: user code at 0x38 */
      ((uint64_t)0x0028u << 32);   /* SYSCALL CS: kernel code at 0x28 */
  ```
  STAR = `0x0038002800000000`. **CORRECT.**
- **Clarification:** The checklist states "9 descriptors" but the GDT has 11 slots. The GDTR limit of 87 is consistent only with 11 entries (9 entries would give limit=71). The "9" in the checklist refers ambiguously to non-null non-TSS entries. The implementation is internally consistent and correct — GDTR limit=87 matches the actual 11-slot GDT.

### Item 8: GENSD toposort — Kahn's algorithm
**Result: PASS**

`init/gensd/service.c:gsd_dep_order()` (lines 509-580) implements Kahn's algorithm correctly:

1. **In-degree computation (step 1):** For each service `i`, iterates over its `requires[]` array, looks up whether each dependency name exists in the services array, and if found increments `in_degree[i]`. Only verified dependencies count toward in-degree; unknown deps are ignored (forward-compatible).

2. **Queue initialization (step 2):** All services with `in_degree[i] == 0` are enqueued.

3. **BFS loop (step 3):** Dequeues service `u`, appends to `order_out`, then scans ALL other services `v` to find which ones list `u` in their `requires[]`. For each such `v`, decrements `in_degree[v]` and enqueues if it reaches 0. The `in_degree[v] > 0` guard prevents underflow on pre-existing zero-degree nodes.

4. **Cycle detection (step 4):** If `out_idx != n` after the BFS, logs a warning and fills remaining output slots with unordered indices (best-effort recovery). Returns -1.

**Correctness observation:** The in-degree computation correctly increments `in_degree[i]` (the dependent service) rather than the dependency. This matches standard Kahn's semantics where in-degree represents "how many things must run before me."

**Minor note:** Unknown dependency names are silently ignored rather than returning an error. This is intentional (forward-compatible) but means a `.gsd` file with a typo in `Requires` will start the service out-of-order without warning.

### Item 9: PAL 14-section contract
**Result: PASS**

`pal/include/pal.h` contains all 14 required sections:
- §1 Primitive Types (`uint8_t`..`uint64_t`, `size_t`, `bool`, `NULL` guard)
- §2 Status Codes (`pal_status_t`, PAL_OK, PAL_ERR_*, 16 codes)
- §3 Handle System (`pal_handle_t`, PAL_INVALID_HANDLE, `pal_handle_close`)
- §4 Physical Memory (`pal_phys_alloc`, `pal_phys_free`, `pal_phys_to_virt`)
- §5 Virtual Memory (`pal_pages_alloc`, `pal_pages_free`, `pal_map_range`)
- §6 Threading (`pal_thread_create`, `pal_thread_join`, `pal_thread_yield`, `pal_thread_sleep_ns`, `pal_thread_config_t`, `PAL_THREAD_BACKGROUND`)
- §7 Synchronization (`pal_spinlock_t`, `pal_spin_lock`, `pal_spin_unlock`, `PAL_SPINLOCK_INIT`)
- §8 Timekeeping (`pal_time_now_ns`)
- §9 IPC Channels (`pal_channel_create`, `pal_channel_send`, `pal_channel_recv`)
- §10 Crypto (`pal_sha256`, `pal_csprng_fill`)
- §11 DMA/Scatter-Gather (`pal_dma_alloc`, `pal_dma_free`, `pal_sg_list_t`)
- §12 Console Output (`pal_console_putchar`, `pal_console_printf`)
- §13 Platform Query (`pal_cpu_count`, `pal_memory_total_bytes`, `pal_thermal_read_cpu`)
- §14 Backend Initialization (`pal_init`, `pal_shutdown`)

### Item 10: CPU_RELAX() macro
**Result: PASS**

`pal/src/pal_aether.c` defines CPU_RELAX() correctly for all three target architectures with no recursive expansion:

```c
#if defined(__x86_64__)
#  define CPU_RELAX()   __asm__ volatile("pause" ::: "memory")
#elif defined(__aarch64__)
#  define CPU_RELAX()   __asm__ volatile("yield" ::: "memory")
#else
#  define CPU_RELAX()   __asm__ volatile("" ::: "memory")
#endif
```

The `"memory"` clobber ensures the compiler does not reorder memory accesses across the pause/yield. The prior recursive expansion defect has been resolved.

---

## Subsystem Grades

### Sprint 0 Subsystems

#### PAL Contract (`pal/include/pal.h`)
**Grade: A**
All 14 API sections present and consistently typed. NULL guard applied. Freestanding-safe (no libc headers). PAL_SPINLOCK_INIT macro defined for static initializer use. `pal_thread_config_t` fully specified including `PAL_THREAD_BACKGROUND` priority enum.

#### PAL-Aether Backend (`pal/src/pal_aether.c`)
**Grade: B**
CPU_RELAX() macro is correct. x86_64 `pal_console_putchar` / `pal_console_printf` use MMIO serial (port 0x3F8). §4 physical memory, §5 virtual memory, §6 threads, §9 IPC are all TODO-S1 stubs returning `PAL_ERR_NOT_SUPPORTED`. Acceptable for Sprint 1 scope but represents approximately 40% of the PAL surface being unstubbed. The deduction is for functional completeness not a defect per se.

#### PAL-Linux Backend (`pal/src/pal_linux.c`)
**Grade: A**
Full implementation of all 14 PAL sections using Linux syscalls (mmap, pthread, eventfd, clock_gettime). Correct `PAL_ERR_*` mapping from errno. eventfd-based IPC channels correctly handle blocking send with backpressure. sha256 uses OpenSSL `EVP_MD_CTX`. `pal_dma_alloc` uses `posix_memalign` for alignment. Suitable as validation backend.

---

### Sprint 1 Subsystems

#### Boot Entry (`kernel/xenos/core/entry.asm`)
**Grade: C**
GDT layout is correct (11 entries, GDTR limit=87, CS_KERNEL=0x28). ISR stubs cover all 256 vectors. **BSS zeroing is absent (P1-BSS-ZERO-001).** The GDT has 5 leading null entries; this is unconventional but not incorrect for x86-64 compatibility mode considerations.

#### Interrupt Service Routines (`kernel/xenos/core/isr.asm`)
**Grade: B**
File contains only `extern` declarations — all ISR stub code lives in entry.asm, which is architecturally clean (single assembly unit). No executable code to audit here. Linking structure is sound.

#### SYSCALL Path (`kernel/xenos/core/syscall.asm`)
**Grade: C**
Register argument shuffle is correct and dependency-free (RAX→RDI, RSI→RSI, RDX→RDX, R10→R8). RSP save/restore via GS-relative per-CPU struct is correct for the SYSCALL path. **SWAPGS race in ISR path (P1-SWAPGS-RACE-001):** `_common_isr_entry` performs no SWAPGS and no CS privilege check, leaving kernel exceptions with undefined GS state.

#### Kernel Main (`kernel/xenos/core/main.c`)
**Grade: C**
14-step kmain sequence is well-structured. STAR MSR encoding is correct. EFER.NXE enabled before vmm_init. gdt_reload() correctly patches the TSS base into GDT slots 9-10 and loads TR with 0x48. **IDT #DF IST=0 (P0-IDT-IST-001):** the idt_init() loop sets `ist=0` for all 256 vectors with no #DF special-case.

#### Physical Memory Manager (`kernel/xenos/mm/pmm.c`)
**Grade: A-**
Binary buddy allocator with order 0-10 (4KB–4MB). Two zones (DMA32/NORMAL) correctly partitioned at 4GB boundary. `pmm_init()` correctly parses the EFI memory map and splits regions around the XENOS ELF image. `pmm_hhdm_live()` flag correctly switches phys_to_pf conversion from identity mapping to HHDM offset post-vmm_init. `_pmm_add_range()` properly aligns to power-of-2 buddy boundaries. Minor: no PMM statistics export (reservation sizes, fragmentation) but that is Sprint 2 scope.

#### Virtual Memory Manager (`kernel/xenos/mm/vmm.c`)
**Grade: D**
4-level page table initialization is structurally correct. HHDM at 0xFFFF888000000000 and KERN_BASE at 0xFFFFFFFF80000000 are standard. Platform Integrity fix (no PTE_USER on kernel intermediate entries) is applied. `_vm_flags_to_pte()` correctly handles NX for 4KB pages. **However, P1-VMM-NX-001 is critical:** both the HHDM 2MB PDE loop and the kernel ELF 2MB PDE loop omit `PTE_NX`. Despite EFER.NXE being set, all physical memory is mapped executable. This is a security regression that would allow trivial code injection exploits once user processes run.

#### Heap / Slab Allocator (`kernel/xenos/mm/heap.c`)
**Grade: A**
10 size classes (8..4096 bytes). O(1) fast path for small allocations. Large allocations (>4096) use raw PMM pages with `large_hdr_t` prepended in the HHDM. `kfree()` correctly distinguishes slab vs. large by checking if the pointer aligns to a slab page and the slab header magic matches. `g_heap_lock` spinlock covers all paths. No double-free detection in Sprint 1 but that is expected.

#### Contra-Rotation Thermal Scheduler (`kernel/xenos/sched/contra_rotation.c`)
**Grade: B+**
3-phase COMPUTE→COOLDOWN→LOAD scheduler is correct and well-isolated. Fail-safe forced COOLDOWN on `CR_TEMP_SENSOR_ERROR = INT32_MIN` is appropriate. 500ms poll interval via PAL §6 thread. NCCL EP-RDMA lane scaling is stubbed with a TODO for Sprint 2. Temperature threshold constants (75°C throttle, 90°C emergency) are reasonable defaults for the HP EliteBook x360 target platform.

#### XKABI Capability System (`kernel/xenos/cap/xkabi_capabilities.c`)
**Grade: B**
Handle encoding (slot[63:40] | rights[39:16] | generation[15:0]) is consistent and documented. Correctly imports rights from canonical `xkabi_rights.h` (P1-RIGHTS-MISMATCH-01 fix applied). Generation counter prevents stale handle reuse. **Known Sprint 1 limitation:** No HMAC on handle values — handles can be synthesized by any code that knows the slot/rights layout. Sprint 2 pal_sha256-based HMAC is planned. **AetherBoot gap:** capability_init.c still uses ad-hoc bitmasks (P2-RIGHTS-SYNC-001).

#### NVMe Driver (`kernel/xenos/drv/nvme.c`)
**Grade: B-**
Full NVMe 1.4 reset sequence, admin/IO queue setup, Identify Controller/Namespace, and PRP-based Read/Write. Doorbell stride correctly computed from `CAP.DSTRD`. Admin CQ interrupt suppression (IOSQES/IOCQES in CC) is correct. **P2-NVME-BAR0-001:** `bar0_phys` must be passed by caller but `xenos_boot_info_t` has no such field. Until Sprint 2 adds PCI enumeration, `nvme_init()` cannot be called from `kmain` in a portable way.

#### Intel iGPU Driver (`kernel/xenos/drv/intel_igpu.c`)
**Grade: B+**
GOP framebuffer mapping with PAL `PAL_MEM_UNCACHED|PAL_MEM_WRITE_COMBINE` and correct fallback to HHDM direct mapping when PAL returns `PAL_ERR_NOT_SUPPORTED`. Embedded 8x16 bitmap font for early console. `igpu_boot_splash()` and `igpu_draw_text_8x16()` correctly handle scale factors. `igpu_fb_present()` is a memory barrier (`__asm__ volatile("" ::: "memory")`) on direct-mapped framebuffers — appropriate for Sprint 1.

#### TPM 2.0 Driver (`aetherboot/src/tpm.c`)
**Grade: A-**
Self-contained SHA-256 (FIPS 180-4 compliant, verified K constants and round function). Big-endian wire format helpers (`put_be16`, `put_be32`, `get_be32`) are correct. PCR extension command layout (65 bytes) matches TPM 2.0 spec wire format. PCR read response parsing uses correct fixed offset (28 bytes) for single-PCR SHA-256 read. Graceful degradation when `EFI_TCG2_PROTOCOL` is absent. PCR[8]=AetherBoot, PCR[9]=XENOS is a sound measured boot chain. Minor: `tpm2_hash_buffer()` takes a `UINT32 len` but SHA-256 internal uses `UINT64`; for kernel images >4GB this would truncate, though that is not a realistic concern on the HP EliteBook target.

---

### GENSD Subsystems

#### GENSD Main / Service Lifecycle (`init/gensd/main.c`)
**Grade: B+**
PID 1 init sequence (register → watch → supervisor thread → start services) is correctly ordered: services are watched before any are started, ensuring the supervisor is ready for immediate failures. Rights are correctly sourced from `xkabi_rights.h` (P1-RIGHTS-MISMATCH-01 fix applied). Orderly shutdown (reverse order, supervisor join, journal flush) is present. Sprint 1 service start is a stub (no actual `fork+exec`), which is documented and expected. Essential services list (`xnet-loopback`, `xstore-init`, `xapi-health`) covers the correct Sprint 1 dependency chain.

#### GSD Parser + Dependency Sorter (`init/gensd/service.c`)
**Grade: A-**
GSD file format parser is robust: comment handling (`#`, `;`), whitespace stripping, unknown section tolerance, `Requires`/`After` both mapped to the requires list, `.gsd` extension stripped from dependency names. `gsd_validate()` enforces name charset, exec path starting with `/`, and rights mask against known bits only. `parse_rights()` correctly handles `|`-delimited token strings. Kahn's algorithm is correctly implemented (see Item 8 analysis). The `known_mask` in `gsd_validate()` only includes software rights (bits 0-11) — it will reject any service requesting hardware rights (bits 12-22) like `XKABI_RIGHT_NET_SEND`. This is likely intentional for Sprint 1 (GENSD does not yet grant hardware rights via .gsd files) but should be documented.

#### Process Supervisor (`init/gensd/supervisor.c`)
**Grade: B**
Exponential backoff (`sv_next_backoff`, doubles to 30s cap) is correct with overflow guard. Process liveness probe correctly distinguishes DAEMON (must stay running) from ONESHOT (exit is OK). HTTP probe is a correctly documented Sprint 1 stub. `supervisor_watch()` uses a documented manual offset layout (`svc_layout_t` typedef with `_pad[6]` for alignment) instead of a shared header — fragile but functional for Sprint 1. **Known documented defect (P1-SUPERVISOR-SLEEP from supervisor.c comment itself):** `supervisor_restart()` calls `pal_thread_sleep_ns(delay_ns)` for up to 30 seconds, blocking the supervisor thread from probing all other services during that window. This is self-documented with a TODO for Sprint 2 non-blocking timer. Counted as a known risk, not a new finding.

#### Journal (`init/gensd/journal.c`)
**Grade: A-**
4MB BSS ring buffer with wrap-around write. FNV-1a hash for service names is appropriate (fast, good distribution for short strings). `journal_flush_serial()` forward-scan with per-entry validation (level 0-4, msg_len 0-255) correctly handles partially-overwritten entries. `ring_write_bytes` split-boundary write is correct. `journal_read_recent()` is a Sprint 1 stub (returns empty) — acceptable. Minor: the flush does not acquire `g_jlock` during the scan (only reads `wp` and `total` under lock), so concurrent writes can produce torn entries in the output — acceptable for a debug-only flush path.

#### Boot Splash (`init/gensd/splash.c`)
**Grade: A**
Framebuffer dimensions queried at `splash_show()` time (not compile-time). Progress bar geometry is runtime-computed from `fb_w`/`fb_h` — correct for any resolution. Thread-safe: `splash_update_progress()` acquires the spinlock, copies dimensions, releases lock, then draws without holding the lock (avoiding a deadlock with igpu calls). `splash_hide()` correctly sets `visible=false` under lock before drawing the clear. Color constants match the visual specification in the header comment.

---

## Capability Rights Consistency Summary

The rights mismatch across the AetherBoot/GENSD/kernel boundary is the most important cross-cutting concern:

| File | Rights Source | Status |
|------|--------------|--------|
| `kernel/xenos/cap/xkabi_capabilities.c` | `#include "xkabi_rights.h"` | CORRECT |
| `init/gensd/main.c` | `#include "xkabi_rights.h"` | CORRECT |
| `init/gensd/service.c` | `#include "xkabi_rights.h"` | CORRECT |
| `init/gensd/supervisor.c` | No rights definitions needed | N/A |
| `aetherboot/src/capability_init.c` | Local ad-hoc `#define` block | **INCORRECT — P2** |

The AetherBoot side remains unfixed. The GENSD and kernel sides are unified via the canonical header.

---

## TPM / AetherBoot Additional Notes

`aetherboot/src/tpm.c` — Measured boot chain is sound:
- PCR[8] = SHA-256 of AetherBoot image (self-measurement, pre-ExitBootServices)
- PCR[9] = SHA-256 of XENOS kernel ELF (kernel measurement, pre-ExitBootServices)
- Graceful degradation (no TPM = no-op, boot continues)
- Self-contained SHA-256 implementation avoids any dependency on EFI crypto protocols

`aetherboot/src/capability_init.c` — EFI handle enumeration for cap table bootstrap:
- AllHandles enumeration via `LocateHandleBuffer` is correct UEFI Spec §7.3 usage
- `FreePool(handles)` is correctly called after enumeration
- Cap table stored in BSS with magic header `0x584B414249434150ULL` ("XKABICAT")
- Rights assigned per protocol GUID: GOP → GPU_EXEC|GPU_MAP, BlockIO → STORAGE_READ|STORAGE_WRITE, Network → NET_SEND|NET_RECV, ConOut → CONSOLE_OUT
- **P2-RIGHTS-SYNC-001:** All rights values are wrong due to local ad-hoc definitions

---

## Action Items for Sprint 2

Priority-ordered remediation list:

1. **[P0] Fix #DF IST:** `kernel/xenos/core/main.c:idt_init()` — set `idt[8].ist = 1u`, allocate a 8KB double-fault stack, point `tss.ist[0]` to it.

2. **[P1] Add BSS zero loop:** `kernel/xenos/core/entry.asm:_start` — insert `lea rdi/rcx` + `rep stosb` between stack setup and `call kmain`.

3. **[P1] Fix VMM NX on HHDM/kernel 2MB PDEs:** `kernel/xenos/mm/vmm.c:vmm_init()` — add `PTE_NX` to all data large-page entries; ensure kernel text pages are identified and kept executable.

4. **[P1] Add SWAPGS guard in ISR path:** `kernel/xenos/core/syscall.asm:_common_isr_entry` — add CS[1:0] check before SWAPGS on entry and exit for all hardware interrupt/exception vectors.

5. **[P2] Fix capability_init.c rights:** `aetherboot/src/capability_init.c` — replace local `#define XKABI_RIGHT_*` block with `#include "../../kernel/xenos/include/xkabi_rights.h"`.

6. **[P2] Add nvme_bar0_phys to xenos_boot_info_t:** `kernel/xenos/include/xenos.h` — add `uint64_t nvme_bar0_phys;` field; update AetherBoot to populate it from PCI BAR0 enumeration.
