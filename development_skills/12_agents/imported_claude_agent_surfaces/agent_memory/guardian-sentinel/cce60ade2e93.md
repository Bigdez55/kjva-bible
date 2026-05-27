# Sprint 15 Security Audit (2026-03-07)

## Scope
- `net/xnet/drv/virtio_net.c` -- virtio-net legacy PCI driver
- `net/xnet/drv/e1000.c` -- Intel E1000 NIC driver
- `sec/xsec/tls/aes_ni.c` -- AES-NI hardware crypto (AES-128-GCM)
- `kernel/xenos/core/main.c` -- XK_SYS_EXEC process isolation
- `sec/xsec/include/xsec.h` -- __AES__ guard for intrinsics
- `aetherboot/src/aetherboot.c` -- D-04 rename efi_main -> aetherboot_main
- `kernel/xenos/mm/vmm.c` -- vmm_alloc_process_pml4, vmm_map_into

## Verdict: HOLD (1 P1 found, 5 P2, 3 P3)

## Findings

### P1-VN-RX-01: virtio RX pkt_len not capped to buffer size
- File: virtio_net.c:619-642
- Device-supplied pkt_len from used ring is only checked > HDR_SIZE, not < BUF_SIZE
- If malicious/buggy device reports len > 1528, frame_ptr + frame_len overflows buffer
- Fix: add `if (pkt_len > VIRTIO_NET_RX_BUF_SIZE) { skip; }`

### P2-E1K-BAR0-01: E1000 MMIO BAR0 physical address not range-checked
- File: e1000.c:438-449
- mmio_phys from PCI config space mapped via PHYS_TO_VIRT without upper bound check
- Malicious PCI device could supply phys addr beyond HHDM 4GB window
- Fix: reject mmio_phys >= 4GB (HHDM covers 4 × 1GB pages)

### P2-EXEC-WX-01: vmm_map_into allows VM_WRITE|VM_EXEC (no W^X enforcement)
- File: vmm.c:157 (_vm_flags_to_pte) -- no check for WRITE+EXEC combo
- main.c uses correct flags (user stack=RW, code=RX) but nothing PREVENTS W+X
- Fix: reject flags with both VM_WRITE and VM_EXEC in _vm_flags_to_pte

### P2-EXEC-ENTRY-01: XK_SYS_EXEC does not validate a1 is in kernel text range
- File: main.c:1194,1264-1266
- a1=0 is checked, but arbitrary kernel VA (e.g. pointing to data/stack) accepted
- Should validate a1 >= KERN_BASE and a1 < KERN_BASE + KERN_MAP_SIZE

### P2-VN-TX-01: virtio TX frame_len truncation from size_t to uint32_t
- File: virtio_net.c:537
- `uint32_t pkt_len = VIRTIO_NET_HDR_SIZE + (uint32_t)frame_len`
- On 64-bit, if frame_len > ~4GB, cast truncates silently; but MTU check catches it

### P2-AESNI-H-SCRUB-01: GHASH subkey H not scrubbed in __m128i form
- File: aes_ni.c:458
- H_bytes is scrubbed, but __m128i H (line 385) lives on stack unscrubbed
- Fix: `H = _mm_setzero_si128();` after use

### P3-E1K-EEPROM-01: EEPROM read addr parameter is uint8_t (max 255) -- sufficient
- File: e1000.c:164
- E1000 EEPROM is 64 words; addr=0..2 is fine. No overflow possible with uint8_t.
- Advisory: add explicit `if (addr > 63) return false;` for defense-in-depth

### P3-AESNI-SELFTEST-01: selftest returns XSEC_OK when AES-NI is absent
- File: aes_ni.c:564-567
- Design-correct (fallback to software path), but masks hardware faults on CPUs
  that SHOULD have AES-NI. Advisory: log a warning when aesni_available() returns false.

### P3-EXEC-CLEANUP-01: User code page mapping failure is non-fatal
- File: main.c:1273-1281
- By design (Sprint 15 stub for Sprint 16 ELF loader), but means process runs with
  kernel VA only. Advisory: make fatal when ELF loader ships.
