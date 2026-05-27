# Sprint 9 Hardware Driver Audit — Final Integration

Date: 2026-03-06
Auditor: Hardware Integration Engineer (Apex)
Target: HP EliteBook x360 1030 G4

## Files Audited (3,712 LOC total)
- kernel/xenos/drv/hpet.c (279 LOC) + include/xhpet.h (215 LOC) = 494 LOC
- kernel/xenos/drv/lapic.c (337 LOC) + include/xlapic.h (260 LOC) = 597 LOC
- kernel/xenos/drv/pci.c (264 LOC) + include/xpci.h (259 LOC) = 523 LOC
- kernel/xenos/drv/xacpi.c (805 LOC) + include/xacpi.h (295 LOC) = 1,100 LOC
- tools/iso/gen_iso.c (354 LOC) + include/gen_iso.h (240 LOC) = 594 LOC
- kernel/xenos/drv/elitebook_x360.c (404 LOC)

## HHDM_BASE Consistency: PASS
- xenos.h: 0xFFFF888000000000ULL (canonical definition)
- xhpet.h: 0xFFFF888000000000ULL (XHPET_HHDM_BASE)
- xlapic.h: 0xFFFF888000000000ULL (XLAPIC_HHDM_BASE)
- xacpi.h: 0xFFFF888000000000ULL (XACPI_HHDM_BASE)
- main.c: uses HHDM_BASE from xenos.h via APIC_HHDM_VIRT macro
- All 4 definitions are IDENTICAL = 0xFFFF888000000000

## XLAPIC Vector Assignments: PASS
- TIMER=0x30, RESCHEDULE=0x31, PANIC=0x32, SPURIOUS=0xFF (xlapic.h:155-158)
- main.c APIC_VEC_TIMER=0x30 matches (main.c:381)
- main.c APIC_SPURIOUS_VEC=0xFF matches (main.c:383)

## XPCI Device IDs: PASS
- iGPU UHD620: 0x3EA0 (xpci.h:132) -- CORRECT for Whiskey Lake i5-8265U/i7-8565U
- xHCI: 0x9D2F (xpci.h:138) -- CORRECT for Cannon Point-LP USB 3.1
- WiFi AX201: 0x02F0 (xpci.h:144) -- NOTE: AX201 is Ice Lake, EliteBook x360 G4 has AC 9560
- NVMe: 0xF1A8 (xpci.h:135) -- labeled I225-LM (wrong, I225 is Ethernet); this is generic NVMe
- LPC: 0x9D84 (xpci.h:141) -- CORRECT for Cannon Point-LP LPC
- HDA: 0x9DC8 (xpci.h:147) -- CORRECT for Cannon Point-LP audio

## P0 Findings (Critical -- Boot Blocking)

### HW-S9-P0-01: LAPIC Timer Calibration Uses Busy-Loop, Not HPET
- File: lapic.c:209-210
- The calibration delay is `volatile uint32_t delay = 1000000u; while (delay > 0u) { delay--; }`
- Comment at line 205: "In a full kernel, replace with xhpet_udelay(ctx, 10_000_000)"
- This loop is NOT calibrated to 10ms -- iteration count depends on CPU frequency, compiler
  optimization level, and memory latency
- On Whiskey Lake at 3.9GHz boost, 1M iterations takes ~250us, NOT 10ms (~40x too fast)
- Result: bus_hz will be computed as ~40x too LOW, timer interrupts will fire ~40x too slowly
- Impact: LAPIC timer ticks at ~25 Hz instead of 1000 Hz, scheduler and timers broken
- Fix: Wire xhpet_udelay() as the calibration reference before calling xlapic_timer_init()

### HW-S9-P0-02: Sprint 9 Drivers NOT Wired Into kmain() Boot Sequence
- File: main.c (14-step boot sequence)
- Grep for xhpet_init, xlapic_init, xpci_init, xacpi_init, hp_elitebook in main.c: NO MATCHES
- The 14-step init (main.c:736-830) does NOT call any Sprint 9 driver init functions
- apic_init() in main.c is the Sprint 1 LAPIC stub -- it does NOT call xlapic_init()
- The Sprint 9 XHPET/XLAPIC/XPCI/XACPI drivers exist but are dead code from kmain's perspective
- Impact: None of the Sprint 9 hardware drivers will execute on boot
- Fix: Add init steps after step 10 (APIC) to call xacpi_init, xpci_init, xhpet_init,
  then recalibrate LAPIC timer with xhpet_udelay, then call hp_elitebook_x360_init

## P1 Findings (High -- Functional Correctness)

### HW-S9-P1-01: WiFi Device ID Mismatch -- AX201 vs AC 9560
- File: xpci.h:143-144
- EliteBook x360 1030 G4 (Whiskey Lake) ships with Intel Wireless-AC 9560 (iwlwifi)
- PCI device ID for AC 9560: 0x2526 (CNVi composite device)
- xpci.h defines AX201 (0x02F0) which is Ice Lake/Tiger Lake, NOT Whiskey Lake
- Impact: xpci_find_device(ctx, 0x8086, 0x02F0) will return NULL on real G4 hardware
- Fix: Add XPCI_DEV_INTEL_WIFI_AC9560 = 0x2526u

### HW-S9-P1-02: elitebook_x360.c References Tiger Lake, Not Whiskey Lake
- File: elitebook_x360.c:8, :105, :292-300
- Header comment says "Intel Tiger Lake / Alder Lake platform" -- WRONG for G4
- Battery register comments say "Tiger Lake EliteBook x360" -- WRONG
- Thunderbolt MMIO base 0xFED80000 is Tiger Lake-specific -- G4 is Whiskey Lake (no TB4)
- HP EliteBook x360 1030 G4 has TB3 via Alpine Ridge, NOT TB4 via integrated Tiger Lake
- Impact: Thunderbolt D3hot write goes to wrong MMIO address on G4 hardware
- Risk: Writing to unmapped MMIO could cause machine check exception (#MC)

### HW-S9-P1-03: Thunderbolt MMIO Access Without HHDM Mapping
- File: elitebook_x360.c:306-307
- `(volatile uint32_t *)(uintptr_t)(HP_TBT_MMIO_BASE + HP_TBT_PCIE_PWR)`
- This accesses physical address 0xFED80044 as a raw pointer WITHOUT adding HHDM_BASE
- After vmm_init(), only HHDM-mapped addresses are valid for MMIO access
- All other drivers (LAPIC, HPET, NVMe, iGPU) correctly add HHDM_BASE to physical addresses
- Impact: Page fault (#PF) on real hardware -- the kernel will halt

### HW-S9-P1-04: ACPI Namespace 64 Entries May Be Insufficient
- File: xacpi.h:57 -- XACPI_NAMESPACE_SIZE = 64
- HP EliteBook BIOS DSDT typically contains 200-400 named objects
- HP WMI alone defines ~30 methods (GBSG, SBSG, WMID, WQBC, etc.)
- With only 64 slots, the scanner will silently drop objects after slot 63
- The _S3_ and _S5_ sleep packages may not be found if they appear late in DSDT
- Impact: Sleep state entry may fail silently (typ_a/typ_b remain 0)

### HW-S9-P1-05: XHPET Counter Overflow in ticks_to_ns Multiplication
- File: hpet.c:148 -- `return (ticks * ctx->period_fs) / 1000000ULL`
- period_fs can be up to 0x05F5E100 (100,000,000 fs) per XHPET_CLK_PERIOD_MAX
- If ticks exceeds ~184 billion (1.84 * 10^11), the multiply overflows uint64
- After ~12,800 seconds (~3.5 hours) at 14.3 MHz, the counter hits overflow range
- Impact: Time conversion returns wrong values after ~3.5 hours of uptime

## P2 Findings (Medium -- Correctness/Robustness)

### HW-S9-P2-01: HPET 64-bit Read Double-Read Roll-Over Has Race Window
- File: hpet.c:54-62
- The double-read pattern reads lo1, hi, lo2. If lo2 < lo1, re-reads hi.
- Correct for single roll-over. But if TWO roll-overs occur between lo1 and lo2
  (counter increments past 0xFFFFFFFF twice), the guard fails.
- On 14.3 MHz HPET, two full 32-bit wraps take ~300 seconds per wrap = ~600s total
- Probability of double-wrap in ~3 instruction window: effectively zero
- Status: Theoretically unsound but practically safe. Document the assumption.

### HW-S9-P2-02: PCI Bus Scan Limited to Buses 0-3
- File: xpci.h:54 -- XPCI_MAX_BUS = 4
- Most EliteBook x360 devices are on bus 0, but PCIe root ports may assign buses 1-7
- NVMe behind a PCIe switch could appear on bus 4+
- Impact: Some devices may not be discovered during PCI enumeration
- Workaround: Increase XPCI_MAX_BUS to 8 for safety

### HW-S9-P2-03: GENISO 16 Component Limit Assessment
- File: gen_iso.h:125 -- GISO_MAX_COMPONENTS = 16
- Current GEN.OS components: AetherBoot.efi, xenos.elf, gensd.elf, manifest.bin,
  rootfs.xpkg = 5 required. Optional: initrd, keyring, dtb = 8 total
- 16 slots provides 2x headroom. SUFFICIENT for Sprint 9.
- Future risk: if per-driver firmware blobs are added (iwlwifi, i915 GuC/HuC),
  could approach limit

### HW-S9-P2-04: ACPI AML Scanner Skip-On-Error Is Byte-Granular
- File: xacpi.c:474-475 and :509-510
- When an unrecognized data object or method body is encountered, the scanner
  advances by 1 byte (`pos++`)
- This can cause the scanner to land mid-opcode and misparse subsequent AML
- Impact: Some namespace objects may be missed or misidentified
- Standard practice: Use PkgLength to skip unknown compound objects entirely

### HW-S9-P2-05: HP EC Busy-Wait Loops Are Not Bounded by Time
- File: elitebook_x360.c:64-69 (ec_wait_ibf), :73-79 (ec_wait_obf)
- Loops iterate 100,000 times with io_pause() (~1us each) = ~100ms timeout
- On hardware with a stuck EC (dead battery, firmware update in progress),
  this blocks the kernel boot for 100ms per EC operation
- hp_elitebook_x360_init() calls ec_read/ec_write ~15 times = ~1.5s maximum block
- Not fatal, but noticeable boot delay if EC is slow

### HW-S9-P2-06: DSDT Not in XSDT on HP EliteBook
- File: xacpi.c:763 -- `xa_find_table(ctx, XACPI_SIG_DSDT)`
- DSDT is NOT listed as a pointer in the XSDT. Per ACPI spec, DSDT is found via
  the FADT field at offset 140 (DSDT_addr, 64-bit) or offset 40 (DSDT_addr, 32-bit)
- xa_find_table() only searches table_phys[] populated from XSDT entries
- Impact: DSDT will NOT be found on real HP hardware. xacpi_parse_dsdt() will fail.
  _S3_, _S5_ sleep types will remain 0. Sleep state entry will use SLP_TYP=0.
- Fix: Read FADT offset 140 (X_DSDT) or offset 40 (DSDT) to locate the DSDT

### HW-S9-P2-07: LAPIC IPI Timeout Has No Error Reporting
- File: lapic.c:262-266 (xlapic_send_ipi)
- If the IPI delivery timeout expires (100,000 iterations), the function returns silently
- No error code, no log message, no retry
- Impact: TLB shootdown IPIs that fail silently cause stale TLB entries = memory corruption

## P3 Findings (Low -- Hardening/Polish)

### HW-S9-P3-01: GENISO PVD Combined Hash Uses XOR (Not Cryptographic)
- File: gen_iso.c:175-177 -- XOR of SHA-256 hashes
- XOR is not a collision-resistant combination function
- Two components with identical hashes cancel each other in combined_hash
- Not a security issue because Ed25519 signature covers individual hashes
- Suggestion: Use SHA-256(concat(all hashes)) for manifest integrity

### HW-S9-P3-02: XHPET Period Validation Missing Lower Bound
- File: hpet.c:93 -- checks period_fs == 0 and > XHPET_CLK_PERIOD_MAX
- No lower bound check. A period_fs of 1 (1 femtosecond = 10^15 Hz) passes validation
- Impact: freq_hz would compute to 10^15, overflow uint32_t
- Suggestion: Enforce minimum period_fs (e.g., 10,000 fs = 100 GHz max frequency)

### HW-S9-P3-03: elitebook_x360.c Uses inb/outb Without Shared Definitions
- File: elitebook_x360.c:48-56 defines static inline inb()/outb()
- main.c:100-108 defines static inline _inb()/_outb()
- xacpi.c:661-663 defines static inline xa_outw()
- Three separate copies of I/O port access functions
- Suggestion: Centralize in pal.h or a shared io.h header

### HW-S9-P3-04: LAPIC Calibration Comment Says 10ms, Code Is ~250us
- File: lapic.c:187 -- LAPIC_CALIB_MS = 10
- The constant name and calculation assume 10ms, but the actual delay is ~250us
- bus_hz = elapsed * 1600 applies a 10ms correction factor to a 0.25ms measurement
- Result: bus_hz is ~40x too low (see P0-01)

### HW-S9-P3-05: HP WMI Settings Table Is Static, Not ACPI-Derived
- File: xacpi.c:602-618 -- xa_hp_wmi_init_defaults()
- Settings are hardcoded, not read from ACPI namespace
- xacpi_hp_wmi_get/set operate on a RAM table, not real EC/BIOS registers
- Acceptable for Sprint 8-9 scaffold, but must be replaced with real AML evaluation

### HW-S9-P3-06: XACPI RSDP Signature Validation Incomplete for ACPI 2.0+
- File: xacpi.c:89-96 -- xa_rsdp_valid()
- Only validates first 20 bytes (ACPI 1.0 checksum)
- ACPI 2.0+ extended RSDP has an additional checksum over the full 36 bytes (ext_checksum)
- xacpi_init() uses xsdt_phys (ACPI 2.0+ field) but does not verify ext_checksum
- Impact: A corrupted extended RSDP could pass validation

## Hardware Integration Score: 6/10

### Scoring Breakdown
- Driver correctness (register offsets, bit masks, MMIO): 8/10
- Boot integration (wired into kmain): 2/10 (NOT WIRED -- P0-02)
- Timer calibration accuracy: 2/10 (busy-loop, not HPET -- P0-01)
- ACPI compatibility: 5/10 (DSDT not found via FADT -- P2-06)
- PCI device coverage: 7/10 (WiFi ID wrong -- P1-01)
- HP platform support: 6/10 (Tiger Lake references on Whiskey Lake -- P1-02)
- Power management: 7/10 (S3/S5 path correct if DSDT found, TB MMIO wrong -- P1-03)
- Error handling: 6/10 (IPI silent failure -- P2-07)

## HP EliteBook x360 Boot Readiness Assessment

### Will These Drivers Initialize on Real Hardware? NO (with current kmain)

1. kmain() does NOT call any Sprint 9 driver init functions (P0-02)
2. Even if wired, LAPIC timer calibration will be wildly inaccurate (P0-01)
3. DSDT will not be found because xa_find_table searches XSDT, not FADT (P2-06)
4. Thunderbolt MMIO access will page fault (missing HHDM_BASE -- P1-03)
5. WiFi detection will fail (wrong PCI device ID -- P1-01)

### If P0 and P1 Issues Are Fixed:
- HPET: WILL initialize (MMIO via HHDM, period validation, counter access correct)
- LAPIC: WILL initialize (MSR access, SIVR enable, LVT masking all correct)
- PCI: WILL enumerate (config mechanism #1 correct, bus scan functional)
- ACPI: PARTIALLY works (RSDP/XSDT valid, FADT decode correct, DSDT path broken)
- HP EC: WILL initialize (I/O port EC protocol correct, register offsets plausible)

## ACPI Compatibility Assessment

### Tables Parsed by XACPI:
| Table | Signature | Status |
|-------|-----------|--------|
| RSDP  | "RSD PTR " | Validated (20-byte checksum, not 36-byte) |
| XSDT  | "XSDT" | Enumerated (64-bit pointers, checksum verified) |
| FADT  | "FACP" | Decoded (PM1a/PM1b control block ports) |
| DSDT  | "DSDT" | NOT FOUND (searched in XSDT, should use FADT offset) |
| SSDT  | "SSDT" | Defined but not parsed |
| MCFG  | "MCFG" | Defined but not parsed (PCIe ECAM) |
| HPET  | "HPET" | Defined in xhpet.h but not searched by xacpi_init |

### HP EliteBook ACPI Tables (expected on real hardware):
- RSDP, XSDT, FADT, DSDT, SSDT (multiple), MCFG, HPET, MADT (APIC),
  DMAR (VT-d), BGRT, FPDT, TPM2, WDAT (HP watchdog), WPBT (HP tools)
- MADT (APIC topology) is NOT parsed -- CPU enumeration relies on boot_handoff
- DMAR (VT-d IOMMU) is NOT parsed -- DMA protection not active

## Top 5 Hardware Integration Risks

1. **Dead Code** -- Sprint 9 drivers exist but are not called from kmain (P0-02)
2. **Timer Inaccuracy** -- LAPIC calibration uses uncontrolled busy-loop (P0-01)
3. **DSDT Not Discoverable** -- xacpi searches XSDT instead of FADT for DSDT (P2-06)
4. **Platform Mismatch** -- elitebook_x360.c targets Tiger Lake, hardware is Whiskey Lake (P1-02)
5. **Thunderbolt Page Fault** -- MMIO access without HHDM_BASE (P1-03)
