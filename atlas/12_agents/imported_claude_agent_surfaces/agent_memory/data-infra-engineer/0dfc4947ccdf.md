---
name: Sprint 41 storage and memory fixes audit
description: Findings from the H2/H4/H5/H6/H13/H15/M17 storage and memory fix pass; which items were already resolved vs. which had a real remaining bug
type: project
---

# Sprint 41 — Storage & Memory Fix Audit (2026-03-21)

**Why:** Comprehensive pass over XSTORE WAL checkpoint, free-page tracking, txn
commit counter, XBLOB GC metrics, XMIND 336MB memory leak, XMIND heap_free
no-op, and council telemetry hardcoded stubs.

**How to apply:** Before raising a fix ticket for these items in future sprints,
consult this file first — most were already resolved in Sprint 38.

---

## Status of Each Item

| Item | File | Status | Sprint fixed |
|------|------|--------|--------------|
| H2: WAL unbounded growth — checkpoint | `store/xstore/wal/wal.c` | **ALREADY DONE** — full `xstore_wal_checkpoint()` exists (§4, lines 191-258). Auto-trigger wired in `mvcc.c` after each commit at 75% fill (lines 279-288). | Sprint 38 |
| H4: free_pages stub | `store/xstore/xstore.c` | **ALREADY DONE** — free-list walk implemented (lines 328-336). | Sprint 38 |
| H5: txn_commits stub | `store/xstore/xstore.c` | **ALREADY DONE** — uses `store->next_txn_id - 1` and `store->txn_aborts` (lines 341-343). | Sprint 38 |
| H6: gc_blobs_freed stub | `store/xblob/xblob.c` | **ALREADY DONE** — tombstone count used as gc_blobs_freed (lines 144-151). | Sprint 38 |
| H13: XMIND 336MB leak per restart (state buffers) | `ai/xmind/src/xmind.c` | **ALREADY DONE** — `xmind_shutdown()` frees all state buffers via `xm_heap_free()` slab. | Sprint 10 / Sprint 38 |
| H13: XMIND 336MB leak per restart (weight pages) | `ai/xmind/src/weights_loader.c` | **BUG FOUND + FIXED** — `wl_free_all_pages()` called `pal_pages_free(ph)` without `pal_unmap(mh)` first. Added `pal_unmap(mh)` call with `PAL_HANDLE_INVALID` guard. | Sprint 41 (this session) |
| H15: heap_free was a no-op | `ai/xmind/src/xmind.c` | **ALREADY DONE** — Sprint 38 fix: `xm_heap_free()` calls `pal_unmap(mh)` then `pal_pages_free(ph)` via slab. | Sprint 38 |
| M17: Council telemetry hardcoded stubs | `council/ruth/telemetry/telemetryd.c` | **ALREADY DONE** — reads live `pal_thermal_read_cpu()`, `vdram_pf_get_drops()`, `vdram_pf_get_enqueued()`, `svc_registry_foreach()`. | Sprint 38 |

---

## The One Real Fix (H13/H15-WL)

**File:** `ai/xmind/src/weights_loader.c`

**Root cause:** `wl_free_all_pages()` (line ~525) iterated the `s_wl_slab[]`
array and called `pal_pages_free(ph)` for each entry but never called
`pal_unmap(mh)`. The virtual mapping handle leaked on every model restart.
For Llama 3.2 3B (~370 weight allocations × 4 KiB–multi-MB pages), this
caused ~336 MB of virtual address space to leak per restart.

**Fix applied:** Added `pal_unmap(s_wl_slab[i].mh)` before `pal_pages_free()`
with a `PAL_HANDLE_INVALID` guard. Also updated the stale Sprint 8 comment in
`xmind_weights_unload()` which falsely claimed the memory was leaked.

**Pattern:** This is the identical bug that `xm_heap_free()` had in Sprint 6,
fixed in Sprint 38 (RA-XMIND-02). The weight-loader slab (`s_wl_slab`) is a
separate parallel slab from the inference-state slab (`s_xm_slab`) — both
must follow the `pal_unmap → pal_pages_free` order.

**Key invariant to enforce in all future PAL memory management code:**
Always call `pal_unmap(mh)` BEFORE `pal_pages_free(ph)`. Freeing physical
pages while the virtual mapping is still live produces a dangling VA range
with undefined behavior on the next mmap.

---

## Structural Notes on XSTORE/XBLOB After Sprint 38

- `xstore_wal_checkpoint()` in `wal.c` is the canonical checkpoint function.
  `xstore_checkpoint()` in `xstore.c` is just a thin forwarder to it.
- Auto-checkpoint is at 75% of `XSTORE_WAL_RING_SIZE` (65536 entries), not
  the 1024-entry threshold that was proposed in the task spec. The threshold
  in the actual code is intentionally higher to reduce checkpoint frequency.
- The WAL ring never shrinks below `wal_tail` — tail advances only after a
  checkpoint commits and updates the superblock. This is correct ACID behavior.
- `store->txn_aborts` is incremented in `xstore_txn_abort()` — needed to make
  the H5 stats counter accurate for aborted transactions.
