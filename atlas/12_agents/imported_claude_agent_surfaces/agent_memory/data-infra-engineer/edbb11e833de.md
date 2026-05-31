# Sprint 21 P2 Fixes + CI — 2026-03-07

## Files Modified

### store/xstore/wal/wal.c — P2-S20-WAL-01-FIXED
- **Root cause**: `committed_count < WAL_REPLAY_MAX_TXNS` guard in Phase 1 of
  `xstore_wal_replay()` silently discarded COMMIT records once the 256-entry
  array was full.  Transactions 257+ were not replayed; function returned
  `XSTORE_OK` with data loss.
- **Fix**: Added `committed_count >= WAL_REPLAY_MAX_TXNS` check that emits a
  `pal_console_puts()` diagnostic and returns `XSTORE_ERR_REPLAY_OVERFLOW`.
- **New error code**: `XSTORE_ERR_REPLAY_OVERFLOW = -15` added to `xstore.h`.
- **Variable used**: `committed_count` (the loop-local counter) — NOT `n_txns`
  (that was the task description's placeholder name only).
- Compile check: exit 0, zero warnings.

### sec/xsec/audit/audit.c — P2-S20-AUDIT-01-FIXED
### sec/xsec/include/xsec.h — struct extension + new getter

- **Root cause**: `xsec_audit_log()` incremented `dropped_events` whenever
  `write_idx >= XSEC_AUDIT_RING_SIZE`.  Since `write_idx` is monotonically
  increasing, this condition is true for EVERY write after the first 1024
  events — i.e., on every normal ring rotation.  `dropped_events` grew
  unboundedly on normal operation, making it useless as an alert metric.
- **Fix**:
  1. Added `volatile uint64_t ring_overwrites` field to `xsec_audit_ctx_t`
     in `xsec.h`.
  2. In `audit.c` write path: changed `pal_atomic_add(&xsec_g_audit.dropped_events, 1u)`
     to `pal_atomic_add(&xsec_g_audit.ring_overwrites, 1u)`.
  3. `xsec_audit_init()` now zeroes `ring_overwrites`.
  4. `xsec_audit_dump()` reports `ring_overwrites` as "Ring overwrites (normal
     rotation)" and `dropped_events` as "WARNING: events truly dropped
     (consumer fell behind)" — clearly distinguishing the two semantics.
  5. Added `uint64_t xsec_audit_get_ring_overwrites(void)` getter declared in
     `xsec.h` and implemented in `audit.c`.
  6. `dropped_events` is kept at zero (reserved for a future consumer-index
     flow) — no callers break.
- Compile check: exit 0, zero warnings.

## Files Created

### .github/workflows/sprint21.yml
- 4 jobs + gate (5 total, same pattern as sprint20.yml):
  1. `sprint21-security-fixes` (15m): KASLR marker, x509 compile + CERT-01
     marker check, xkabi compile + race marker check.
  2. `sprint21-storage-audit` (10m): wal.c + audit.c compile + fix marker
     verification + cppcheck on both.
  3. `sprint21-full-compile` (20m): All 5 S21 sources freestanding (x509 tries
     cert/ then pki/ path).
  4. `sprint21-libc-scan` (5m): grep-based libc symbol scan.
  5. `sprint21-gate`: summary echo.
- SHA-pinned checkout `@11bd71901bbe5b1630ceea73d27597364c9af683`
- `permissions: contents: read`

### docs/adr/ADR-S21-01-X509-DN-FIELD-ISOLATION.md
- Covers P1-S3-CERT-04: hostname validation scanned formatted DN string.
- Decision: add `cn_start`/`cn_len` to `x509_cert_t`; populate at DER decode;
  validate against dedicated field in `xsec_x509_verify_hostname()`.
- Multi-CN: last CN in DER sequence wins (RFC 6125 most-specific).
- Struct grows 8 bytes; chain pool grows 64 bytes total — negligible.

## Key Lessons

- WAL_REPLAY_MAX_TXNS cap: the variable name in the task description (`n_txns`)
  does NOT match the actual code variable (`committed_count`) — always read the
  source before writing the fix.
- Monotonically-increasing write_idx vs ring slot index: `write_idx >= RING_SIZE`
  is true on EVERY write after the first full rotation; it is NOT an overflow
  signal.  Only a consumer-index scheme can detect genuine read-side loss.
- `pal_atomic_add` inside a spinlock: redundant but harmless — the spinlock
  already provides mutual exclusion; the atomic is there for future lockless
  readers in dump path.
