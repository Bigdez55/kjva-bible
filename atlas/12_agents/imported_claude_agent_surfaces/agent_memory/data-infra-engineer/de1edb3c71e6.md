# Sprint 3 Data Model Audit — xsec.h / xnet.h / xpkg.h
# Date: 2026-03-05

## Critical Findings (Fix Before Any Archive Written to Disk)

### FINDING 01 — CRITICAL — xpkg_registry_t is ~40 MB Static
- xpkg_package_t ≈ 79,080 bytes (driven by xpkg_file_entry_t[256])
- xpkg_registry_t = 512 × 79,080 ≈ 40.5 MB in BSS — fatal on freestanding OS
- Fix: split into xpkg_pkg_record_t (~380 bytes) + shared xpkg_file_pool_t (16,384 entries = ~4.9 MB)
- xpkg_pkg_record_t fields: name[64], version, state, dep_count, file_count, file_pool_start, content_hash[32], install_path[256]

### FINDING 02 — CRITICAL — xpkg_archive_header_t Missing __attribute__((packed))
- All xnet.h wire structs are packed; xpkg_archive_header_t is not
- Future field insertion will silently add padding, corrupting on-disk format
- Direct byte-pointer cast is UB on ARM/RISC-V without packed
- Fix: add __attribute__((packed)) + _Static_assert(sizeof == 24)
- ALSO needed: xpkg_file_entry_t (see Finding 03)

## High Findings

### FINDING 03 — HIGH — xpkg_file_entry_t Padding Gap Leaks Stack Bytes
- Layout: path[256] + uint32_t size + uint16_t mode + uint8_t hash[32] + uint32_t offset
- uint32_t offset at byte 294 is not 4-byte aligned → compiler inserts 2 bytes of padding
- Those 2 bytes contain stack garbage, leaked into archive files
- Fix: reorder to path[256] + uint32_t size + uint32_t offset + uint16_t mode + uint8_t _pad[2] + uint8_t hash[32]
- Add __attribute__((packed)) + _Static_assert(sizeof == 300)

### FINDING 04 — HIGH — ARP Packed Struct Unaligned sender_ip / target_ip
- xnet_arp_pkt_t: sender_ip at offset 14, target_ip at offset 24 (not 4-byte aligned)
- Wire format is correct per RFC 826, but direct dereference is UB on ARM/RISC-V
- Fix: add xnet_arp_sender_ip() / xnet_arp_target_ip() safe accessor macros using xnet_memcpy
- Coding law: never dereference packed struct uint32_t fields directly

### FINDING 05 — HIGH — Gossip Node Has Hidden Padding + No Wire Form
- xnet_gossip_node_t: 2 bytes padding between port (offset 20) and state enum (offset 24)
- If gossip messages serialize this struct to UDP, protocol breaks across compiler versions
- Fix: add explicit uint16_t _pad in in-memory struct; add separate xnet_gossip_wire_node_t packed struct
- xnet_gossip_wire_node_t: id[16] + addr(4) + port(2) + state(1,uint8) + _reserved(1) + incarnation(8) + last_seen_ns(8) = 40 bytes
- _Static_assert(sizeof(xnet_gossip_wire_node_t) == 40)

### FINDING 06 — HIGH — xnet_sockaddr_t Zero-Slack for IPv6
- xnet_sockaddr_t = uint16_t family + uint8_t _data[26] = 28 bytes total
- xnet_sockaddr_in6_t = 28 bytes; fits exactly with zero margin
- One field addition to sockaddr_in6_t would silently truncate on copy
- Fix: _Static_assert(sizeof(xnet_sockaddr_in6_t) <= sizeof(xnet_sockaddr_t)); grow _data to 110 bytes for Unix domain socket future compat

### FINDING 07 — HIGH — xsec_tls_ctx_t Mixes Hot Crypto State with 16 KB Cold I/O Buffer
- sizeof(xsec_tls_ctx_t) ≈ 17,312 bytes; hot path only needs ~108 bytes of keys/seqs
- record_buf[16640] inside struct forces full 17 KB into cache on every crypto op
- Cannot be stack-allocated in freestanding kernel (stack overflow risk)
- Fix preferred: caller provides record_buf as pointer; context becomes ~680 bytes (L1-friendly)

### FINDING 08 — HIGH — xpkg_index_entry_t.dep_names is a CSV String
- char dep_names[256] stores comma-separated dep names — no version constraints
- Requires tokenizer at every read site; 256 bytes can overflow at 16 × 15-char names
- Fix: replace with uint32_t dep_count + char dep_names[16][64] (Option B)
- Index entry grows from ~372 to ~1408 bytes; repo index becomes ~720 KB — acceptable

## Medium Findings

### FINDING 09 — MEDIUM — Archive Header Has No CRC32
- magic + format_version fields but no header checksum
- Single bit flip in metadata_offset/payload_offset corrupts parse before Ed25519 can run
- Fix: add uint32_t header_crc32 as last field; validate as very first check in xpkg_format_validate()
- header_crc32 = CRC32 of preceding 20 bytes
- Also: add extensions_offset field for forward compat (see schema evolution section)

### FINDING 10 — MEDIUM — Cert Validity Time Unit Mismatch
- xsec_x509_cert_t.not_before / not_after: seconds since Unix epoch (parsed from ASN.1)
- xsec_x509_verify_chain() parameter: now_ns — nanoseconds since BOOT (pal_time_now_ns())
- These are NOT comparable without RTC wall-clock conversion
- Fix: rename parameter to now_unix_sec (seconds since Unix epoch); require caller to provide RTC-derived time

### FINDING 11 — MEDIUM — ARP Cache Saturated by Full Gossip Cluster
- ARP_CACHE_SIZE = 256, GOSSIP_MAX_NODES = 256 — identical; zero slack for DNS/NTP/gateway
- ARP eviction under full gossip cluster will cause ARP re-resolution storms
- Fix: increase ARP_CACHE_SIZE to 512; add ARP_CACHE_PINNED_MAX = 8 for infra entries

### FINDING 12 — MEDIUM — xpkg_version_t Missing SemVer Pre-Release Field
- Only major/minor/patch; no pre-release or build metadata
- Resolver treats 1.0.0-rc1 and 1.0.0 as equal
- Fix: add char pre_release[32]; update xpkg_version_cmp: non-empty pre_release < empty
- Schema evolution: add in format_version 2; v1 parsers treat absent field as ""

## Low Findings

### FINDING 13 — LOW — Audit Global Not Const (Writable Before Init)
- extern xsec_audit_ctx_t xsec_g_audit — any TU can write before xsec_audit_init()
- Fix: expose as extern const xsec_audit_ctx_t; implementation .c keeps mutable static

### FINDING 14 — LOW — Dep Graph Has No Lock
- xpkg_dep_graph_t has no pal_spinlock_t; xpkg_registry_t has one
- Concurrent resolve + install corrupts visited/on_stack fields
- Fix: add lock OR document "single-caller-only, not thread-safe" explicitly

### FINDING 15 — LOW — TLS_AES_128_GCM_SHA256 (0x1301) Missing
- RFC 8446 REQUIRES 0x1301; XSEC only has 0x1302 and 0x1303
- Most real-world TLS 1.3 peers advertise 0x1301 first; will get XSEC_ERR_NOT_SUPPORTED
- Fix: add XSEC_TLS_CIPHER_AES_128_GCM_SHA256 = 0x1301
- Requires: SHA-256 transcript (already have it); AES-128 key schedule addition

## Endianness Summary
- xnet.h wire structs: correctly packed; XNET_IPV4() produces host-byte-order uint32 — must call xnet_htonl() before assigning to packed header fields
- xsec.h: SHA uses xsec_be32/be64 (correct); ChaCha20 uses xsec_le32 (correct per RFC 8439)
- xpkg.h: all archive fields little-endian via xpkg_load_le32/store_le32 (correct for x86-64)

## Schema Evolution Contract (establish now)
- XPKG_FORMAT_VERSION_MAX = 1; parsers MUST reject version > max
- Reserved flags bits (2-15) MUST be zero in v1; non-zero = reject (not ignore)
- Planned v2 changes: extensions_offset field, pre_release in version, header_crc32
- Blue-Green rule: bump format_version before any struct shape change

## Static Pool Memory Budget
- xpkg_registry_t CURRENT: ~40.5 MB — CRITICAL, must fix
- xpkg_registry_t TARGET (after fix): ~195 KB records + ~4.9 MB file pool ~= 5.1 MB total
- ARP pending queue: 256 x 3 x 1514 = 1.16 MB — document this explicitly
- xsec_audit_ctx_t ring: 1024 x ~80 bytes ~= 81 KB — acceptable
- xsec_tls_ctx_t: ~17 KB per session — must not be stack-allocated; requires static or caller-managed storage

## Files Audited
- sec/xsec/include/xsec.h (658 lines)
- net/xnet/include/xnet.h (707 lines)
- pkg/xpkg/include/xpkg.h (597 lines)

---

# Sprint 3 Data Flow Audit — tls13.c / netif.c / ip4.c / tcp.c / socket.c / ethernet.c / audit.c / pkg_format.c / pkg_verify.c / install.c
# Date: 2026-03-05
# All findings fixed: 2026-03-05

## FINDING INDEX

| ID | Severity | Component | Status | Title |
|----|----------|-----------|--------|-------|
| S3-DI-C01 | CRITICAL | tls13.c | FIXED | Double send in tls_send_record_encrypted |
| S3-DI-C02 | CRITICAL | tls13.c | FIXED | ~33 KB combined stack frame — freestanding stack overflow |
| S3-DI-H01 | HIGH | audit.c | FIXED | Ring buffer overflow silently discards events |
| S3-DI-H02 | HIGH | aes_gcm.c | FIXED | Decrypt destroys ct buffer when ct/pt overlap on tag-mismatch |
| S3-DI-H03 | HIGH | ip4.c | FIXED | g_frag_out_buf race — concurrent fragment streams corrupt each other |
| S3-DI-H04 | HIGH | pkg_format.c | FIXED | hex_to_hash wrong loop bound |
| S3-DI-H05 | HIGH | pkg_format.c / pkg_verify.c | FIXED | Self-referential content_hash (hashed region includes hash line) |
| S3-DI-M01 | MEDIUM | install.c | FIXED | xpkg_list_installed TOCTOU: count read under lock, iteration without lock |
| S3-DI-M02 | MEDIUM | socket.c | FIXED | Blocking UDP recv busy-spins — livelock in single-threaded scheduler |
| S3-DI-M03 | MEDIUM | tls13.c | CONFIRMED OK | transcript_get save/restore already correct |
| S3-DI-M04 | MEDIUM | netif.c | FIXED | tx callback uses dangling pointer into zeroed interface slot |
| S3-DI-L01 | LOW | audit.c | FIXED | Auto-init check-then-act race |
| S3-DI-L02 | LOW | pkg_verify.c | FIXED | Lock ordering documented (s_key_lock -> s_rev_lock) |
| S3-DI-L03 | LOW | ip4.c | FIXED | hdr_copy[20] read with ihl_bytes up to 60 |

## Fix Implementation Details (2026-03-05)

### S3-DI-C01 + S3-DI-C02 (tls13.c)
- Removed double-send: spurious tls_send_record_plain() call already gone in current HEAD
- Promoted scratch[16640] + ct_buf[16640] to module-static: tls_enc_scratch[] + tls_enc_ct_buf[]
- Static buffers zeroed via xsec_secure_zero before return on all paths including error paths

### S3-DI-H01 + S3-DI-L01 (audit.c)
- Added volatile uint64_t dropped_events to xsec_audit_ctx_t in xsec.h
- xsec_audit_log: increments dropped_events atomically when total_events >= RING_SIZE
- xsec_audit_log: removed auto-init; returns XSEC_ERR_STATE if !initialized (caller must call init)
- xsec_audit_dump: prints "Visible in ring: N" and "WARNING: events dropped: N" separately
- Added xsec_audit_get_dropped() public accessor declared in xsec.h

### S3-DI-H02 (aes_gcm.c)
- xsec_aes_gcm_decrypt: rejects overlapping ct/pt with XSEC_ERR_INVAL before aes_gcm_core
- Overlap test: buffers overlap when NOT (pt_end <= ct || ct_end <= pt)

### S3-DI-H03 + S3-DI-L03 (ip4.c)
- Added g_frag_out_lock (PAL_SPINLOCK_INIT) protecting g_frag_out_buf
- xnet_ip4_input: acquires g_frag_out_lock before ip4_reassemble, holds through protocol dispatch
- Lock released after dispatch_rc determined; non-fragment paths never acquire g_frag_out_lock
- hdr_copy resized from [IP4_HDR_LEN=20] to [IP4_MAX_HDR_LEN=60]; copies ihl_bytes not IP4_HDR_LEN

### S3-DI-H04 (pkg_format.c)
- hex_to_hash: unified single loop: for i in 0..31 where i*2+1 < hex_len

### S3-DI-H05 (pkg_format.c + pkg_verify.c)
- content_hash now covers [payload_offset, signature_offset) only (payload bytes, not metadata)
- xpkg_format_serialize: two-pass — writes metadata with '0' placeholder, writes payload, back-patches hash
- xpkg_format_validate: hashes [payload_offset, signature_offset) not [metadata_offset, signature_offset)
- xpkg_verify_integrity: hashes [pay_off, sig_off) not [meta_off, sig_off)
- Wire format unchanged (XPKG_FORMAT_VERSION unchanged); existing archives must be rebuilt

### S3-DI-M01 (install.c)
- xpkg_list_installed: per-entry snapshot pattern — take lock, copy entry, release, call cb, re-acquire
- Re-reads count each iteration to handle concurrent removals compacting the registry

### S3-DI-M02 (socket.c)
- Blocking UDP recv: XNET_UDP_RECV_SPIN_MAX=8 fast spins with pause instruction
- Then XNET_UDP_RECV_YIELD_MAX=128 pal_thread_yield() calls
- After YIELD_MAX exceeded: returns XNET_ERR_AGAIN to prevent indefinite starvation

### S3-DI-M04 (netif.c)
- xnet_netif_send: snapshots struct xnet_netif iface_snap = *iface under lock before unlock
- tx callback receives &iface_snap (local copy), not &g_interfaces[if_idx] (live slot)
- Stats still updated against live slot (re-validated under lock after tx returns)

### S3-DI-L02 (pkg_verify.c)
- xpkg_remove_trusted_key: added comment block documenting fixed lock order (s_key_lock -> s_rev_lock)
- Linter also snapshot-fixed xpkg_verify_signature to copy key store under lock before verify loop

---

## DETAILED FINDINGS

### S3-DI-C01 — CRITICAL — tls13.c: Double send in tls_send_record_encrypted

**Location:** tls13.c inside tls_send_record_encrypted, approximately lines 257-271

**Description:**
The function calls `tls_send_record_plain(ctx, XSEC_TLS_CT_APPLICATION_DATA, NULL, 0u)` and then
ALSO manually sends the header + ciphertext + tag in three separate transport.send calls.

The first call emits a 5-byte TLS record header for a zero-length APPLICATION_DATA record to the wire.
The second block emits the real encrypted record. The peer receives two back-to-back TLS records: one
zero-length APPLICATION_DATA (which it will try to decrypt and fail with an unexpected_message alert),
followed by the real record (which it will never reach).

Every encrypted application data send after handshake is malformed. The TLS channel delivers no
application data to the peer.

**Fix:** Delete the `tls_send_record_plain(ctx, XSEC_TLS_CT_APPLICATION_DATA, NULL, 0u)` call.
The three manual transport.send calls that follow constitute the complete and correct wire record.

---

### S3-DI-C02 — CRITICAL — tls13.c: ~33 KB combined stack allocation

**Location:** tls_send_record_encrypted and tls_recv_record_encrypted

**Description:**
tls_send_record_encrypted allocates on the stack:
  scratch[TLS13_MAX_RECORD + TLS13_RECORD_OVERHEAD] = scratch[16640]
  ct_buf[TLS13_MAX_RECORD + TLS13_RECORD_OVERHEAD]  = ct_buf[16640]
  Total: ~33,280 bytes of stack, plus the function call frame overhead.

tls_recv_record_encrypted allocates:
  ct_buf[TLS13_MAX_RECORD + TLS13_RECORD_OVERHEAD]  = 16640 bytes
  pt_buf[TLS13_MAX_RECORD + 1]                      = 16385 bytes
  Total: ~33,025 bytes of stack.

In a freestanding x86_64 kernel with a per-CPU stack of 8KB-16KB (typical), these functions will
immediately overflow the stack, corrupting kernel data below the stack pointer.

Additionally, scratch holds plaintext. If the encrypt call fails (rc != XSEC_OK at line 254),
the function returns before reaching xsec_secure_zero(scratch, ...) at line 274, leaving plaintext
on the stack.

**Fix:**
1. Move the large buffers to module-static (one per TLS context, serialized by the context's own lock),
   OR pass them in the xsec_tls_ctx_t struct (as the record_buf field already provides 16640 bytes —
   reuse that field for one of the buffers at a time).
2. Add xsec_secure_zero(scratch) on all early-exit paths before the final return.

---

### S3-DI-H01 — HIGH — audit.c: Silent ring buffer overflow

**Location:** xsec_audit_log, audit.c lines 129-139; xsec_audit_dump lines 190-229

**Description:**
When total_events >= 1024, write_idx wraps and overwrites the oldest entry silently. There is no
dropped_events counter, no overflow flag, and no external notification. xsec_audit_dump prints
"Total events logged: N" where N > 1024, giving the false impression that all N events are available.
A security auditor querying the last 1024 entries has no way to know how many earlier events were lost.

XSEC_AUDIT_HANDSHAKE_FAILED, XSEC_AUDIT_CERT_REJECTED, and XSEC_AUDIT_AUTH_TAG_MISMATCH events lost
to overflow are a compliance gap — these are exactly the events a SIEM would need to detect an attack.

**Fix:** Add `volatile uint64_t dropped_events` to xsec_audit_ctx_t. In xsec_audit_log, when
write_idx causes an overwrite (i.e., total_events >= XSEC_AUDIT_RING_SIZE), increment dropped_events
atomically before overwriting. Include dropped_events in xsec_audit_dump output and in
xsec_audit_query_recent return metadata.

---

### S3-DI-H02 — HIGH — aes_gcm.c: Overlapping buffer data destruction on auth failure

**Location:** xsec_aes_gcm_decrypt and aes_gcm_core, aes_gcm.c

**Description:**
In aes_gcm_core (decrypt path): gctr() writes decrypted bytes into `out` BEFORE the GHASH-based tag
is computed and verified. The tag check happens after. If the caller passes ct and pt as overlapping
buffers (e.g., decrypt in-place), gctr() has already overwritten ct with the (unauthenticated)
plaintext. When the tag fails and xsec_secure_zero(pt, ct_len) is called, pt==ct is zeroed,
destroying both the plaintext AND the original ciphertext. The caller is left with no recoverable data.

This is not a plaintext exposure (the zeroing happens), but is a data integrity destruction bug.
The API documentation says "separate buffers required" but this is not enforced.

**Fix:** At entry to xsec_aes_gcm_decrypt, add overlap detection:
  if (ct < pt + ct_len && pt < ct + ct_len) return XSEC_ERR_INVAL;

---

### S3-DI-H03 — HIGH — ip4.c: g_frag_out_buf race condition

**Location:** ip4.c line 407 (declaration) and xnet_ip4_input lines 489-526

**Description:**
`static uint8_t g_frag_out_buf[FRAG_MAX_SIZE]` is a single module-static buffer. ip4_reassemble()
fills it under g_frag_lock and returns XNET_OK. The lock is then released. xnet_ip4_input sets
payload = g_frag_out_buf (outside any lock) and dispatches to TCP/UDP/ICMP.

If two threads call xnet_ip4_input concurrently — both completing reassembly of different fragmented
datagrams — both call ip4_reassemble(), both write into g_frag_out_buf (the second write happens
during or after the first thread's lock release), and both dispatch from a buffer that may contain
mixed data from both datagrams.

**Fix:** Copy the reassembled data from g_frag_out_buf into a local stack buffer while still holding
g_frag_lock, then release the lock and dispatch from the stack copy. Given the 64KB size, declare
a local uint8_t local_payload[FRAG_MAX_SIZE] inside the is_fragment branch. This is large for the
stack — alternatively, add a second reassembly buffer per frag_entry_t so each fragment stream has
its own output buffer.

---

### S3-DI-H04 — HIGH — pkg_format.c: hex_to_hash inconsistent loop bounds

**Location:** pkg_format.c lines 208-215 (hex_to_hash function)

**Description:**
```c
// First loop: bytes 0..15
for (uint32_t i = 0; i < 16 && i * 4 < hex_len; i++) { ... }
// Second loop: bytes 16..31
for (uint32_t i = 16; i < 32 && i * 2 + 1 < hex_len; i++) { ... }
```
The first loop bound is `i * 4 < hex_len`. For hex_len=64 this works (max i=15: 60 < 64). But for
any hex_len < 60 (a truncated or malformed hash field), the first loop exits before byte 15. This is
a copy-paste error — the condition should match the second loop: `i * 2 + 1 < hex_len`. The result
is that bytes 15 downward may be zero-filled when they should contain decoded hash bytes, causing
a false XPKG_ERR_INTEGRITY on packages with valid hashes stored in truncated metadata.

**Fix:** Merge into one loop with the correct bound:
  for (uint32_t i = 0; i < 32 && (i * 2 + 1) < hex_len; i++) {
      hash_out[i] = (uint8_t)((hex_to_nibble(hex[i*2]) << 4) | hex_to_nibble(hex[i*2+1]));
  }

---

### S3-DI-H05 — HIGH — pkg_format.c / pkg_verify.c: Self-referential content_hash

**Location:** pkg_format.c xpkg_format_validate lines 586-607; pkg_verify.c xpkg_verify_integrity lines 326-335

**Description:**
content_hash is defined as SHA-256 of archive[metadata_offset .. signature_offset). The metadata
section contains the key-value line `content_hash=<64-hex-chars>`. That line is INSIDE the covered
region. This means the hash is computed over a region that contains a hex encoding of that same hash.

A legitimately constructed package cannot satisfy this: SHA-256("...content_hash=X...") = X has no
known solution. Every correctly signed package will fail xpkg_format_validate with XPKG_ERR_INTEGRITY.

This means the content_hash integrity check is permanently broken for all packages. The signature
check (Ed25519 over content_hash) is also broken because the content_hash that was signed can never
match the recomputed hash.

**Fix (Option A, minimal change):** Define content_hash to cover only the payload section:
archive[payload_offset .. signature_offset). This is the region that is NOT self-referential.
Update both xpkg_format_validate and xpkg_verify_integrity.

**Fix (Option B, matches IP header pattern):** Keep the range as [metadata_offset .. signature_offset)
but zero-fill the content_hash metadata field before computing the hash (as in IP header checksum
verification). Document: "content_hash= field is set to 64 zeros for the purpose of hash computation."

---

### S3-DI-M01 — MEDIUM — install.c: xpkg_list_installed TOCTOU

**Location:** install.c lines 491-500

**Description:**
The function acquires the lock to read count, releases the lock, then iterates 0..count calling the
callback without holding the lock. A concurrent xpkg_remove that runs between count-read and iteration
compacts the registry by swapping the removed slot with the last slot and decrementing count. The
iterator may then: (a) visit the now-compacted entry at its new position twice, or (b) access a slot
at index >= new count that has been zeroed by memset.

**Fix:** Either hold the lock for the entire iteration (callback must be non-blocking), or snapshot
the count and add a `p->state != 0` guard per entry to tolerate concurrent mutations.

---

### S3-DI-M02 — MEDIUM — socket.c: Blocking UDP recv busy-spins

**Location:** socket.c xnet_recv lines 469-496

**Description:**
The blocking UDP recv path loops: acquire lock, check udp_recv_ready, release lock, call
pal_thread_yield(), repeat. In the XENOS single-core cooperative scheduler (Sprint 3), there is no
preemptive context switch. pal_thread_yield() with no other runnable thread is a no-op. Network
packet delivery into udp_recv_ready happens via interrupt context. If the calling thread is at a
privilege level where interrupts are masked, or if the scheduler does not return to interrupt context
during yield, this loop never terminates.

There is no timeout, no cancellation mechanism, and no backoff.

**Fix:** Add a timeout_ns parameter (0 = non-blocking, UINT64_MAX = block indefinitely). Use
pal_time_now_ns() to implement the timeout. Document that truly blocking recv requires an interrupt-
driven scheduler that can preempt the yield loop.

---

### S3-DI-M03 — MEDIUM — tls13.c: transcript_get mutates context

**Location:** tls13.c transcript_get lines 413-418

**Description:**
```c
static void transcript_get(xsec_tls_ctx_t *ctx, uint8_t out[32]) {
    xsec_sha256_ctx_t saved = ctx->transcript_hash;
    xsec_sha256_final(&ctx->transcript_hash, out);   // finalizes & mutates ctx->transcript_hash
    ctx->transcript_hash = saved;                     // restore
}
```
xsec_sha256_final likely zeroes or invalidates the context it finalizes. The save-and-restore pattern
is correct for single-threaded use but fails if:
1. Two handshake steps race and both call transcript_get — the second save captures a partially-
   finalized state.
2. A future SHA-256 implementation uses a pointer-to-self or PRNG internal state that is not valid
   after copy.

**Fix:** Operate on a copy, never touch ctx:
  xsec_sha256_ctx_t copy = ctx->transcript_hash;
  xsec_sha256_final(&copy, out);
  xsec_secure_zero(&copy, sizeof(copy));
This is re-entrant and leaves ctx->transcript_hash pristine.

---

### S3-DI-M04 — MEDIUM — netif.c: Stale pointer to interface slot after lock release

**Location:** netif.c xnet_netif_send lines 302-315

**Description:**
At line 302 the spinlock is released. At line 304, the tx callback is called as:
  tx(&g_interfaces[if_idx], frame, frame_len)
Between releasing the lock and the callback completing, another thread could call
xnet_netif_unregister(if_idx), which calls xnet_memset(iface, 0, ...) on the same slot. The tx
callback now has a pointer to a live struct that is being zeroed concurrently.

**Fix:** Copy the relevant fields (tx_fn, name for logging) under the lock before releasing it.
Pass the copied tx_fn pointer directly instead of &g_interfaces[if_idx]. The netif pointer argument
to the tx callback should be a snapshot, not a live pointer to the table entry.

---

### S3-DI-L01 — LOW — audit.c: Non-atomic auto-init

**Location:** xsec_audit_log lines 113-116

**Description:**
`if (!xsec_g_audit.initialized) { xsec_audit_init(); }` is a check-then-act race. Two concurrent
callers both read initialized=false and both call xsec_audit_init(), which calls
xsec_memset(&xsec_g_audit, 0, sizeof(xsec_g_audit)). The second memset may zero an entry that the
first caller just wrote at line 129.

**Fix:** Require explicit xsec_audit_init() at system boot (already documented as the contract).
Remove the auto-init path. Return XSEC_ERR_STATE if not initialized.

---

### S3-DI-L02 — LOW — pkg_verify.c: Lock ordering undocumented

**Location:** xpkg_remove_trusted_key lines 191-197

**Description:**
This function acquires s_key_lock, then acquires s_rev_lock while holding s_key_lock. All other
functions that use s_rev_lock (xpkg_key_is_revoked, xpkg_revoke_key) do not also hold s_key_lock.
Current code is safe because only one function acquires both. But the ordering rule is not written down.
A future developer adding a code path that takes s_rev_lock then s_key_lock will deadlock.

**Fix:** Add at the top of pkg_verify.c:
  /* Lock ordering: ALWAYS s_key_lock before s_rev_lock. Never reverse. */

---

### S3-DI-L03 — LOW — ip4.c: hdr_copy[20] with ihl_bytes up to 60

**Location:** ip4.c xnet_ip4_input lines 448-453

**Description:**
```c
uint8_t hdr_copy[IP4_HDR_LEN];   // 20 bytes
xnet_memcpy(hdr_copy, hdr, IP4_HDR_LEN);
// ...
uint16_t computed = xnet_ip4_checksum(hdr_copy, ihl_bytes);  // ihl_bytes can be up to 60
```
xnet_ip4_checksum reads ihl_bytes/2 words from hdr_copy. If ihl_bytes > 20 (IP options present),
the checksum function reads up to 40 bytes past the end of hdr_copy into adjacent stack memory.

In practice XNET never generates options and most inbound packets won't have them, but a crafted
packet with IHL=15 (60 bytes) triggers a deterministic 40-byte stack read overrun.

**Fix:** Either expand hdr_copy to uint8_t hdr_copy[60] and copy ihl_bytes bytes, or clamp:
  uint32_t cksum_bytes = (ihl_bytes <= IP4_HDR_LEN) ? IP4_HDR_LEN : ihl_bytes;
  uint8_t hdr_copy[60];
  xnet_memcpy(hdr_copy, hdr, cksum_bytes);
  ((xnet_ip4_hdr_t *)hdr_copy)->checksum = 0;
  uint16_t computed = xnet_ip4_checksum(hdr_copy, cksum_bytes);

---

## DATA FLOW CORRECTNESS SUMMARY

### Flow 1: TLS Record Layer (plaintext -> AEAD -> wire -> AEAD -> plaintext)
ENCRYPT path (tls_send_record_encrypted):
  1. plaintext || inner_content_type -> scratch buffer
  2. AAD built as 5-byte TLSCiphertext header
  3. Per-record nonce = write_iv XOR (seq_num big-endian) -- CORRECT per RFC 8446 S5.3
  4. AES-GCM or ChaCha20-Poly1305 encrypt scratch -> ct_buf + tag
  5. CRITICAL BUG (S3-DI-C01): zero-length plain record sent first, then real record
  6. send_seq incremented -- CORRECT

DECRYPT path (tls_recv_record_encrypted):
  1. Header received -- CORRECT
  2. Ciphertext + tag received separately -- CORRECT
  3. Nonce derived same way as encrypt -- CORRECT
  4. Decrypt with AAD=header -- CORRECT (header used as AAD, matching encrypt side)
  5. Tag mismatch -> audit log + return error -- CORRECT
  6. Inner content type stripped from end of plaintext -- CORRECT
  7. recv_seq incremented -- CORRECT
  CONCERN (S3-DI-M03): transcript_get modifies context in place

AES-GCM implementation correctness:
  - Key schedule: AES-256 correct (14 rounds, 60 words)
  - GHASH: GF(2^128) correct (0xe1 reduction polynomial)
  - GCTR: counter starts at inc32(J0) -- CORRECT per NIST SP 800-38D
  - Tag computation: GHASH(AAD) then GHASH(CT) then GHASH(len_block) then XOR E(K,J0) -- CORRECT
  - Decrypt: zeroes output on tag mismatch -- CORRECT
  - Constant-time tag comparison via xsec_ct_eq -- CORRECT
  - Constant-time S-box via full-table scan -- CORRECT

### Flow 2: Network Packet Path (ethernet frame -> IP -> TCP -> socket read)
  Driver calls xnet_netif_input(if_idx, frame, frame_len)
  -> stats update (under lock)
  -> xnet_eth_input: MAC filter, EtherType dispatch
  -> xnet_ip4_input: version/IHL/checksum/TTL validation
  -> Fragment reassembly if needed (RACE BUG S3-DI-H03 on g_frag_out_buf)
  -> xnet_tcp_input: TCP state machine, sequence validation, data delivery to recv ring
  -> xnet_tcp_recv: copies from TCB recv ring to caller buffer
  -> xnet_recv (socket): calls xnet_tcp_recv, returns bytes to application

  Buffer lifecycle: frames are const pointers through the entire receive chain -- no copies
  until tcp_recv copies from TCB ring to app buffer. No double-free risk in this path.
  Packet buffers are caller-provided (netif driver); XNET never frees them.

### Flow 3: XPKG Install Chain (.xpkg -> parse -> verify -> extract -> install)
  xpkg_install:
    1. xpkg_format_parse: header bounds-checked, metadata parsed, signature copied -- CORRECT
    2. xpkg_gate_check: 9-gate check including signature + integrity gates
    3. xpkg_verify_signature: Ed25519 verify over content_hash -- STRUCTURALLY CORRECT
       BUT content_hash itself is broken (S3-DI-H05) so the signed value is meaningless
    4. xpkg_verify_integrity: SHA-256 over [meta_off..sig_off) vs stored content_hash -- ALWAYS FAILS (S3-DI-H05)
    5. extract_files: per-file SHA-256 verify BEFORE "write" -- CORRECT data integrity chain
       (but only for file-level hashes; the archive-level hash is broken)
    6. Registry commit under spinlock -- CORRECT
  Data integrity chain: broken at archive level (S3-DI-H05), intact at per-file level.

### Flow 4: XSEC Audit Ring Buffer (1024 entries)
  On overflow: oldest entry silently overwritten -- HIGH BUG (S3-DI-H01)
  Concurrent write correctness: atomic fetch-add on write_idx ensures each writer gets a unique
    slot -- CORRECT design
  Dump/query use spinlock to prevent torn reads -- CORRECT
  But: write happens outside the lock (by design for lock-free writes), so dump may observe
    a partially-written entry if a writer is mid-write when dump runs. This is inherent to the
    lock-free write design and acceptable for a diagnostic log.
  write_idx and total_events are updated in two separate atomic operations (lines 129 and 139),
    so there is a window where total_events lags write_idx by 1. This is benign for ring_count
    computation (ring_count uses total_events, which may be 1 behind write_idx momentarily).

## Summary
- CRITICAL: 2 (S3-DI-C01, S3-DI-C02)
- HIGH: 5 (S3-DI-H01 through S3-DI-H05)
- MEDIUM: 4 (S3-DI-M01 through S3-DI-M04)
- LOW: 3 (S3-DI-L01 through S3-DI-L03)
- Data flow total: 14 new findings (in addition to 15 schema findings above)

---

# Sprint 3 Runtime State-Table Audit — XNET + XPKG Live Data Structures
# Auditor: Data Infrastructure Engineer
# Date: 2026-03-06
# Files: arp.c, tcp.c, dns.c, gossip.c, dep_resolve.c, install.c, pkg_verify.c, repo_index.c

## FINDING INDEX

| ID | Severity | Subsystem | Description |
|----|----------|-----------|-------------|
| P1-PKG-03 | P1 | XPKG dep resolver | Off-by-one in dep_name parser truncates 63-char names silently |
| P1-PKG-06 | P1 | XPKG trusted keys | Revocation list overflow — new key compromises unrevokable |
| P2-ARP-01 | P2 | XNET ARP | STALE entry TTL compared against resolved timestamp, not stale timestamp |
| P2-TCP-01 | P2 | XNET TCP | Silent rexmit queue full drop — connection degrades without diagnostic |
| P2-TCP-03 | P2 | XNET TCP | TIME_WAIT expiry requires tick; table exhaustion under high-churn server |
| P2-DNS-02 | P2 | XNET DNS | Single global pending query slot — concurrent resolvers timeout |
| P2-PKG-02 | P2 | XPKG install | Upgrade rollback marks BROKEN with no provenance event emitted |
| P2-PKG-04 | P2 | XPKG solver | Conflict detection O(V²) runs after full graph build — inefficient |
| P2-PKG-07 | P2 | XPKG verify | Static local key snapshot in xpkg_verify_signature not thread-safe |
| P2-GOSSIP-01 | P2 | XNET gossip | Silent JOIN drop at 256-node limit — no operator signal or NACK |
| P2-GOSSIP-03 | P2 | XNET gossip | PING_REQ relay is no-op stub — indirect ping (SWIM) non-functional |
| P2-GOSSIP-04 | P2 | XNET gossip | DEAD message header path omits g_member_count decrement (overcounts) |
| P3-TCP-02 | P3 | XNET TCP | Header comment says 256 TCBs; implementation is TCP_TCB_MAX=128 |
| P3-DNS-01 | P3 | XNET DNS | Eviction picks oldest-inserted, not soonest-expired (suboptimal) |
| P3-PKG-05 | P3 | XPKG repo | xpkg_repo_get_indexes() returns raw static pointer without lock |
| P3-GOSSIP-02 | P3 | XNET gossip | uint64_t incarnation wraparound → permanent SUSPECT (theoretical) |

**Totals: 2 P1, 10 P2, 4 P3**

---

## CAPACITY ANALYSIS

| Table | Limit | Enforcement | On Overflow |
|-------|-------|-------------|-------------|
| ARP cache | 256 | Eviction (STALE→RESOLVED order) | No error; evicts oldest |
| TCP TCBs | 128 | XNET_ERR_NOMEM | Hard fail on alloc |
| TCP ring buffers | 16 KB each | Clip to available | Write returns short count |
| TCP rexmit queue | 32 per TCB | Silent drop (P2-TCP-01) | No diagnostic |
| TCP OOO buffer | 8 per TCB | Silent drop | Acceptable per RFC |
| DNS cache | 128 | LRU-by-insertion eviction | Evicts oldest-inserted |
| Gossip members | 256 | Silent JOIN drop (P2-GOSSIP-01) | No NACK |
| Gossip event queue | 32 | Evict most-transmitted | Deterministic |
| XPKG registry | 512 | XPKG_ERR_CAPACITY | Hard fail |
| XPKG dep graph | 512 nodes | XPKG_ERR_CAPACITY | Hard fail |
| Trusted key store | 32 | XPKG_ERR_CAPACITY | Hard fail |
| Revocation list | 64 | XPKG_ERR_CAPACITY — silent on remove_key (P1-PKG-06) | Key not revoked |
| Repo list | 16 | XPKG_ERR_CAPACITY | Hard fail |

---

## DETAILED FINDINGS

### P1-PKG-03 — XPKG dep_names parser off-by-one

Location: dep_resolve.c build_graph() dep_names parsing loop (~line 380-438)

The comma-separated dep_names parser includes the last character when `*(dp+1) == '\0' && *dp != ','`
but checks `if (dn_len < 63)` before adding it. Package names are char[64] (63 chars + null).
A dependency name of exactly 63 characters has its last character silently dropped, producing an
incorrect 62-character name that will not match any repository entry.

This only affects the index-only dep resolution path (when src_pkg is NULL). The full-package struct
path uses dep->name directly and is unaffected.

Fix: change `if (dn_len < 63)` to `if (dn_len < 64)` for the last-char inclusion. The null
terminator is written separately at dep_name[dn_len] after the inclusion, so no overflow occurs.

---

### P1-PKG-06 — Revocation list saturation

Location: pkg_verify.c xpkg_remove_trusted_key() lines 204-211; xpkg_revoke_key() lines 245-248

When s_revoked_count == XPKG_MAX_REVOKED_KEYS (64):
- xpkg_revoke_key() returns XPKG_ERR_CAPACITY
- xpkg_remove_trusted_key() silently skips the s_revoked_hashes append with no log, no error return

A platform that has cycled through 64+ compromised keys cannot revoke any further key.
New package installs cannot be blocked even if the signing key is known-compromised.

The key IS removed from the trusted store (active=false, zeroed), so it cannot sign NEW packages.
But if the key material is re-added by any code path, it bypasses revocation detection entirely.

Fix (preferred): when revocation list is full, evict index 0 (memmove entries 1..63 down) to make
room. This preserves the most recently revoked keys — the most operationally relevant set.
Alternative: increase XPKG_MAX_REVOKED_KEYS to 256.
Minimum: log a CRITICAL-level event and return an error from xpkg_remove_trusted_key.

---

### P2-ARP-01 — STALE TTL timestamp comparison error

Location: arp.c xnet_arp_resolve() lines 314-337; xnet_arp_expire() lines 480-483

In xnet_arp_resolve(), when an entry is RESOLVED with TTL expired:
  entry->state = ARP_STATE_STALE;  // sets state but does NOT update timestamp_ns
  // falls through to STALE branch
  // STALE branch: transitions to PENDING, issues ARP request
This is functionally correct for the new PENDING transition.

In xnet_arp_expire(), STALE entries are freed when `(now - e->timestamp_ns) >= ARP_TTL_NS * 2`.
The timestamp_ns on a STALE entry is the ORIGINAL resolved time, not when it became stale.
An entry resolved at T=0, TTL expired at T=30min, forced STALE at T=30min has timestamp_ns=T=0.
At T=31min, the expire pass sees age = 31min >= 60min (2×TTL)? No. So the entry lingers.
At T=60min, age=60min >= 60min? Yes. Entry freed after holding STALE for 30 minutes — correct.

But in xnet_arp_resolve() under the STALE branch: the entry was already STALE (from a prior expire
pass). The timestamp_ns comparison `(now - entry->timestamp_ns) < ARP_TTL_NS` runs against the
original resolved timestamp. If the entry was resolved 31 minutes ago and became STALE in the expire
pass (at 30 minutes), calling xnet_arp_resolve() at 31 minutes: (31min - 0) < 30min? No — it takes
the STALE→PENDING transition correctly. No false-hit bug. The concern is the reverse: if STALE entry
has timestamp_ns refreshed on every PENDING→RESOLVED cycle, the 2×TTL free window is reset. Confirmed
timestamp IS refreshed on ARP_INPUT resolution (entry->timestamp_ns = now). So the 2×TTL window
measures from last resolution, not last stale transition. Documented as acceptable behavior; the
"STALE for 2×TTL" rule means 60 minutes after the last successful resolution.

The true gap: when entry is RESOLVED and TTL expires in the resolve path, `entry->state = ARP_STATE_STALE`
is set but timestamp_ns is NOT updated. The entry keeps timestamp from when it was last resolved.
Then in the STALE branch: `entry->state = ARP_STATE_PENDING; entry->timestamp_ns = now;` — timestamp
IS updated here. So the final state after the stale-re-resolve path has a fresh timestamp. Confirmed
correct path.

Residual concern: if the table is full of PENDING entries and arp_find_free() returns NULL (line 342),
xnet_arp_resolve() returns XNET_ERR_NOMEM with no eviction fallback. A denial-of-service sending ARP
requests to 256 unknown IPs saturates the table, causing all subsequent ARP resolution to fail.

Reclassify as **P3** — operational concern, not a timestamp correctness bug.

---

### P2-TCP-01 — Silent rexmit queue full drop

Location: tcp.c rexmit_enqueue() lines 504-522

When all TCP_REXMIT_QUEUE_MAX (32) rexmit slots are occupied, the enqueue loop exhausts without
storing the segment. There is no return value, no counter, no log message.

The segment WAS sent (tcp_send_segment called before rexmit_enqueue in all call sites). It will not
be retransmitted on timeout. Under sustained packet loss with 32+ in-flight segments, unacknowledged
data is permanently lost from the retransmit perspective. The TCP connection eventually times out
via keepalive (2 hours idle) rather than retransmitting promptly.

Fix: rexmit_enqueue should return bool. On false, the calling tcp_send_segment wrapper should log
and increment a per-TCB rexmit_overflow count. In xnet_tcp_timer_tick(), a non-zero overflow count
should RST the connection. A stalled connection is better terminated than silently degraded.

---

### P2-TCP-03 — TIME_WAIT table exhaustion

Location: tcp.c xnet_tcp_timer_tick() (not read in full — inferred from design comments)

TIME_WAIT entries persist for TCP_TIME_WAIT_NS = 120 seconds. Expiry requires xnet_tcp_timer_tick()
to be driven by xnet_tick() at sufficient cadence. With TCP_TCB_MAX=128 and 120-second TIME_WAIT,
a server accepting 1+ connections/second exhausts the table in ~2 minutes.

No fallback exists to close TIME_WAIT entries early if the table is full. tcb_alloc() returns NULL
and new connections are rejected with XNET_ERR_NOMEM.

Fix: document required minimum tick rate (1 Hz minimum). Add a warning log when TIME_WAIT count
exceeds TCP_TCB_MAX/2 (64). Consider RFC 6191 (reducing TIME_WAIT with timestamps) for Sprint 4.

---

### P2-DNS-02 — Single global pending query slot

Location: dns.c g_dns_pending (line 259), dns_do_resolve() lines 414-423

g_dns_pending is a single struct. Concurrent calls to xnet_dns_resolve() race:
- Caller A registers QID=0x1234, sets waiting=true
- Caller B overwrites: QID=0x5678, waiting=true
- A's DNS response arrives, fails QID match, discarded
- A spin-loops to timeout

In Sprint 3 (single-threaded), this is safe. Any future multi-threaded XNET caller will experience
DNS resolution failure on concurrent lookups.

Fix for Sprint 4: replace g_dns_pending with a small array (4 entries) keyed by QID.
Concurrent resolution limited to 4 in-flight queries — sufficient for platform use.

---

### P2-PKG-02 — Upgrade rollback no provenance event

Location: install.c xpkg_upgrade() lines 458-468

On failed install of new version after old version removal, the rollback re-registers the old
package with state=XPKG_STATE_BROKEN. No provenance event is emitted. In Sprint 4 with real VFS,
files will be partially removed with no audit trail. A BROKEN package has no automatic repair trigger.

Fix: emit a provenance event on rollback: `pipeline.xpkg.upgrade.rollback` with old/new version,
failure reason, and timestamp. Add a BROKEN package scan at XPKG init that logs outstanding BROKENs.

---

### P2-PKG-07 — Static local key snapshot not thread-safe

Location: pkg_verify.c xpkg_verify_signature() lines 275-283

`static xpkg_trusted_key_t key_snapshot[XPKG_MAX_TRUSTED_KEYS]` is a function-scope static.
All invocations share the same static buffer. Concurrent calls from different threads race on writes.

In Sprint 3: single-threaded, safe.
In Sprint 4+: BROKEN under concurrent package verification.

Fix: declare key_snapshot as a stack-local variable. At 32 × sizeof(xpkg_trusted_key_t) = 32 × 100
bytes = ~3.2 KB stack usage — acceptable for a non-recursive call path in a kernel context with
a kernel stack of at least 8 KB.

---

### P2-GOSSIP-01 — Silent JOIN drop at membership table capacity

Location: gossip.c gossip_recv_callback() lines 379-389

When g_members table is full (all 256 slots active), gossip_alloc_member() returns NULL.
The JOIN is silently dropped with no log, no NACK to the joining node.
The joining node will keep sending JOINs and PINGs, eventually being suspected DEAD by any
members that probe its address (no responses) — a false negative that cascades into misleading
cluster state.

Fix: log `[xnet/gossip] WARNING: membership table full, rejecting JOIN from %08x` at minimum.
For Sprint 4: send a negative JOIN response (not in current SWIM spec — use DEAD message with
a special flag, or add a GOSSIP_MSG_FULL message type).

---

### P2-GOSSIP-03 — PING_REQ relay is no-op stub

Location: gossip.c gossip_recv_callback() case GOSSIP_MSG_PING_REQ: line 425-428

The relay side of indirect ping does nothing:
  case GOSSIP_MSG_PING_REQ:
      /* For Sprint 3: forward the PING_REQ as a direct PING to embedded target */
      break;

The gossip_tick() sends PING_REQ to k=3 relays when a direct ping times out. All 3 relays
silently ignore it. The false-positive failure detection rate is higher than SWIM specifies —
any single-path failure (route asymmetry, NAT, etc.) triggers SUSPECT regardless of whether
indirect paths exist.

Fix: implement relay behavior:
1. Parse target node ID from first piggybacked event in the PING_REQ message
2. Send direct GOSSIP_MSG_PING to target on behalf of requester
3. When ACK arrives from target (matched by target node ID), forward ACK back to requester

---

### P2-GOSSIP-04 — DEAD header path skips member count decrement

Location: gossip.c gossip_recv_callback() case GOSSIP_MSG_DEAD: lines 453-458

Direct DEAD message: sets m->info.state = GOSSIP_NODE_DEAD but does NOT set m->active=false
and does NOT decrement g_member_count.

Piggybacked DEAD event (gossip_process_events): correctly checks m->active, sets false, decrements.

Divergent logic: a node declared DEAD via the message header (not piggybacked) inflates g_member_count
by 1. The node IS excluded from gossip_select_random (dead state check) but max_transmit calculation
uses g_member_count, so infection fanout is inflated.

Fix: in case GOSSIP_MSG_DEAD, after setting m->info.state = GOSSIP_NODE_DEAD, add:
  if (m->active) { m->active = false; if (g_member_count > 0) g_member_count--; }

---

### P3-TCP-02 — Header comment says 256 TCBs, implementation is 128

Location: tcp.c line 87: #define TCP_TCB_MAX 128U

The audit brief and xnet.h §12 reference "256 descriptors". TCP_TCB_MAX is 128.
Static memory impact: 128 TCBs × ~93 KB each ≈ 11.9 MB BSS (already large; 256 would be 23.8 MB).

Fix: update all documentation references to "128 TCP connections (TCBs)".

---

### P3-DNS-01 — DNS cache evicts oldest-inserted, not soonest-expired

Location: dns.c dns_cache_alloc() lines 229-241

Eviction strategy: minimum cached_at_ns (insertion time).
Better strategy: minimum (cached_at_ns + ttl_ns - now) — evict the entry expiring soonest.

Current behavior: a 86400-second TTL entry inserted at T=0 is evicted before a 30-second TTL
entry inserted at T=1 that has already been expired for hours. The expired slot wastes cache space
while valid long-TTL entries are dropped prematurely.

Fix: in dns_cache_alloc(), track minimum remaining_ttl_ns = (cached_at_ns + ttl*1e9) - now
with special case: if remaining_ttl_ns <= 0, this entry is already expired — evict immediately.
The second pass (if no expired entries found) evicts the minimum remaining_ttl_ns entry.

---

### P3-PKG-05 — xpkg_repo_get_indexes returns raw pointer without lock

Location: repo_index.c lines 395-399

Returns direct pointer to s_repo_indexes static array and a snapshot of s_repo_count without
holding s_repo_lock. The function comment documents this: "safe as long as no concurrent add/remove."

In Sprint 3 this is safe — XPKG is single-caller. In Sprint 4 with concurrent operations this
is a TOCTOU: caller reads s_repo_count=N, then a repo_remove compacts the array, then caller
iterates index N-1 which now contains different data.

Fix for Sprint 4: expose a snapshot API:
  xpkg_status_t xpkg_repo_snapshot_indexes(xpkg_repo_index_t *out_buf, uint32_t buf_count,
                                             uint32_t *out_count);
This copies indexes under lock into caller-provided buffer.

---

### P3-GOSSIP-02 — uint64_t incarnation wraparound (theoretical)

Location: gossip.c g_self.incarnation++ on SUSPECT receipt

At 1 increment/second (unrealistically high), overflow takes 585 billion years.
At overflow, wrapped incarnation=0 would be rejected by all peers (0 < UINT64_MAX).
Node permanently stuck in SUSPECT with no way to clear it.

No fix needed for Sprint 3-5. Document as known behavior.

---

## INITIALIZATION AND ZEROING SUMMARY

All module-static tables confirmed initialized on startup:
- ARP, TCP, DNS: C static BSS (zero at boot)
- Gossip: xnet_gossip_init() called by xnet_init() — explicit memset
- XPKG registry: explicit C initializer (count=0, PAL_SPINLOCK_INIT)
- Trusted keys: xpkg_verify_init() via xpkg_init() — memset + SYSTEM key pre-load
- Repo list: xpkg_repo_init() via xpkg_init() — memset

All free/remove paths zero their entries before making slots available:
- ARP: xnet_memset on expiry and eviction
- TCP: xnet_memset on LAST_ACK completion
- DNS: xnet_memset on TTL expiry
- XPKG: xpkg_memset on registry compaction last slot; volatile wipe on key removal

No information leakage between entries identified. All allocation paths zero before use.
