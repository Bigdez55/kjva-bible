# Sprint 1 Causal Graph Analysis (2026-03-03)

## Defect Registry (7 defects, priority-sorted)

### P0 CRITICAL
- **D-S1-05:** capability_init.c uses local XKABI_RIGHT_* values (0x01-0x80) that differ from
  xkabi_rights.h canonical values (1u<<1 to 1u<<23). Every boot-created capability has wrong bits.
  100% functional break. R2=1.00. Fix: #include xkabi_rights.h, remove local defines.

### P1 HIGH
- **D-S1-04:** vmm.c HHDM large pages (line 288) and kernel mapping (line 329) lack PTE_NX.
  All HHDM pages are RWX. R2=0.98. Fix: add |PTE_NX to both pd[m] assignments.
- **D-S1-02:** IST stacks not configured. idt_init sets ist=0 for all 256 vectors.
  _tss0.ist[] never populated. NMI/DF/MC handlers have no dedicated stack. R2=0.82.
- **D-S1-03:** SWAPGS NMI race in syscall.asm SYSRET path (lines 189-205).
  NMI between swapgs and sysretq runs handler at CPL0 with user GS and user RSP. R2=0.91.

### P2 MEDIUM
- **D-S1-01:** BSS not zeroed in entry.asm. REVISED: R2=0.35 (SPECULATIVE NOISE).
  Code has defense-in-depth: most critical variables have explicit initializers (.data) or
  are explicitly zeroed before first use. Residual risk only for edge cases.
- **D-S1-08:** Identity map PML4[0..3] copied from AetherBoot, never cleaned up.
  Future risk when user-space runs in Sprint 2. R2=0.55.
- **D-S1-06:** Same as D-S1-04 but for kernel ELF mapping at line 329 vmm.c.

## Causal Dependency Ordering
D-S1-02 (IST) partially mitigates D-S1-03 (SWAPGS) -- must be fixed together.
D-S1-04 (NX) independent of others.
D-S1-05 (rights) independent but highest functional impact.
D-S1-01 (BSS) independent defense-in-depth.

## Counterfactual: P(QEMU boot | fix BSS + NX)
Result: P(idle_loop) ~ 0.79 [R2=0.55, SPECULATIVE NOISE].
Dominant external dependency: AetherBoot boot_info fidelity + PAL-Aether completeness.
BSS fix is near-zero impact (code already resilient). NX fix is security-only.

## Key Patterns
- "Static initializer defense": most kernel globals use `= PAL_SPINLOCK_INIT` or `= false`,
  placing them in .data instead of .bss. This is good defensive practice.
- "Boot cap table orphan": capability_init.c is the only file that did NOT get the
  xkabi_rights.h migration (GS-P1-RIGHTS-MISMATCH-01 fix missed it).
- "IST gap pattern": IST is defined in the TSS struct but never used. Classic OS dev oversight
  where the data structure is prepared but the init code forgets to populate it.
