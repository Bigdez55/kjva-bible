# Full GEN.OS Observability Audit -- Sprint 0-9

**Auditor:** Observability Nexus (Apex Engineering Corps)
**Date:** 2026-03-07
**Scope:** Complete observability infrastructure audit, Sprints 0-9
**Codebase state:** Post-Sprint 9 (commit 810e3e4)

---

## OBSERVABILITY NEXUS REPORT

```
OBSERVABILITY NEXUS REPORT
===========================
Scope:         Full Platform (Sprints 0-9)
Pillar:        All (Logs / Metrics / Traces)
Coverage:      4/20 subsystems have audit events; 0/20 have structured logging
Maturity:      Level 1 (Minimal -- fatal-only visibility in some subsystems)
Priority Gaps: TCP DARK, XSTORE DARK, XBLOB DARK, XJIT DARK, Audit->Journal routing missing
```

---

## 1. PRIOR FINDING VERIFICATION

### 1.1 P0-01: TCP (1,341 LOC) Zero Audit/Logging -- STILL OPEN

**File:** `net/xnet/transport/tcp.c`

Verified via exhaustive grep: ZERO occurrences of `xsec_audit_log`, `journal_write`,
`pal_console_printf`, or `pal_console_puts` in the entire file.

TCP is the largest protocol handler in XNET and remains completely invisible:
- Connection state machine transitions: silent
- RST reception/transmission: silent
- Retransmit timeout exhaustion: silent
- SYN flood or sequence number attack: silent
- Keepalive failure: silent
- Window zero probe: silent
- Out-of-order segment overflow: silent

**VERDICT: P0 -- UNCHANGED. Highest-priority observability gap in the platform.**

### 1.2 P0-02: XPKG Refusal Gate Zero xsec_audit_log -- FIXED

**File:** `pkg/xpkg/gate/refusal_gate.c`

Two `xsec_audit_log` calls confirmed:
- Line 537: `xsec_audit_log(XSEC_AUDIT_PKG_GATE_FORCED, XSEC_MODULE_XPKG, check->detail)` -- when FAIL is force-demoted to WARN
- Line 545: `xsec_audit_log(XSEC_AUDIT_PKG_GATE_FAIL, XSEC_MODULE_XPKG, check->detail)` -- for all non-PASS outcomes

Additionally, extensive `pal_console_printf` at lines 489, 533-534, 548-560 for gate results.

**VERDICT: FIXED. Both FAIL and FORCED outcomes emit structured audit events.**

### 1.3 P0-03: Dead Event Types -- ALL FIXED

Previously 3 of 11 audit event types had no call sites:

| Event Type | Status | Call Site |
|-----------|--------|-----------|
| XSEC_AUDIT_KEY_GENERATED | FIXED | x25519.c:445, ed25519.c:729 |
| XSEC_AUDIT_DECRYPT_FAIL | FIXED | aes_gcm.c:496, chacha20.c:446 |
| XSEC_AUDIT_TLS_ALERT_RECV | FIXED | tls13.c:356 |

**All 11 event types are now ACTIVE with at least one production call site.**

### 1.4 TLS Audit Coverage -- IMPROVED (33% -> 83%)

tls13.c now has 20 `xsec_audit_log` calls (was 8):
- HANDSHAKE_FAILED: 13 sites (12 error paths + 1 ServerFinished fail)
- HANDSHAKE_COMPLETE: 1 site (line 1086)
- SESSION_CLOSED: 1 site (line 1193)
- TLS_ALERT_RECV: 1 site (line 356)
- AUTH_TAG_MISMATCH: 1 site (line 402)
- CERT_REJECTED: 3 sites (lines 858, 863, 882)

Security-relevant error paths: 19/23 handshake errors audited (83%).
Record-layer/IO errors: 1/26 audited (4%) -- by design (low signal).

### 1.5 Advisory-03: Audit -> Journal Routing -- STILL OPEN

Exhaustive verification:
- `init/` directory: ZERO references to `xsec_audit`, `audit_query`, `audit_dump`, `audit_get_dropped`
- `sec/` directory: ZERO references to `journal_write`, `journal`, `gensd`
- `supervisor.c`: Does NOT poll XSEC audit ring
- `gensd main.c`: `journal_flush_serial()` flushes GENSD journal only, never reads XSEC audit ring

**All 38 production xsec_audit_log events are write-only. No consumer exists.**

### 1.6 Audit Ring Saturation -- STILL OPEN

Ring capacity: 1024 entries (XSEC_AUDIT_RING_SIZE).
At 100 events/sec (failed TLS handshake storm), ring overwrites in ~10 seconds.
No persistent-storage flush hook exists. No overflow notification mechanism.

---

## 2. SPRINT 4-9 OBSERVABILITY COVERAGE

### 2.1 XSTORE (Sprint 4) -- DARK

**Files:** xstore.c, btree.c, wal.c, mvcc.c, page_cache.c (~2,100 LOC combined)

ZERO occurrences of any logging function across the entire XSTORE subsystem.

Silent failure modes:
- Superblock CRC mismatch (xstore.c:83): returns XSTORE_ERR_CORRUPT silently
- WAL ring full (wal.c:68): returns XSTORE_ERR_WAL_FULL silently
- WAL entry CRC mismatch (wal.c:118): entry silently skipped during replay
- WAL replay partial txn discard: silently discarded (no log of which txn)
- B+ tree node split: silent
- Page cache eviction: silent
- OCC conflict (mvcc.c:165): returns XSTORE_ERR_CONFLICT silently
- Checkpoint write failure (wal.c:213-218): returns error silently

**Notable:** `xstore_stats_t` struct exists with cache_hits/misses/evictions fields,
but no consumer reads them. This is latent metrics infrastructure with no exposure.

### 2.2 XBLOB (Sprint 4) -- DARK

**Files:** blob.c, index.c, gc.c, xblob.c (~800 LOC combined)

ZERO occurrences of any logging function. Content-addressed storage operations
(insert, lookup, garbage collection) are completely invisible.

### 2.3 MVCC WAL Fix Observability Gap (P1)

**File:** `store/xstore/txn/mvcc.c` lines 212-226

```c
if (we->op == XSTORE_WAL_OP_INSERT) {
    // ... btree_lookup to recover value for WAL ...
    if (xstore_btree_lookup(store, txn->snapshot_lsn, &k, &vout) == XSTORE_OK) {
        entry.val_len = (uint16_t)vout.out_len;
    }
    /* On lookup failure: val_len=0, replay remains best-effort.
     * This should not occur in normal operation ... */
}
```

When `btree_lookup` fails, the WAL INSERT entry is written with `val_len=0`.
During crash recovery, `xstore_wal_replay()` will call `xstore_btree_insert()`
with an empty value -- causing silent data loss for that key.

This failure path has:
- ZERO pal_console_printf
- ZERO xsec_audit_log
- ZERO journal_write
- Only a code comment stating "should not occur"

**This is a P1 observability gap. A btree_lookup failure during commit means the
in-memory page cache is inconsistent with the WAL, which is exactly when crash
recovery diagnostics are most critical.**

### 2.4 XSHELL (Sprint 5) -- PARTIAL

**File:** `shell/xshell/src/xshell.c` (475 LOC)

14 `pal_console_puts`/`pal_console_printf` calls covering:
- Init: "[XSHELL] Initialized -- XSHELL x.y.z"
- Run: "[XSHELL] Entering main loop"
- Shutdown: "[XSHELL] Shutting down"
- App launch: "[XSHELL] App launched: %s (id=%u)"
- App close: "[XSHELL] App closed (id=%u)"
- Notify: "[XSHELL] Notify [%u]: %s"
- Error paths: "[XSHELL] xframe_init failed", etc.

Not routed to journal. No structured logging. No error counts.

### 2.5 Orange Suite (Sprint 5) -- PARTIAL

4 pal_console_printf calls across notes.c (2), calendar.c (1), drive.c (1).
Lifecycle init only. No error tracking for document operations.

### 2.6 XORCHESTRA (Sprint 5) -- PARTIAL

15 pal_console_printf calls across xorchestra.c (9) and health.c (6).
Service registry and health check results logged to console.
Not routed to journal.

### 2.7 XMIND (Sprint 6) -- PARTIAL

~35 pal_console_printf calls across xmind.c, weights_loader.c, tokenizer.c, quantize.c.
Covers:
- Model init success/failure with config details
- State allocation success/OOM
- Weights loader GGUF parsing events
- BPE vocab loading
- Q4 quantization roundtrip verification

Missing: inference latency metrics, tokens/sec, memory utilization, KV cache fill level.

### 2.8 XJIT (Sprint 6) -- DARK

**Files:** ir.c, regalloc.c, codegen.c, xjit.c (~1,817 LOC)

ZERO logging in compilation/codegen/register allocation code.
Only the XEMU JIT backend has a stats dump function (xjit_backend.c:412-417)
that prints hits/misses/compiled/lifted_insns -- but this is a diagnostic-only
dump, not runtime event logging.

### 2.9 XBUILD (Sprint 7) -- PARTIAL

30 pal_console_printf calls across graph.c (16), scanner.c (3), executor.c (4),
xbuild.c (6), xbuild.h (1). DAG operations and build steps logged to console.

### 2.10 XEMU (Sprint 7) -- PARTIAL

27 pal_console_printf calls across xemu.c (18), rewriter.c (2), xjit_backend.c (6),
xemu.h (1). ELF loading, instruction decoding, syscall translation logged.

### 2.11 Boot Chain (Sprint 8) -- PARTIAL

47 pal_console_printf calls covering all 10 boot stages with pass/fail status.
Structured xchain_result_t with per-stage OK flags.
Not routed to journal (pal_console_printf goes to serial only).

### 2.12 XACPI/XHPET/XLAPIC/XPCI (Sprint 8-9) -- PARTIAL

Hardware driver subsystems have diagnostic dump functions and init logging.
XACPI: ~30 pal_console_printf (FADT decode, DSDT namespace scan, sleep states).
XHPET: ~10 pal_console_printf (timer calibration, counter readout).
XLAPIC: ~15 pal_console_printf (APIC ID, bus frequency, timer init).
XPCI: ~8 pal_console_printf (device enumeration, BAR decode).

No runtime event notifications. No interrupt rate tracking. No thermal alerts.

### 2.13 GENISO (Sprint 9) -- PARTIAL

11 pal_console_printf calls in gen_iso.c. ISO component addition and manifest
verification events logged to console.

---

## 3. GENSD JOURNAL ASSESSMENT

### 3.1 Write API

```c
void journal_write(const char *service, int level, const char *msg);
```

- `service`: Human-readable string, hashed to fnv1a32 for storage
- `level`: 0=debug, 1=info, 2=warn, 3=error, 4=fatal
- `msg`: Null-terminated, truncated to 255 bytes

### 3.2 Ring Buffer

- Size: 4MB (JOURNAL_SIZE = 4 * 1024 * 1024)
- Location: BSS (.bss segment, zero-initialized)
- Entry format: 16B header + variable msg (max 255B)
- Capacity: ~15,600 entries at average 256 bytes per entry
- Wrap behavior: Oldest entries silently overwritten (newest wins)
- Thread safety: `pal_spinlock_t g_jlock`
- Total entries tracked: `g_total_entries` (uint64_t, monotonic)

### 3.3 Read API

`journal_read_recent()` at lines 233-240 is a **Sprint 1 STUB**:
```c
void journal_read_recent(...) {
    /* Sprint 1 stub: return nothing */
    (void)max_entries;
    if (out_entries) *out_entries = NULL;
    if (out_count)   *out_count   = 0;
}
```

The only operational reader is `journal_flush_serial()` which:
- Scans forward from `g_write_pos` (oldest data)
- Validates entries (level 0-4, msg_len 0-255)
- Prints to serial console: `[JOURNAL] [LEVEL] ts=Ns hash=0xHHHHHHHH msg`
- Caps output at 64 entries
- Called periodically by GENSD main loop (30s interval)

### 3.4 Persistent Storage

**NONE.** The entire journal is in volatile BSS memory. All journal data is lost
on any reboot, crash, or power loss. There is no flush-to-disk hook.

### 3.5 Cross-Subsystem Usage

Only GENSD's own `supervisor.c` and `main.c` call `journal_write()`.
No other subsystem (XSEC, XNET, XPKG, XSTORE, XMIND, XSHELL, etc.) uses it.
All other subsystems use raw `pal_console_printf()` which bypasses the journal entirely.

---

## 4. GAP REGISTRY

### P0 Gaps (Critical -- must fix)

| ID | Gap | Impact | Recommended Fix |
|----|-----|--------|-----------------|
| OBN-TCP-01 | TCP (1,341 LOC) entirely DARK | Connection errors, RST floods, retransmit storms, SYN attacks -- all invisible. Network debugging impossible. | Add xsec_audit_log for: RST received, connection refused, retransmit exhaustion (5 retry limit), SYN_RCVD overflow, keepalive timeout |
| OBN-XSTORE-02 | XSTORE+XBLOB (~2,900 LOC) entirely DARK | WAL corruption, B+ tree corruption, checkpoint failures, OCC conflicts -- all undetectable. Crash recovery diagnostics impossible. | Add pal_console_printf for: superblock CRC fail, WAL CRC skip, checkpoint write fail, cache eviction. Add xsec_audit_log for corruption events. |
| OBN-ROUTE-03 | XSEC audit ring -> GENSD journal routing missing | 38 security audit events are write-only with no consumer. Ring wraps in ~10s under load. All audit data lost. | Implement bridge: gensd supervisor polls xsec_audit_query_recent() every 5s, forwards entries to journal_write() with appropriate level mapping |

### P1 Gaps (High -- should fix)

| ID | Gap | Impact | Recommended Fix |
|----|-----|--------|-----------------|
| OBN-MVCC-04 | btree_lookup failure in txn_commit silently swallowed (mvcc.c:220-226) | WAL INSERT with val_len=0 -> crash recovery replays empty values -> silent data loss | Add pal_console_printf("[XSTORE] WARN: btree_lookup failed during WAL commit for key len=%u", we->key_len) |
| OBN-XJIT-05 | XJIT (1,817 LOC) entirely DARK | JIT compilation failures, register allocation errors, code generation bugs -- all invisible | Add pal_console_printf for: IR lowering failure, regalloc spill, codegen encoding error |
| OBN-JOURNAL-06 | journal_read_recent() is a stub | Journal data cannot be queried at runtime -- only serial dump | Implement forward scan from g_write_pos with entry validation and snapshot copy to caller buffer |
| OBN-RING-07 | Audit ring no persistent storage hook | 1024-entry ring wraps in ~10s at 100 events/sec. Historical audit data permanently lost. | Add periodic flush callback: xsec_audit_flush_to_store(xstore_t *) writes ring to XSTORE key-value pairs |
| OBN-STATS-08 | XSTORE stats struct exists but no consumer | cache_hits, cache_misses, cache_evictions tracked but never exposed | Wire xstore_stats() into XORCHESTRA health or periodic console dump |

### P2 Gaps (Medium -- should improve)

| ID | Gap | Impact | Recommended Fix |
|----|-----|--------|-----------------|
| OBN-STRUCT-09 | All Sprint 4-9 logging is unstructured pal_console_printf | Cannot query, filter, aggregate, or correlate. No timestamps embedded. | Define KLOG(subsys, level, msg) macro that calls journal_write() after journal_init() |
| OBN-BOOT-10 | boot_chain.c uses pal_console_printf not journal_write | Boot events not captured in journal ring | After Stage 0 (kernel_ready), switch to journal_write() for subsequent stages |
| OBN-DNS-11 | DNS query/response not logged | DNS resolution failures silent (only 1 truncation warning exists) | Add pal_console_printf for: query sent, response received, NXDOMAIN, timeout |
| OBN-HKDF-12 | HKDF key derivation not audited | TLS key material derivation steps invisible | Add xsec_audit_log for HKDF-Expand failures (unlikely but security-critical) |
| OBN-XMIND-13 | No inference metrics (tokens/sec, latency, KV cache fill) | Cannot monitor AI performance or detect degradation | Add token generation counter and timing around transformer_forward() |
| OBN-SEQNO-14 | No per-entry sequence number in audit ring | Cannot detect out-of-order delivery or detect missing entries | Add monotonic seq_id field to xsec_audit_entry_t |
| OBN-SYSLOG-15 | GENSD journal not used by any subsystem except GENSD itself | Journal infrastructure wasted -- all subsystems bypass it | Export journal_write() declaration in a shared header; add calls in XNET, XSTORE, XMIND |

---

## 5. OBSERVABILITY MATURITY SCORES

### Per-Subsystem (0=no visibility, 5=distributed trace)

| Subsystem | Sprint | Score | Change vs Prior | Rationale |
|-----------|--------|-------|-----------------|-----------|
| XSEC audit ring | S3 | 3/5 | = | Lock-free ring, typed events, query API. No persistence, no routing, no priority tiers |
| XSEC TLS 1.3 | S3 | 4/5 | +1 | 20 audit calls, 83% security path coverage. No perf metrics or trace context |
| XSEC X.509 | S3 | 4/5 | = | 100% rejection+success paths audited. No certificate chain metrics |
| XSEC crypto | S3 | 2/5 | +2 | KEY_GENERATED + DECRYPT_FAIL now wired. No HKDF audit, no key lifecycle metrics |
| XNET TCP | S3 | 0/5 | = | COMPLETELY DARK. 1,341 LOC zero logging. |
| XNET DNS | S3 | 0/5 | = | Only 1 truncation warning. No query/response logging. |
| XNET netif | S3 | 3/5 | = | Atomic counters (rx/tx/error/dropped). No threshold alerts, no exposure API |
| XPKG gate | S3 | 2/5 | +2 | PKG_GATE_FAIL + FORCED wired. PASS outcomes not logged. No per-gate metrics |
| GENSD journal | S1 | 2/5 | = | Ring works, write API functional. Reader stub. No persistence. No routing |
| XSTORE | S4 | 0/5 | NEW | COMPLETELY DARK. Zero logging in 2,100 LOC. stats struct unused |
| XBLOB | S4 | 0/5 | NEW | COMPLETELY DARK. Zero logging in ~800 LOC |
| XSHELL | S5 | 1/5 | NEW | pal_console_printf lifecycle only. No error tracking |
| Orange Suite | S5 | 1/5 | NEW | 4 pal_console_printf. Effectively dark for errors |
| XORCHESTRA | S5 | 1/5 | NEW | Health probe console output. No journal routing |
| XMIND | S6 | 1/5 | NEW | Init/OOM logging. No inference metrics |
| XJIT | S6 | 0/5 | NEW | COMPLETELY DARK in compilation. Stats dump only |
| XBUILD | S7 | 1/5 | NEW | DAG operations logged. No structured output |
| XEMU | S7 | 1/5 | NEW | ELF/insn logging. No structured output |
| Boot Chain | S8 | 2/5 | NEW | 47 console logs + result struct. Not journal-routed |
| Kernel drivers | S8-9 | 1/5 | NEW | Diagnostic dump functions. No runtime events |

### Platform Summary

| Metric | Count |
|--------|-------|
| Total subsystems audited | 20 |
| Subsystems with xsec_audit_log | 4 (XSEC TLS, X.509, crypto, XPKG gate) |
| Subsystems completely DARK | 5 (TCP, DNS, XSTORE, XBLOB, XJIT) |
| Subsystems with structured logging | 0 |
| Subsystems with queryable metrics | 0 |
| Subsystems with distributed tracing | 0 |
| Production xsec_audit_log call sites | 38 (36 in sec/, 2 in pkg/) |
| Active audit event types | 11/11 |
| journal_write consumers | 1 (GENSD only) |
| pal_console_printf calls (approx) | ~200+ across platform |

### Overall Platform Maturity: **Level 1 -- Minimal**

Level 0: No visibility
**Level 1: Fatal-only visibility in some subsystems** <-- GEN.OS is here
Level 2: Error visibility across most subsystems
Level 3: Lifecycle events and structured logging
Level 4: Metrics collection and exposure
Level 5: Distributed tracing with correlation IDs

---

## 6. PRODUCTION xsec_audit_log CALL SITES (38 total)

| File | Event Type | Count |
|------|-----------|-------|
| tls13.c | HANDSHAKE_FAILED | 13 |
| tls13.c | HANDSHAKE_COMPLETE | 1 |
| tls13.c | SESSION_CLOSED | 1 |
| tls13.c | TLS_ALERT_RECV | 1 |
| tls13.c | AUTH_TAG_MISMATCH | 1 |
| tls13.c | CERT_REJECTED | 3 |
| x509.c | CERT_REJECTED | 11 |
| x509.c | CERT_VERIFIED | 1 |
| x25519.c | KEY_GENERATED | 1 |
| ed25519.c | KEY_GENERATED | 1 |
| aes_gcm.c | DECRYPT_FAIL | 1 |
| chacha20.c | DECRYPT_FAIL | 1 |
| refusal_gate.c | PKG_GATE_FORCED | 1 |
| refusal_gate.c | PKG_GATE_FAIL | 1 |
| **Total** | | **38** |

---

## 7. RECOMMENDATIONS (Priority Ordered)

### Immediate (P0):
1. Add minimum 5 xsec_audit_log calls in tcp.c (RST, conn_refused, retransmit_exhausted, SYN_flood, keepalive_fail)
2. Add pal_console_printf in xstore WAL/checkpoint/corruption error paths (~8 sites)
3. Implement GENSD supervisor audit ring bridge (poll every 5s, forward to journal)

### Short-term (P1):
4. Add pal_console_printf on mvcc.c:220 btree_lookup failure path
5. Add compilation failure logging in XJIT codegen
6. Implement journal_read_recent() forward scan reader
7. Design audit ring overflow notification / persistent flush

### Medium-term (P2):
8. Define KLOG() macro for kernel subsystem structured logging
9. Expose XSTORE stats via XORCHESTRA health endpoint
10. Add inference timing metrics to XMIND transformer
11. Route boot_chain events to journal after journal_init()
