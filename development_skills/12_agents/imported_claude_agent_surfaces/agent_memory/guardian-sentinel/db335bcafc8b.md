# AetherBoot + Kernel Handoff Security Audit — 2026-03-07

Audit Token: `a1c7e3f9d2b048569e3a17c4f85d2091b7e6a3c4d9f012385a6b7c8d9e0f1a2b`
Status: **FLAG** (Conditional GO — 1 HIGH, 4 MEDIUM, 2 LOW)

## Files Audited
- `aetherboot/src/aetherboot.c` (903 lines)
- `kernel/xenos/core/main.c` (1202 lines)
- `kernel/xenos/include/xkabi_rights.h` (91 lines)
- `init/gensd/main.c` (673 lines)
- `kernel/xenos/mm/vmm.c` (cross-reference for PTE_GLOBAL / CR4.PGE)
- `aetherboot/src/tpm.c` (cross-reference for tpm2_measure_aetherboot)
- `aetherboot/src/capability_init.c` (cross-reference for xkabi_rights.h import)

## Findings

### GS-AB-001 [HIGH] ELF p_paddr not bounds-checked — kern_span overflow
- File: `aetherboot/src/aetherboot.c:633-651`
- load_min initialized to (UINT64)-1 = 0xFFFFFFFFFFFFFFFF
- Kernel ELF linked at KERN_BASE_VIRT = 0xFFFFFFFF80000000
- If p_paddr == KERN_BASE_VIRT (which it does per comment line 647):
  load_min = 0xFFFFFFFF80000000, load_max = load_min + p_memsz
  kern_span = p_memsz (reasonable)
- BUT: if multiple PT_LOAD segments exist with wildly different p_paddr
  (e.g., one high-addr, one low-addr from malformed ELF), kern_span
  could be enormous, kern_pages could overflow UINTN on 32-bit UEFI
- Mitigation present: AllocatePages will fail for absurd sizes
- Risk: On 64-bit UEFI, no overflow but could request terabytes
- Fix: Add `if (kern_span > 64ULL * 1024 * 1024) { /* reject */ }` upper bound

### GS-AB-002 [MEDIUM] PTE_G (Global bit) set before CR4.PGE enabled
- File: `aetherboot/src/aetherboot.c:510,514`
- Identity map + HHDM 1GB pages carry PTE_G flag
- CR4.PGE is NOT set anywhere in aetherboot.c
- Kernel vmm.c line 542 says "global entries flushed if CR4.PGE toggled — deferred to Sprint 2"
- Impact: Without CR4.PGE=1, the PTE_G bit is ignored by hardware (Intel SDM Vol3 4.10.2.4)
- The bit is harmless when PGE is disabled — it becomes meaningful only when PGE is later enabled
- Risk: When kernel eventually enables CR4.PGE, stale identity-map TLB entries from AetherBoot
  could survive CR3 reload (global pages are not flushed on CR3 write)
- Current: vmm_init() builds new page tables and loads new CR3 — identity map NOT in new tables
- Status: LOW RISK currently because vmm_init() replaces the page tables entirely
- Sprint 2 TODO: ensure CR4.PGE toggle (off then on) when vmm_switch_to() is called

### GS-AB-003 [MEDIUM] No NX bit on kernel data pages in AetherBoot page tables
- File: `aetherboot/src/aetherboot.c:524`
- Kernel 2MB pages: `PTE_P | PTE_RW | PTE_PS` — no NX bit
- EFER.NXE is NOT set by AetherBoot (it IS set by kmain step 4.5)
- This means kernel .data/.bss is executable under AetherBoot's page tables
- Window: from do_kernel_jump (line 704) until vmm_init() at kmain step 5
- During this window: steps 1-4 (serial, IDT, GDT, PMM) execute with no NX
- vmm.c line 288: `PTE_PRESENT | PTE_WRITE | PTE_PS | PTE_GLOBAL` — also no NX on data
- vmm.c line 327-329: comment says "Mark NX for data" but code does NOT set PTE_NX
- Impact: kernel data pages executable — code injection into .bss could execute
- Fix: vmm.c should set PTE_NX on non-text kernel pages (Sprint 2 ELF section remapping)

### GS-AB-004 [MEDIUM] AllocateAddress at 0x200000 — no fallback alignment guarantee
- File: `aetherboot/src/aetherboot.c:653-663`
- Preferred: AllocateAddress at 0x200000 (2MB aligned, good for huge pages)
- Fallback: AllocateAnyPages — no alignment guarantee
- If fallback fires, kern_phys may not be 2MB-aligned
- build_page_tables maps with PTE_PS (2MB pages) starting at kern_phys
- Misaligned kern_phys with PTE_PS = #GP or undefined behavior
- Fix: fallback should use AllocatePages with alignment constraint or
  round down and allocate extra pages

### GS-AB-005 [MEDIUM] ELF phdr iteration assumes sizeof(Elf64_Phdr) == e_phentsize
- File: `aetherboot/src/aetherboot.c:634-636`
- `ph[i]` uses C array indexing = `ph + i * sizeof(Elf64_Phdr)`
- ELF spec: program header entry size is `e_phentsize`, NOT necessarily sizeof
- For standard ELF64 this is always 56 bytes = sizeof(Elf64_Phdr), so practically safe
- But a malformed/future-extended ELF could have e_phentsize != 56
- Fix: validate `eh->e_phentsize == sizeof(Elf64_Phdr)` or use byte arithmetic

### GS-AB-006 [LOW] TPM measurement with NULL/0 — carry-forward from GS-S01-003
- File: `aetherboot/src/aetherboot.c:826`
- `tpm2_measure_aetherboot(NULL, 0)` — hashes empty string
- Comment says "derives load address internally" but tpm.c:395-399 shows
  it directly calls tpm2_hash_buffer(image_base=NULL, image_size=0, digest)
- This measures SHA-256("") = e3b0c442... into PCR, not the actual bootloader
- Status: CARRY-FORWARD (GS-S01-003 from Sprint 0/1 audit, still open)

### GS-AB-007 [LOW] g_xenos_handoff in EfiLoaderData — boot info lifetime safe
- File: `aetherboot/src/aetherboot.c:418,878-893` + `kernel/xenos/core/main.c:995-1020`
- g_xenos_handoff is static BSS in AetherBoot = EfiLoaderData type
- Kernel reclaims EfiLoaderData via PMM after ExitBootServices
- Question: does kmain read bi-> fields before pmm_init() could reclaim them?
- Answer: YES — kmain step 1 (line 1003) reads bi->magic BEFORE pmm_init (step 4, line 1020)
- Step 3 (gdt_reload) does NOT read bi
- Step 4 (pmm_init) receives bi and should consume all fields before marking pages free
- Analysis: SAFE — pmm_init reads the memory map FROM bi, so it must preserve bi until done
  The memory map itself (g_mmap_buf) is in AetherBoot's EfiLoaderData BSS, separate from
  g_xenos_handoff. pmm_init processes the map entries and builds the buddy allocator.
  As long as pmm_init does not immediately free pages containing g_xenos_handoff, this works.
- Risk: LOW — depends on pmm_init implementation not immediately freeing the boot region
- Post-pmm_init reads: step 7 (pal_init) and step 10a read bi->acpi_rsdp_phys, bi->tsc_hz etc.
  If pmm has already reclaimed the EfiLoaderData page, these reads are UAF.
- Mitigation: g_boot_info_ptr = bi at line 1177 (step 10e), gensd_start(bi) at step 13
- Status: NEEDS VERIFICATION of pmm_init — does it mark EfiLoaderData as reclaimable immediately?
  If yes: P1 UAF. If no (deferred reclaim): safe.

### GS-AB-CLEAR-01: XKABI Rights Conformance — VERIFIED CLEAN
- `init/gensd/main.c:108` includes `xkabi_rights.h` (canonical single source)
- All 7 essential_services use correct canonical macros:
  - xnet-loopback: NET_SEND|NET_RECV (bits 17,18) -- correct
  - xstore-init: STORAGE_READ|STORAGE_WRITE (bits 15,16) -- correct
  - xapi-health: NET_SEND|NET_RECV (bits 17,18) -- correct
  - xorchestra: EXEC|IPC_SEND|IPC_RECV (bits 0,2,6) -- correct
  - xshell: DISPLAY|IPC_SEND|IPC_RECV|INPUT (bits 7,2,6,8) -- correct
  - xmind-server: NET_SEND|NET_RECV|STORAGE_READ (bits 17,18,15) -- correct
  - xbuild-daemon: EXEC|STORAGE_READ|STORAGE_WRITE (bits 0,15,16) -- correct
- `aetherboot/src/capability_init.c:46` includes `xkabi_rights.h` -- correct
- P1-RIGHTS-MISMATCH-01: FULLY RESOLVED across all files

### GS-AB-CLEAR-02: Handoff Struct ABI Alignment — VERIFIED CLEAN
- AetherBoot xenos_handoff_t (aetherboot.c:400-416) has identical layout to
  kernel xenos_boot_info_t (xenos.h:85-108)
- Both have: magic, mem_map_addr, mem_map_count, mem_map_desc_size,
  fb_base, fb_width, fb_height, fb_pitch, fb_format, xenos_phys, xenos_size,
  num_cpus, _reserved, tsc_hz, acpi_rsdp_phys
- Field order, types, and sizes all match
- Sprint 13 acpi_rsdp_phys field present in both definitions

### GS-AB-CLEAR-03: EFER.NXE Timing — VERIFIED ACCEPTABLE
- AetherBoot does NOT set EFER.NXE (no NX protection in boot page tables)
- kmain step 4.5 (main.c:1028-1033) sets EFER.NXE before vmm_init (step 5)
- vmm_init builds new page tables that CAN use NX bit
- Window: boot page tables active without NX from do_kernel_jump to step 4.5
  (~4 steps: serial, IDT, GDT, PMM). Acceptable for boot-only code path.
