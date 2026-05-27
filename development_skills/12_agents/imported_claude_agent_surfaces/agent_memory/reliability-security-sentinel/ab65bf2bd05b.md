# Sprint 0 + Sprint 1 Native Kernel Build Track — Security & Reliability Audit
**Date:** 2026-03-03
**Files read:** 25 (all in scope)
**Verdict:** Sprint 0 PASS, Sprint 1 CONDITIONAL

## Sprint Gate Verdicts

### Sprint 0 — PASS
All 5 components compile, test, and pass cppcheck. No P0/P1 blocking findings.

### Sprint 1 — CONDITIONAL
22/22 compile checks pass. 5 P1 findings block Sprint 2 start.

## Security Findings Summary

### P1 (blocking Sprint 2)

**P1-SEC-01: SWAPGS MISSING IN ISR PATH**
- File: kernel/xenos/core/entry.asm _common_isr_entry
- SYSCALL path (syscall.asm:114) issues swapgs correctly — only reachable from ring 3 via SYSCALL, so CPL=0 on entry, always correct.
- ISR path (_common_isr_entry) does NOT issue swapgs. Hardware interrupts from ring 3 will NOT swap GS → GS-relative percpu access in xenos_isr_dispatch uses wrong GS base.
- No userspace in Sprint 1, so not triggered yet. BECOMES P0 when Sprint 2 introduces userspace.
- Fix: Check CS[1:0] from saved interrupt frame. If CS&3==3 (came from ring 3), issue swapgs at ISR entry and again before iretq.

**P1-SEC-02: PCR[8] MEASURES SHA-256("") NOT AETHERBOOT IMAGE**
- File: aetherboot/src/aetherboot.c line 427
- tpm2_measure_aetherboot(NULL, 0) — NULL image_base, 0 size → SHA-256 of empty string = e3b0c4...
- PCR[8] always same value regardless of bootloader integrity. TPM attestation for bootloader is broken.
- Comment says "PCR[7]" but TPM2_PCR_AETHERBOOT=8 — comment inconsistency also.
- Fix: Pass loaded_image->ImageBase and loaded_image->ImageSize via EFI_LOADED_IMAGE_PROTOCOL.

**P1-SEC-03: CAP TABLE PHYSICAL ADDRESS NEVER PASSED TO KERNEL**
- File: aetherboot/src/capability_init.c + aetherboot/src/aetherboot.c
- cap_init_from_efi() populates g_cap_table in UEFI memory. cap_get_table_phys() returns its address.
- But xenos_boot_info_t / pal_aether_boot_info_t has NO field for cap_table_phys.
- Kernel cap_table_init() zeroes its own table independently. UEFI capability enumeration result silently discarded.
- Fix: Add cap_table_phys field to xenos_boot_info_t. Store cap_get_table_phys() before ExitBootServices(). Kernel copies from that physical address.

**P1-SEC-04 / P1-REL-01: SUPERVISOR BLOCKING SLEEP (30s) HALTS ALL SUPERVISION**
- File: init/gensd/supervisor.c line 214 — pal_thread_sleep_ns(delay_ns) inside supervisor_restart()
- Single supervisor thread sleeps up to 30s during backoff. ALL service liveness probing suspended.
- Cascade failure: service A crashes → 30s sleep → services B and C undetected during sleep.
- Source itself documents this as TODO(Sprint 2) at lines 207-212.
- Fix: Per-service timer. Supervisor loop never sleeps; checks next_restart_at_ns timestamps.

**P1-SEC-05: aetherboot/capability_init.c USES LOCAL #define RIGHTS vs xkabi_rights.h**
- File: aetherboot/src/capability_init.c lines 43-51
- Local #define CAP_RIGHT_GPU_EXEC 0x0001 etc. instead of including xkabi_rights.h.
- gensd/main.c and gensd/service.c ALREADY FIXED (include xkabi_rights.h) — confirmed.
- Only aetherboot/capability_init.c remains unfixed. Drift risk if canonical bits change.
- Fix: Replace local defines with #include "../../kernel/xenos/include/xkabi_rights.h"

### P2 Findings

- P2-SEC-01: HHDM pages have no PTE_NX bit — W^X violated for all 128GB. Sprint 2 gate.
- P2-SEC-02: Double fault (#DF vector 8) uses no IST stack — triple-fault on stack overflow. Sprint 2 gate.
- P2-SEC-03: xas.c NULL ptr deref — bare `jmp` with no operand → strncpy(f->name, NULL, 63) → SIGSEGV.
- P2-SEC-04: tpm2_get_pcr reads digest at fixed offset 28 without validating response structure.
- P2-SEC-05: kfree() magic check false positive — LARGE_ALLOC_MAGIC in slab data → wrong pmm_free_pages call.
- P2-SEC-06: service.c parse_rights() silently drops unknown capability tokens — no WARNING logged.
- P2-REL-01: GENSD idle loop has no shutdown mechanism in Sprint 1 (no signal handling).
- P2-REL-02: vdram_alloc brief active=1 window before page alloc — stats overcount race.
- P2-REL-03: ring_write_bytes len==space_to_end edge case — CONFIRMED CORRECT. Not a bug.
- P2-REL-04: contra_rotation thermal MSR inside spinlock — latency issue on PAL-Linux only.
- P2-REL-05: gsd_dep_order unknown dep names silently ignored → silent ordering violations in Sprint 3.

### Advisory Findings (Confirmed)

- ADV-01: supervisor journal_write called AFTER spinlock release — CORRECT. No issue.
- ADV-02: gensd shutting_down flag logic — CORRECT. Infinite loop is intended in Sprint 1.
- ADV-03: stage1.asm ABI translation — correct for UEFI entry (no caller to preserve regs for).
- ADV-04: journal_flush_serial reads ring without lock — documented best-effort. Sprint 3 fix.
- ADV-05: FROZEN access returns PAL_OK but data is zeroed — footgun, consider PAL_ERR_EVICTED.
- ADV-06: ait_compress main() uses printf not pal_console_printf — portability issue for PAL-Aether.
- ADV-07: fread return unchecked in ait_compress — silent corrupt compression on short read.

## Confirmed PASS Items (from this audit)

- CPU_RELAX() macro in pal_aether.c — NOT recursive. #if x86_64 uses pause instruction. FIXED.
- sv_next_backoff() overflow guard — `next < current_ms` check prevents uint32_t overflow. PASS.
- ring_write_bytes split-write at wrap boundary — CORRECT (both paths verified). PASS.
- journal_write spinlock discipline — lock before ring write, unlock after. PASS.
- supervisor_watch duplicate check — correct string comparison before insert. PASS.
- gsd_validate rights mask check — `svc->rights & ~known_mask` returns -1 on unknown bits. PASS.
- Kahn cycle detection fallback — fills remaining slots with unsorted indices, returns -1. PASS.
- entry.asm _xenos_start — correct GDT load, CS reload via retfq, segment reload sequence. PASS.
- syscall.asm argument shuffle — dependency-safe chain (no WAR hazards). PASS.
- syscall.asm stack alignment — 2 pushes (rcx, r11) + call push = correct 8-byte misalign at callee. PASS.
- stage1.asm Windows→SysV ABI translation — rcx→rdi, rdx→rsi, stack aligned to 16. PASS.
- isr.asm — placeholder only, no code emitted. All symbols in entry.asm. PASS.
- gensd main.c #include xkabi_rights.h — FIXED. Using canonical rights header. PASS.
- gensd service.c #include xkabi_rights.h — FIXED. Using canonical rights header. PASS.
- splash.c spinlock discipline — lock covers visible flag check, release before draw calls. PASS.
- progress bar coordinate math — no integer overflow (bar_w capped before multiply). PASS.
- foundation.yml actions SHA-pinned. PASS.
- xenos.yml actions SHA-pinned. PASS.
- ci.yml — uses mutable @v4 tag refs (not SHA-pinned). Open: W1C-08 still applies to ci.yml.
- Makefile.foundation: -fstack-protector-strong -D_FORTIFY_SOURCE=2 -fpie on Linux-hosted targets. PASS.
- stage1.asm assembled with -f elf64 in xenos.yml (not -f win64) — CI compile-check only, not final PE32+ link. Acceptable in Sprint 1.

## CI Gaps

- No ASan/UBSan build variant in any CI workflow for Linux-hosted tests
- No secret scanning (truffleHog/git-secrets) in kernel track workflows
- No GPG signing of artifact SHA256SUMS (N-10 from prior audit, still open)
- Trivy installed via curl | sh with mutable main URL — W1C-02 still open
- ci.yml uses ubuntu-latest not a pinned version
- xenos.yml stage1.asm assembled as elf64 not win64 — harmless in compile-check scope

## Test Coverage Gaps

- XAS: no malformed-input fuzz (bare jmp, oversized line, overlapping labels)
- libvdram: no concurrent alloc/free stress, no OOM exhaustion (1024 slots full), no 4GB+ region test
- XENOS kernel: COMPILE CHECK ONLY — no runtime tests for PMM, VMM, heap, scheduler, XKABI
- GENSD: COMPILE CHECK ONLY — no restart backoff timing test, no dependency cycle detection test
- Mandatory test types missing across both sprints: Integration, Regression, Load, Stress, Security/Fuzz, Reliability
