# Sprint 4 XSTORE + XBLOB Data Infrastructure Audit
# Date: 2026-03-06
# Auditor: Data Infrastructure Engineer
# Commit scope: store/xstore/ + store/xblob/

---

## SMOKE TEST (Mandatory Test Type 1)

### File Existence — All 11 Required Files Present

| File | Present | Task Prefix |
|------|---------|-------------|
| store/xstore/btree/btree.c | YES | S4-STR-01 |
| store/xstore/wal/wal.c | YES | S4-STR-02 |
| store/xstore/txn/mvcc.c | YES | S4-STR-03 |
| store/xstore/io/page_cache.c | YES | S4-STR-04 |
| store/xstore/xstore.c | YES | S4-STR-05 |
| store/xstore/include/xstore.h | YES | S4-STR-00 |
| store/xblob/blob.c | YES | S4-BLB-03 |
| store/xblob/index.c | YES | S4-BLB-01 |
| store/xblob/gc.c | YES | S4-BLB-02 |
| store/xblob/xblob.c | YES | S4-BLB-04 |
| store/xblob/include/xblob.h | YES | S4-BLB-00 |

RESULT: 11/11 PASS. All files present.

### Compile Flags
- All files declare `#define PAL_FREESTANDING` before including their master header.
- All files use `#include "xstore.h"` / `#include "xblob.h"` (not system headers).
- `__attribute__((packed))` used on all on-disk structs.
- `__attribute__((unused))` used on intentionally unused internal statics.
- Compatible with: `clang -target x86_64-unknown-none-elf -ffreestanding -Werror`

RESULT: PASS

---

## REGRESSION TEST — _Static_assert Verification (Test Type 4)

### xstore_wal_entry_t (xstore.h:204)

Field-by-field byte count:
- lsn: 8
- txn_id: 8
- page_no: 4
- op: 1
- key_len: 1
- val_len: 2
- checksum: 4
- _pad: 4
- key[XSTORE_MAX_KEY_LEN=256]: 256
- val[XSTORE_MAX_VAL_LEN=4096]: 4096

TOTAL: 8+8+4+1+1+2+4+4+256+4096 = **4384 bytes**

The _Static_assert expression on line 204-206 evaluates identically:
`(8 + 8 + 4 + 1 + 1 + 2 + 4 + 4 + XSTORE_MAX_KEY_LEN + XSTORE_MAX_VAL_LEN)` = 4384

The comment in the header (§6) claims "fixed-size 128-byte records" — this is WRONG. Entries
are 4384 bytes. The 128-byte comment is a documentation error left over from an earlier design
that was superseded when MAX_VAL_LEN=4096 was chosen. The _Static_assert is correct; the
comment is incorrect. Filed as P2-DOC-01.

### xstore_page_hdr_t (xstore.h:119)
- magic(4) + checksum(4) + page_no(4) + page_type(1) + flags(1) + level(2) + num_keys(4)
  + parent_page(4) + lsn(8) = 32 bytes
- _Static_assert: `sizeof(xstore_page_hdr_t) == 32` — CORRECT

### xstore_superblock_t (xstore.h:142)
- xstore_page_hdr_t(32) + format_version(4) + root_page(4) + free_list_head(4)
  + total_pages(4) + next_txn_id(8) + checkpoint_lsn(8) + wal_head(8) + num_keys(8)
  + _reserved[4016](4016) = 32+4+4+4+4+8+8+8+8+4016 = 4096 bytes
- _Static_assert: `sizeof(xstore_superblock_t) == 4096` — CORRECT

### xblob_hdr_t (xblob.h:114)
- magic(4) + format_version(4) + hash[32] + data_len(4) + checksum(4) + stored_at_ns(8)
  + ref_count(2) + _reserved[6] = 4+4+32+4+4+8+2+6 = **64 bytes**
- _Static_assert: `sizeof(xblob_hdr_t) == 64` — CORRECT

### xblob_index_entry_t (xblob.h:144)
- state(1) + _pad[3] + ref_count(4) + hash[32] + blob_offset(8) + blob_len(4) + crc(4)
  = 1+3+4+32+8+4+4 = **56 bytes**
- _Static_assert: `sizeof(xblob_index_entry_t) == 56` — CORRECT

### xblob_gc_log_entry_t (xblob.h:182)
- seq(8) + op(1) + _pad[3] + hash[32] + new_refcount(2) + _pad2[6] + checksum(4)
  = 8+1+3+32+2+6+4 = **56 bytes**
- _Static_assert: `sizeof(xblob_gc_log_entry_t) == 56` — CORRECT

### xstore_leaf_slot_t (btree.c:115)
- key_len(2) + val_len(2) + rec_off(2) + lsn_hi(2) = 8 bytes
- _Static_assert vs XSTORE_LEAF_SLOT_ENTRY_SIZE(8) — CORRECT

### xstore_int_slot_t (btree.c:125)
- key_len(2) + _pad(2) + right_child(4) = 8 bytes
- _Static_assert: `sizeof(xstore_int_slot_t) == 8` — CORRECT

RESULT: All _Static_asserts correct. One documentation error in §6 header comment (P2).

---

## LOAD TEST — WAL Ring Saturation Analysis (Test Type 5)

### WAL Ring Geometry
- Entry size: 4384 bytes (verified above)
- Ring capacity: 65536 entries
- Total WAL buffer: 65536 × 4384 = 287,309,824 bytes = ~274 MB

FINDING P1-WAL-01: The WAL buffer requirement of ~274 MB is a LARGE caller-provided
allocation. The header comment on XSTORE_WAL_BUF_SIZE is correct, but no caller documentation
warns that this is a 274 MB requirement. On the HP EliteBook x360 with 16 GB RAM, this is
3.4% of physical RAM. If this is a static or stack allocation, it will overflow immediately.
Caller must use PAL DMA pages or equivalent physically-contiguous mapped region.

### WAL Ring Saturation Behavior
- Saturation check: `(store->wal_head - store->wal_tail) >= XSTORE_WAL_RING_SIZE` (wal.c:66)
- On full: returns XSTORE_ERR_WAL_FULL (correct)
- xstore_txn_commit() auto-checkpoints once and retries (mvcc.c:209-215) — CORRECT
- XSTORE_ERR_WAL_FULL is defined and documented in xstore.h — CORRECT

### Saturation Scenario
- 65536 WAL entries at 4384 bytes each
- At 512 writes/txn × 1 COMMIT = 513 entries per txn
- Ring saturates after ~127 concurrent uncommitted transactions
- With 64-entry inflight txn limit (XSTORE_MAX_TXN_INFLIGHT), saturation requires many
  large write sets before checkpoint — realistic but possible under XPKG bulk installs

RESULT: WAL saturation handling is correct. Buffer size requirement needs caller documentation.

---

## STRESS TEST — MVCC Conflict Storm (Test Type 6)

### Scenario: 64 Concurrent Conflicting Transactions

FINDING P0-MVCC-01 (CRITICAL): FALSE PAGE-LEVEL CONFLICT GRANULARITY

In mvcc.c:281-282, xstore_txn_put() records `we->page_no = store->sb.root_page` for
ALL writes, regardless of which leaf page actually holds the key.

This means the conflict check in xstore_mvcc_conflict_check() (mvcc.c:160-166) compares
the root page's last_write_lsn against snapshot_lsn for every write in every transaction.
The root page is touched by every split and insert. This causes:

1. FALSE POSITIVES: Two transactions writing to entirely different leaf subtrees will
   conflict if any write has occurred since their snapshot (because both record root_page
   as the target). At 64 concurrent transactions, the false conflict rate approaches 100%.

2. RETRY STORM: xstore_put() retries up to 3 times. With all 64 txns colliding on root_page,
   all 64 will get XSTORE_ERR_CONFLICT on every attempt until only one succeeds.

3. STARVATION: Under sustained write concurrency, transactions that write to completely
   disjoint key ranges will repeatedly conflict. No forward progress is guaranteed.

The code comment on mvcc.c:281 acknowledges this: "we store the superblock root_page as
a conservative conflict target". This is intentionally conservative for Sprint 4, but at
64-txn concurrency it makes OCC effectively equivalent to a single global write lock.

SEVERITY: P0 for concurrent write scenarios. Acceptable for the stated Sprint 4 single-writer
provenance use case, but MUST be addressed before Sprint 5 multi-threaded workloads.

FIX REQUIRED: btree_insert must return the actual leaf page_no that was modified, and
txn_put must record that page_no in the write_set entry, not root_page.

### MVCC Shadow Table Collision Analysis

FINDING P1-MVCC-02: MVCC SHADOW TABLE CATASTROPHIC OVERFLOW AT SCALE

The shadow table has MVCC_PAGE_TABLE_SIZE = 8192 slots for a store that supports up to
XSTORE_MAX_PAGES = 1M pages.

Load factor analysis:
- At 1M pages: load factor = 1,000,000 / 8192 = 122.07
- Linear probe collision chain at 122x load: the table will be 100% full long before 1M pages
- When the table is full, mvcc_record_write() silently drops the write record (no error,
  no eviction fallback). The inner loop breaks at the end without recording.
- mvcc_query_write() stops early at the first empty slot (line 98: `if (e->page_no == 0) break`)
  — with a 122x-loaded table, every probe chain is unbroken and dense, so this will rarely
  terminate early. But correctness still depends on finding the target entry.

For Sprint 4 workloads (XPKG install state, provenance) with page counts in the hundreds,
the 8192-slot table is adequate. At thousands of pages it degrades. At tens of thousands
it becomes unreliable.

SEVERITY: P1 — Safe for Sprint 4 scope, but the 8192-slot ceiling must be raised before
XSTORE hosts the full provenance + AI context store at scale.

### MVCC Static Global State — Multi-Store Violation

FINDING P2-MVCC-03: g_mvcc_table IS A STATIC GLOBAL (mvcc.c:66-68)

```c
static mvcc_page_entry_t g_mvcc_table[MVCC_PAGE_TABLE_SIZE];
static pal_spinlock_t    g_mvcc_lock = PAL_SPINLOCK_INIT;
static bool              g_mvcc_initialized = false;
```

The comment at mvcc.c:65 says "For Sprint 4 (single store), static is correct and
zero-overhead." This is true, but the consequence is that opening two xstore_t instances
in the same address space (e.g., provenance DB + XPKG DB) will share the same MVCC table.
Their page numbers will collide. This is a latent multi-store bug.

SEVERITY: P2 — single-store Sprint 4 is safe. Must be converted to per-store embedded
struct before Sprint 5.

---

## SECURITY TEST — WAL Checksum Coverage (Test Type 7)

### xstore_wal_crc() Coverage Analysis

From wal.c:47-53 and xstore.h:562:
```c
uint32_t xstore_wal_crc(const xstore_wal_entry_t *e) {
    const uint8_t *p = (const uint8_t *)e;
    return xstore_crc32c(p + 16, sizeof(xstore_wal_entry_t) - 16);
}
```

Bytes [0, 16) = lsn(8) + txn_id(8) — EXCLUDED from CRC
Bytes [16, 4384) = page_no(4) + op(1) + key_len(1) + val_len(2) + checksum(4) + _pad(4)
                   + key[256] + val[4096] — INCLUDED in CRC

FINDING P1-SEC-01: WAL CRC COVERS ITS OWN CHECKSUM FIELD

The checksum field occupies bytes 16–19 within xstore_wal_entry_t, which is inside the
CRC coverage window [16, 4384). This creates a circular dependency in principle.

The implementation resolves this correctly: in xstore_wal_append() (wal.c:78-79):
```c
dst->checksum = 0;
dst->checksum = xstore_wal_crc(dst);
```
The checksum is zeroed before CRC computation, so the CRC function always sees checksum=0
at bytes 16–19. This makes the CRC deterministic and stable. The design is correct.

However, the WAL replay in wal.c:117-118 recomputes and compares without zeroing first:
```c
uint32_t expected_crc = xstore_wal_crc(e);
if (e->checksum != expected_crc) continue;
```
This works only because the stored entry has checksum = CRC(entry_with_checksum=0).
When replay calls xstore_wal_crc(e) on the stored entry, it computes
CRC(entry_with_checksum=STORED_VALUE). This will NOT match the stored checksum.

FINDING P0-SEC-02 (CRITICAL): WAL REPLAY CRC VERIFICATION IS ALWAYS WRONG

The CRC written to disk is computed with checksum=0. The CRC verified during replay is
computed with checksum=STORED_VALUE (non-zero). These will never match unless the stored
checksum happens to be zero.

Proof:
- At write: crc = CRC(data || 0x00000000 || key || val)
- At replay: crc = CRC(data || STORED_CRC || key || val)
- These are equal only if STORED_CRC == 0 (i.e., the actual CRC happens to be zero).

This means: every WAL entry's checksum verification in wal_replay() will FAIL. The
`continue` on mismatch causes ALL entries to be skipped. Crash recovery does nothing.
The store will silently present stale data after a crash.

SEVERITY: P0 — This is a complete crash-safety failure. The WAL replay mechanism is
non-functional as written.

FIX: Either (a) zero the checksum field before calling xstore_wal_crc() during replay,
then compare; or (b) exclude the checksum field from coverage (cover [20, 4384) instead
of [16, 4384)). Option (b) is the canonical WAL design used by PostgreSQL and SQLite.

FINDING P2-SEC-03: LSN AND TXN_ID EXCLUDED FROM WAL CRC

Bytes [0,16) — lsn and txn_id — are excluded from the CRC. An attacker with physical
access who can modify WAL ring entries in memory could:
- Change the txn_id to associate a malicious txn's entries with a legitimate commit
- Change the lsn to alter replay ordering

For an embedded local-device OS with physical security, this is an acceptable trade-off
(WAL is in RAM — if an attacker has RAM access, all security is lost). Acceptable for
GEN.OS threat model but worth documenting.

SEVERITY: P2 — Acceptable for local-device threat model.

---

## FUZZ TEST — WAL Replay Corruption Detection (Test Type 9)

### Corrupted Entry Handling in xstore_wal_replay()

Phase 1 (commit collection), wal.c:111-125:
- `if (e->lsn != lsn) continue` — handles epoch/stale slot correctly
- `if (e->checksum != expected_crc) continue` — see P0-SEC-02 above; broken

Phase 2 (replay), wal.c:128-166:
- Same two guards as Phase 1
- On corrupted op value (not INSERT/DELETE): `continue` — safe
- On zero key_len (impossible per validation but possible in fuzz): btree_insert will
  receive key.len=0 and return XSTORE_ERR_INVAL — result is (void), so ignored safely

FINDING P2-FUZZ-01: REPLAY IGNORES BTREE ERRORS SILENTLY

In wal.c:162 and 165:
```c
(void)xstore_btree_insert(store, &rec_txn, &key, &val);
(void)xstore_btree_delete(store, &rec_txn, &key);
```

Errors are discarded with "Best-effort replay — ignore errors (page may already be
up-to-date)". This is a reasonable idempotency strategy BUT there is no distinction
between "already up-to-date" (XSTORE_ERR_EXISTS, expected) and "page is corrupt"
(XSTORE_ERR_CORRUPT, critical). A corrupt page during replay proceeds silently.

SEVERITY: P2 — During normal crash recovery this is fine. Under adversarial or hardware-
fault conditions, corruption propagates silently.

### WAL Replay Committed Txn Table Overflow

FINDING P1-FUZZ-02: WAL REPLAY SILENTLY DROPS COMMITS BEYOND SLOT 256

In wal.c:96: `#define WAL_REPLAY_MAX_TXNS 256U`

The ring has 65536 entries. If more than 256 distinct txn_ids committed between the
last checkpoint and crash, commits 257+ are silently dropped from the committed_txns[]
array (line 121 silently skips when count >= 256). Their data entries will not be
replayed. This is data loss.

Probability: Low in single-user interactive workload (XPKG, provenance). High during
a bulk package install (xpkg install with 1000 packages, each a txn). The ring holds
65536 / ~513 entries-per-txn = ~127 txns before saturation, so auto-checkpoint usually
triggers. But a crash between 256 and 127*513 entries can lose commits.

SEVERITY: P1 — must increase WAL_REPLAY_MAX_TXNS to match WAL_RING_SIZE, or use a
hash set / dynamically sized structure.

---

## RELIABILITY TEST — Crash Recovery Protocol Completeness (Test Type 10)

### Open Sequence (xstore.c:36-139)

1. Zero store context — CORRECT
2. Wire I/O callbacks — CORRECT
3. Wire WAL ring (wal_head=0, wal_tail=0, next_lsn=1) — CORRECT
4. Init page cache — CORRECT
5. Init spinlocks — CORRECT
6. Read superblock page 0 — CORRECT
   - On existing store: validate CRC, load state from superblock
   - Restore next_txn_id = sb.next_txn_id + 1
   - Restore next_lsn = sb.checkpoint_lsn + 1
   - Restore wal_head = sb.wal_head
   - Restore wal_tail = sb.checkpoint_lsn (note: wal_tail is an LSN, not an entry count)
7. Run WAL replay — BROKEN (see P0-SEC-02)
8. Mark store open — CORRECT

FINDING P1-REL-01: WAL_TAIL vs WAL_HEAD UNIT MISMATCH

At xstore.c:90-91:
```c
store->wal_head = store->sb.wal_head;   // sb.wal_head is a ring write index (count)
store->wal_tail = store->sb.checkpoint_lsn; // checkpoint_lsn is an LSN
```

In xstore_t, wal_head and wal_tail are both `uint64_t`. The saturation check in wal.c:66
is `(store->wal_head - store->wal_tail) >= XSTORE_WAL_RING_SIZE`.

If wal_head is a monotonic write-index count and wal_tail is restored from checkpoint_lsn
(which is the LSN of the last checkpoint entry, not the count of entries), the difference
will be calculated incorrectly on the first WAL append after a crash recovery.

The WAL checkpoint sets `store->sb.wal_head = store->wal_head` (wal.c:204), so wal_head in
the superblock IS the write-index count. But `wal_tail` is restored from `checkpoint_lsn`
(an LSN value), and after checkpoint, wal_tail is set to `checkpoint_lsn + 1` (wal.c:222).

These are aligned only if LSN increments at exactly the same rate as wal_head increments.
In xstore_wal_append(), both `lsn = pal_atomic_add(&store->next_lsn, 1)` and
`store->wal_head++` happen in the same call — so they are in sync. This works correctly
as long as next_lsn and wal_head start at the same value, which they do (both restored
from checkpoint). This is correct but extremely fragile — the invariant is invisible.

SEVERITY: P2 — Currently correct but requires tight invariant maintenance. Should be
documented explicitly with a SAFETY comment.

### WAL Checkpoint Sequence (wal.c:180-225)

1. Flush dirty pages (xstore_cache_flush) — CORRECT
2. Append CHECKPOINT WAL entry — CORRECT
3. Compute checkpoint_lsn = store->next_lsn - 1 — CORRECT
4. Update superblock fields — CORRECT
5. Compute superblock CRC over bytes [8, PAGE_SIZE) — CORRECT (matches page_hdr definition)
6. Write superblock to page 0 — CORRECT
7. Call sync() — CORRECT
8. Advance wal_tail under wal_lock — CORRECT

FINDING P2-REL-02: PAGE CHECKSUM UPDATED AT FLUSH, NOT AT WAL APPEND

In page_cache.c:234-235, page checksums are computed at flush time:
```c
hdr->checksum = xstore_crc32c(e->data + 8, XSTORE_PAGE_SIZE - 8);
```

If a dirty page is evicted before checkpoint (page_cache.c:113-118), it is written to
the backing store WITHOUT a checksum update (the eviction path calls write_page directly
without recomputing the checksum). The on-disk page will have a stale/zero checksum.

This means page integrity verification during a non-checkpoint read path would see a
checksum mismatch for recently evicted dirty pages. If xstore_open() verifies page
checksums before WAL replay, it may reject valid pages as corrupt.

In practice, xstore_open() only verifies the superblock checksum, not leaf pages. But
future Sprint 5 page-level integrity checks would be broken.

SEVERITY: P2 — Does not cause data loss now. Must be fixed before page-level integrity
verification is added.

---

## FUNCTIONAL TEST — xstore_put() Full Call Chain (Test Type 2)

### xstore_put() → xstore_txn_begin() → xstore_txn_put() → xstore_btree_insert() → xstore_wal_append()

1. xstore_put() (xstore.c:171): validates args, calls xstore_txn_begin()
2. xstore_txn_begin() (mvcc.c:131): assigns txn_id via store->next_txn_id++, captures
   snapshot_lsn = store->next_lsn, sets active=true
3. xstore_txn_put() (mvcc.c:261): validates, calls xstore_btree_insert(), then records
   write_set entry with page_no=root_page (see P0-MVCC-01)
4. xstore_btree_insert() (btree.c:525): traverses tree, calls xstore_cache_get() at each
   level, calls _leaf_insert_at() or triggers _leaf_split(), marks pages dirty via
   xstore_cache_mark_dirty()
5. xstore_txn_commit() (mvcc.c:179): OCC check → wal_append for each write → wal_append
   COMMIT → mvcc_record_write for each page
6. xstore_wal_append() (wal.c:59): saturation check, atomic LSN assign, copy entry,
   zero checksum, compute CRC, increment wal_head

FINDING P1-FUNC-01: VALUE NOT WRITTEN TO WAL AT COMMIT

In mvcc.c:205: `entry.val_len = 0; /* val is already applied to B+ tree pages */`

The WAL COMMIT path appends only the key (and page_no, op) — not the value. If the page
cache is evicted BEFORE a checkpoint, the value is lost from the backing store. The WAL
does not have enough information to reconstruct the value during replay.

This is explicitly a redo-only WAL that relies on pages being durable. But the page is
only made durable during checkpoint (or dirty eviction). Between txn commit and checkpoint,
the value exists only in the page cache. A crash in this window would lose the write
despite the WAL COMMIT record being present.

The crash recovery path in WAL replay (wal.c:157-163) tries to replay INSERT entries — but
the val_len=0 means the replayed val is empty. This would insert a zero-length value over
the original.

This is a fundamental architectural gap: a redo-only WAL MUST contain the full post-image
(key + value) to be crash-safe without relying on the page store being ahead of the WAL.

SEVERITY: P1 — Crash between commit and checkpoint causes data loss (value replaced with
empty value on recovery).

FIX: WAL INSERT entries must include val_len and val payload, or the page write must be
synchronous before xstore_txn_commit() returns XSTORE_OK.

### Leaf Cursor Advance (btree.c:755-787)

FINDING P2-FUNC-02: CURSOR ADVANCE STOPS AT PAGE BOUNDARY

btree_cursor_advance() (btree.c:780-786) sets cursor->valid=false and returns
XSTORE_ERR_NOT_FOUND when the cursor reaches the end of a leaf page, even if more pages
exist. The comment says "Sprint 5 adds leaf chaining."

This means range scans are broken for key ranges that span more than one leaf page.
The cursor terminates at the first page boundary. This is a known limitation but is not
flagged anywhere in the public API documentation.

SEVERITY: P2 — Range scans over large key spaces are silently truncated.

---

## INTEGRATION TEST — XBLOB SHA-256 / XSEC Integration (Test Type 3)

### SHA-256 Source Verification

FINDING: XBLOB CORRECTLY USES PAL SHA-256 (NOT A DUPLICATE IMPLEMENTATION)

In blob.c:26-28 comment and blob.c:93:
```c
pal_status_t prc = pal_sha256(data, len, hash);   // xblob_put
pal_status_t prc = pal_sha256(out_buf, blob_len, computed_hash);  // xblob_get
```

XBLOB does NOT have its own SHA-256 implementation. It calls `pal_sha256()` from `pal.h`,
which is the single authoritative FIPS 180-4 pure-C implementation in `pal_aether.c`.
This is the same function used by XSEC (Sprint 3). No deduplication or drift risk.

RESULT: XBLOB SHA-256 integration is CORRECT. Sprint 3 XSEC SHA-256 is the single source.

### xblob_get() Integrity Verification

In blob.c:230-236:
```c
pal_status_t prc = pal_sha256(out_buf, blob_len, computed_hash);
if (xblob_memcmp(computed_hash, hash, XBLOB_HASH_LEN) != 0)
    return XBLOB_ERR_CORRUPT;
```

Every get() recomputes the SHA-256 of retrieved data and compares to the requested hash.
Content-addressing integrity is enforced on every read. CORRECT.

### XBLOB Header Checksum vs SHA-256 Redundancy

The xblob_hdr_t stores a CRC32C `checksum` that covers `hash[] + data_len + blob data`.
The get() path does NOT verify this header checksum — it only verifies the full SHA-256
of the blob body. The header CRC is written at put() time but never read at get() time.

FINDING P2-INT-01: HEADER CRC IS WRITTEN BUT NEVER VERIFIED ON GET

The header checksum (xblob.h:108) covers hash+data_len+blob data. If the header itself is
corrupted (magic/format_version/ref_count/stored_at_ns), this is detected only by the
magic check (`if (hdr.magic != XBLOB_MAGIC)`). If data_len in the header diverges from
the index entry's blob_len, line 223 catches it. But the stored CRC32C field provides
defense-in-depth that is never used.

SEVERITY: P2 — Not a correctness bug, but wasted integrity protection.

---

## GC LOG CORRECTNESS ANALYSIS

### GC Log CRC Coverage

In gc.c:54: `e->checksum = xblob_crc32c((const uint8_t *)e, sizeof(*e) - 4);`
- sizeof(xblob_gc_log_entry_t) = 56 bytes
- Coverage: bytes [0, 52) = 52 bytes
- checksum is the last 4 bytes (bytes 52..55) — NOT included in CRC
- This is the canonical approach: CRC covers all fields except itself. CORRECT.

Header comment says "CRC32C of bytes [0, 52)" — matches implementation. CORRECT.

### GC Log Race Condition

FINDING P1-GC-01: DEADLOCK RISK — gc_log_append() CALLED WHILE HOLDING store_lock

In gc.c:138, xblob_gc_log_append() is called FROM WITHIN xblob_gc_scan() while holding
`blob->store_lock`:
```c
pal_spin_lock(&blob->store_lock);   // gc.c:118
...
xblob_gc_log_append(blob, ...);     // gc.c:138  <-- tries to acquire gc_lock
```

xblob_gc_log_append() acquires gc_lock (gc.c:43).

If any other code path acquires gc_lock then tries to acquire store_lock (the reverse order),
a deadlock occurs. Looking at all callers: blob.c:114, 185, 278, 302 all call
xblob_gc_log_append() AFTER releasing store_lock. gc.c:138 calls it while holding
store_lock.

Currently no code path acquires gc_lock then tries to acquire store_lock. But this is a
fragile ordering constraint that is not documented.

SEVERITY: P1 — Currently safe due to consistent lock ordering in non-GC paths, but
the GC scan breaks the ordering. Future additions that reverse the order will deadlock.

### GC Compaction Re-insertion Bug

FINDING P2-GC-02: COMPACTION CLEARS INDEX BEFORE RE-INSERTING — LOST ENTRIES ON PARTIAL FAILURE

In gc.c:176-196, compaction works as follows:
1. Copy OCCUPIED entry to `chunk[]`, then immediately set `blob->index[i].state = FREE`
2. When chunk is full or at end: re-insert all chunk entries

If xblob_index_insert() fails during re-insertion (XBLOB_ERR_INDEX_FULL or any error),
the already-cleared entries (state=FREE) are silently lost. The blob's storage slot is
still allocated (bitmap set), but the index entry is gone. The blob becomes a storage
leak with no way to free it.

SEVERITY: P2 — xblob_index_insert() should not fail during compaction (table was just
cleared, load factor is low). But any bug in insert logic would cause permanent leaks.

### GC Log Size — Stack Safety

GC log buffer: 16384 × 56 = 917,504 bytes = ~896 KB

This buffer is a caller-provided heap/DMA allocation (passed to xblob_open() as `gc_log_buf`).
It is NOT stack-allocated anywhere in gc.c or xblob.c. SAFE.

The compaction chunk buffer `xblob_index_entry_t chunk[GC_COMPACT_CHUNK]` where
GC_COMPACT_CHUNK=256 is stack-allocated at gc.c:169: 256 × 56 = 14,336 bytes = ~14 KB.
This IS stack-allocated. In freestanding environments, the default stack may be as small
as 4–8 KB. This stack allocation may overflow the kernel stack.

FINDING P1-GC-03: GC COMPACTION CHUNK IS A POTENTIALLY FATAL 14 KB STACK ALLOCATION

```c
xblob_index_entry_t chunk[GC_COMPACT_CHUNK];  // 256 * 56 = 14336 bytes on stack
```

In a freestanding kernel context (XENOS), the stack size depends on PAL thread creation.
If the kernel stack is ≤16 KB (common for OS kernel stacks), this allocation alone
consumes almost the entire stack frame. Combined with any nesting, this is a stack overflow.

SEVERITY: P1 — Must be converted to a static or caller-provided buffer.

---

## XBLOB INDEX CRC COVERAGE ANALYSIS

### index.c CRC Field Calculation

At insert (index.c:98-99):
```c
we->crc = xblob_crc32c((const uint8_t *)we + 8,
                        sizeof(xblob_index_entry_t) - 8 - 4);
```
Coverage: bytes [8, 56-8-4) = bytes [8, 44) = 36 bytes
- Byte 0: state (NOT covered)
- Bytes 1-3: _pad (NOT covered)
- Bytes 4-7: ref_count[0..3] — WAIT: ref_count starts at byte 4 (after state=1, _pad=3)
  - Actually: state(1)+_pad(3) = bytes 0..3, so ref_count(4) = bytes 4..7 — NOT covered
  - hash(32) = bytes 8..39 — COVERED
  - blob_offset(8) = bytes 40..47 — bytes 8+36=44 stops here, NOT covered
  - blob_len(4) = bytes 48..51 — NOT covered
  - crc(4) = bytes 52..55 — NOT covered (correct, it's the checksum itself)

FINDING P1-SEC-04: INDEX ENTRY CRC COVERS ONLY THE HASH FIELD — CRITICAL FIELDS UNPROTECTED

The CRC computation covers bytes [8, 44) = only the 32-byte hash field plus the first 4
bytes of what it computes starting at offset 8. Let me re-derive precisely:

xblob_index_entry_t layout:
- [0]  state: uint8_t (1 byte)
- [1-3] _pad: uint8_t[3] (3 bytes)
- [4-7] ref_count: uint32_t (4 bytes)
- [8-39] hash: uint8_t[32] (32 bytes)
- [40-47] blob_offset: uint64_t (8 bytes)
- [48-51] blob_len: uint32_t (4 bytes)
- [52-55] crc: uint32_t (4 bytes)

CRC covers `(uint8_t *)e + 8` for length `56 - 8 - 4 = 44` bytes:
= bytes [8, 52) = hash(32) + blob_offset(8) + blob_len(4) = 44 bytes

CORRECTION TO EARLIER ANALYSIS: blob_offset and blob_len ARE covered.

NOT covered: state(1), _pad(3), ref_count(4)

The most safety-critical fields (blob_offset = where the blob lives, blob_len = how big
it is) ARE protected by the CRC. The ref_count is NOT protected by the CRC.

A corrupted ref_count that reaches zero would trigger premature GC of a live blob.
This is a moderate integrity gap.

SEVERITY: P2 — ref_count corruption can cause premature blob deletion but is not
immediately exploitable. blob_offset and blob_len are protected.

---

## BLACK BOX API ANALYSIS (Test Type — Black Box)

### Consumer-Facing API Completeness

| API Function | Input Validation | Error Return | Documentation |
|-------------|-----------------|--------------|---------------|
| xstore_open() | NULL checks all params | XSTORE_ERR_INVAL | Complete |
| xstore_put() | NULL + len + open checks | Full set | Complete |
| xstore_get() | NULL + open checks | Full set | Complete |
| xstore_delete() | NULL + open checks | Full set | Complete |
| xstore_exists() | NULL + open checks | bool (no error code) | Note: exists() hides I/O errors |
| xblob_put() | NULL + len + open + readonly | Full set | Complete |
| xblob_get() | NULL + hash + open checks | XBLOB_ERR_CORRUPT on mismatch | Complete |
| xblob_delete() | NULL + open + readonly | Full set | Complete |

FINDING P2-API-01: xstore_exists() MASKS I/O ERRORS

```c
bool xstore_exists(xstore_t *store, const xstore_key_t *key) {
    ...
    xstore_status_t rc = xstore_btree_lookup(...);
    return (rc == XSTORE_OK || rc == XSTORE_ERR_NOMEM);
}
```

If btree_lookup returns XSTORE_ERR_IO or XSTORE_ERR_CORRUPT, xstore_exists() returns
`false` (key not found), which is indistinguishable from a genuine absence. The caller
has no way to distinguish "key does not exist" from "I/O error prevented the lookup."

SEVERITY: P2 — API design issue. Callers relying on xstore_exists() for critical decisions
(e.g., "should I install this package?") may act on false negatives.

### XBLOB Deduplication Correctness

FINDING PASS: XBLOB DEDUPLICATION IS CORRECTLY IMPLEMENTED

In blob.c:99-116, deduplication path:
1. `xblob_index_find(blob, hash)` — O(1) average hash lookup
2. If found: increment ref_count in index, increment dedup_saves, copy hash to out_hash
3. No new storage allocated, no new I/O

The SHA-256 content identity guarantee ensures two distinct byte sequences that hash to the
same value would deduplicate incorrectly, but SHA-256 collision resistance makes this
cryptographically negligible.

RESULT: Deduplication correctness VERIFIED.

---

## DATA CORRECTNESS SCORE: 5/10

Scoring rationale:
- Architecture and API surface: well-designed (saves 2 points)
- _Static_assert / struct sizes: all correct (+1)
- SHA-256 integration: correct, single source (+1)
- Deduplication: correct (+1)
- P0-SEC-02 (WAL replay CRC broken = crash recovery non-functional): -2
- P0-MVCC-01 (all writes record root_page = false OCC): -1
- P1-FUNC-01 (value not in WAL = crash loses data): -1
- P1-GC-03 (14KB stack allocation): -1
- P1-WAL-01 (274MB buffer undocumented): -0.5
- P1-FUZZ-02 (256 replay txn cap): -0.5

---

## COMPLETE FINDINGS REGISTER

### P0 (Critical — Must Fix Before Any Production Use)

| ID | File | Location | Title |
|----|------|----------|-------|
| P0-SEC-02 | wal.c | 117-118 | WAL replay CRC verification always fails — crash recovery non-functional |
| P0-MVCC-01 | mvcc.c | 282, 311 | All writes record root_page — false 100% conflict storm at concurrency |

### P1 (High — Must Fix Before Sprint 5)

| ID | File | Location | Title |
|----|------|----------|-------|
| P1-FUNC-01 | mvcc.c | 205 | Value not stored in WAL — crash loses committed data |
| P1-WAL-01 | xstore.h | 209 | 274 MB WAL buffer requirement undocumented — caller will allocate on stack |
| P1-MVCC-02 | mvcc.c | 54 | MVCC shadow table 8192 slots — collapses at scale beyond ~5000 pages |
| P1-FUZZ-02 | wal.c | 96, 121 | WAL replay tracks only 256 committed txns — silent data loss at 257th |
| P1-GC-01 | gc.c | 118,138 | gc_scan holds store_lock while calling gc_log_append (acquires gc_lock) — fragile lock ordering |
| P1-GC-03 | gc.c | 169 | 14 KB stack allocation for compaction chunk — stack overflow in kernel context |
| P1-SEC-04 | index.c | 98-99 | Index CRC does not cover ref_count — ref_count corruption causes premature GC |
| P1-REL-01 | xstore.c | 90-91 | wal_tail restored from checkpoint_lsn — units aligned only by invariant, not enforced |
| P1-SEC-01 | wal.c | 47-53 | WAL CRC covers its own checksum field (mitigated by pre-zeroing, but fragile) |

### P2 (Medium — Fix Before Sprint 5 or Document Accepted Risk)

| ID | File | Location | Title |
|----|------|----------|-------|
| P2-MVCC-03 | mvcc.c | 66-68 | g_mvcc_table is static global — breaks multi-store scenarios |
| P2-FUNC-02 | btree.c | 780-786 | Cursor advance stops at leaf page boundary — range scans truncated |
| P2-REL-02 | page_cache.c | 113-118 | Dirty page checksum not updated on eviction — stale checksums on disk |
| P2-GC-02 | gc.c | 176-196 | Compaction clears entries before re-inserting — storage leak on insert failure |
| P2-INT-01 | blob.c | xblob_get | Header CRC written at put but never verified at get |
| P2-SEC-03 | wal.c | 47-53 | LSN and txn_id excluded from WAL CRC — modifiable without detection |
| P2-API-01 | xstore.c | 232-240 | xstore_exists() masks I/O errors — returns false on XSTORE_ERR_IO |
| P2-FUZZ-01 | wal.c | 161-165 | Replay ignores all btree errors including XSTORE_ERR_CORRUPT |
| P2-DOC-01 | xstore.h | §6 header | Comment claims "128-byte records" — actual size is 4384 bytes |

### P3 (Low — Note and Track)

| ID | File | Title |
|----|------|-------|
| P3-STAT-01 | xstore.c | xstore_stats: txn_commits/txn_aborts/free_pages not tracked (TODO-S5 markers) |
| P3-STAT-02 | xblob.c | xblob_stats: gc_blobs_freed/gc_bytes_reclaimed not accumulated (TODO-S5) |
| P3-PERF-01 | page_cache.c | _cache_find is O(n) linear scan — Sprint 5 needs O(1) directory |

---

## WAL DURABILITY ANALYSIS

The crash-safety contract (xstore.h:29-33) states: "If power is lost between
xstore_txn_begin() and xstore_txn_commit(), the transaction is fully rolled back on the
next xstore_open() call via WAL replay."

VERDICT: CONTRACT IS NOT UPHELD due to P0-SEC-02 and P1-FUNC-01.

- P0-SEC-02: WAL replay discards all entries due to CRC mismatch. No replay occurs.
- P1-FUNC-01: Even if replay worked, values are absent from WAL entries. Replayed
  inserts write zero-length values.

After a crash, the store presents:
1. The last checkpointed state (correct, durable — pages flushed at checkpoint are fine)
2. Nothing from between checkpoint and crash (even committed data is lost)

The WAL provides durability FROM CHECKPOINT TO SYNC (sync() is called at checkpoint).
The window between the last checkpoint and crash loses all committed data.

VERDICT FOR WAL DURABILITY: 2/10 (checkpoints are durable; inter-checkpoint commits are not)

---

## MVCC CORRECTNESS ANALYSIS

Snapshot Isolation semantics are partially implemented:
- Snapshot acquisition at begin time (next_lsn): CORRECT
- Write set tracking: PRESENT but page granularity is wrong (P0-MVCC-01)
- OCC conflict check at commit: PRESENT but produces false positives (P0-MVCC-01)
- Read snapshot enforcement: PLACEHOLDER — `(void)snapshot_lsn` in btree_lookup (btree.c:510)

FINDING P1-MVCC-05: SNAPSHOT ISOLATION NOT ENFORCED ON READS

In btree.c:510: `(void)snapshot_lsn; /* Full per-version chain in Sprint 5 */`

The snapshot_lsn is captured and passed through the call chain, then discarded. Every
read returns the current physical leaf value regardless of the transaction's snapshot.
This means "reads from the past" do not work — a transaction started before a concurrent
commit will see the committed data immediately.

This violates Snapshot Isolation semantics. Under SI, T1 should not see data committed by
T2 if T2 committed after T1 began.

SEVERITY: P1 for correctness. For Sprint 4's single-writer use case (sequential XPKG
installs, provenance), read anomalies are benign. Must be fixed for Sprint 5.

VERDICT FOR MVCC CORRECTNESS: 4/10 (structural framework present; key enforcement missing)

---

## XBLOB DEDUPLICATION CORRECTNESS

VERDICT: 9/10 (correct; one P2 integrity gap on header CRC not verified at get)

- SHA-256 computed by pal_sha256() (FIPS 180-4, Sprint 3 implementation): CORRECT
- Hash used as storage key: CORRECT
- Deduplication check before write: CORRECT
- ref_count increment on dedup hit: CORRECT
- Full hash comparison to resolve prefix collisions: CORRECT (index.c:60)
- SHA-256 verified on every get(): CORRECT
- Header CRC not verified on get(): P2-INT-01

---
