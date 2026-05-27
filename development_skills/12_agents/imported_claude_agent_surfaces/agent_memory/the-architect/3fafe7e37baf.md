# RFC-002 v5.1 P0/P1 Fix Review — 2026-02-27

## Review Scope
Six targeted fixes across kernel C, platform Python (FastAPI), and Electron TypeScript layers.
All files read and cross-referenced against their headers and inter-module contracts.

---

## P0-1: entropy_classifier.c — LUT direct summation

### Status: APPROVED WITH RESIDUAL ADVISORY

**What the fix did:**
Replaced broken fixed-point accumulation with direct LUT summation.
`lut_idx = (u32)(((u64)freq[i] * 256) / len)` then `entropy_x256 += log2_lut[lut_idx]`.

**Verified correct:**
- O(n) + O(256) complexity. Single-pass frequency count then LUT lookup.
- `(u64)freq[i] * 256` upcast prevents u32 overflow before division.
- `min_t(u64, normalized, 255)` correctly caps return to u8 range.
- rounding at `lut_idx = 255` (clamped if > 255) prevents OOB.
- Prior ENT-C1 defect (255 vs 256 multiplier) CONFIRMED FIXED. lut_idx uses 256.

**Residual advisory (carries forward from prior audit):**
- LUT-SHORT: For packets < 256 bytes the LUT calibration is approximate (LUT assumes
  256-byte population). Score accuracy degrades for very short payloads. Not a regression
  from the fix — was pre-existing. Documented in prior audit as DEFECT PAYLOAD-1.
- LUT-ZEROS: lut[0]=0 (freq=0 byte skipped via `if (freq[i] == 0) continue` — CORRECT).
  Zero entries are properly excluded from accumulation.

---

## P0-2: mr_registry.c + vdram.h — four sub-fixes

### Status: APPROVED WITH ONE RESIDUAL MEDIUM

### owner_node back-pointer (vdram.h)
APPROVED. `struct vdram_mr *owner_node` field present in vdram.h line 91.
`vdram_mr_alloc()` sets `mr->owner_node = node` before spin_lock on node->mr_lock.
Assignment order is safe — mr is private (not yet published to RCU table) at that point.

### list_del under lock (vdram_mr_free)
APPROVED. `vdram_mr_free()` acquires `node->mr_lock` before `list_del_init(&mr->node)`.
Uses `list_del_init` (not bare `list_del`) — safe against double-del if mr->node is
already initialized (INIT_LIST_HEAD called in alloc). lock nesting order:
  alloc: mr_lock -> mr->lock (no nesting — separate operations)
  free:  mr_lock -> rkey_table_lock (no nesting — sequential)
No deadlock risk; locks are never held simultaneously across the two callsites.

### bounded rkey generation (mr_generate_rkey)
APPROVED. 128-iteration retry limit prevents infinite spin at high table occupancy.
Returns 0 on exhaustion with pr_warn. Callers (vdram_mr_rdma_enable, vdram_rkey_rotate)
check for 0 and return -ENOSPC. Correct error propagation.

### rkey==0 check (vdram_mr_free)
APPROVED. `if (mr->rkey)` correctly guards the rkey table cleanup — 0 is the
uninitialized value (kzalloc zeroes the struct), so RDMAless MRs are cleanly skipped.
Consistent with mr_generate_rkey's `rkey != 0` invariant.

**Residual medium (MR-H1, from prior audit — not introduced by this fix):**
mr_generate_rkey() is called with rkey_table_lock HELD. At >99% occupancy, this loops
O(65536) times holding a spinlock. Hard capacity gate at ~60K (92%) recommended.
This fix did not worsen the condition but did not resolve it either.

**Residual race in vdram_rkey_rotate (NOT resolved by P0-2):**
`vdram_rkey_rotate()` reads `mr->rkey` (old_rkey) WITHOUT holding `mr->lock` at line 174.
A concurrent `vdram_mr_rdma_enable()` could be writing `mr->rkey` simultaneously.
Fix: acquire mr->lock to read old_rkey before locking rkey_table_lock.
Current lock order in rotate: rkey_table_lock -> synchronize_rcu -> rkey_table_lock -> mr->lock.
The old_rkey read is naked — race window is narrow (RDMA enable rarely concurrent with rotate)
but the invariant is violated. SEVERITY: MEDIUM.

---

## P0-3: xkabi_capabilities.c — generation capture under lock, ht_free leak fix

### Status: APPROVED — both sub-fixes sound

### generation capture under lock
APPROVED. `cap_generation = cap->generation` is captured inside `spin_lock(&ht->lock)` /
`spin_unlock(&ht->lock)`. The subsequent epoch check at revocation_lock uses the local
copy — no dangling pointer dereference after lock release. Correct two-phase pattern.

The comment on line 218-219 correctly documents WHY this is necessary. This is the
precise fix for the TOCTOU race: cap could be freed by concurrent revoke() after ht->lock
is released, so the generation value must be captured while the lock is held.

### ht_free leak fix
APPROVED. `xkabi_ht_free()` now iterates `idr_for_each_entry` before `idr_destroy()`.
This correctly frees all `struct xkabi_cap *` entries.
`crypto_free_shash()` called first, then `memzero_explicit()` on hmac_key — correct
teardown order (tfm freed before key scrubbed is fine; key material scrubbed last).

**Carrying-forward known defects (not introduced by this fix):**
- RFC-C1: XKABI_RIGHT_* vs XK_RIGHT_* namespace not unified — still open.
- XK-H1: 24-bit vs 20-bit IDR mask aliasing — still open.
- VALIDATE-1: IDR lookup mask mismatch (0xFFFFFF vs 0xFFFFF) — still open.
- XK-M1: 16-bit generation wrap — still open.

---

## P0-5: main.ts (res.ok) + identity/app.py (status_code=201)

### Status: APPROVED — cross-module contract now consistent

### identity/app.py
`@app.post("/users", response_model=UserInfo, status_code=status.HTTP_201_CREATED)`
Line 330. `status.HTTP_201_CREATED` is the FastAPI-idiomatic constant (= 201). APPROVED.

### main.ts shell:create-user
```typescript
if (res.ok) {
  return { ok: true };
}
```
`res.ok` covers HTTP 200–299 inclusive. This correctly handles both 200 and 201
responses and is robust against future status code changes (e.g., 202 Accepted for
async creation flows). APPROVED.

**SHELL-C1 from prior audit: RESOLVED.** The prior defect was `res.status === 201`
vs the server returning 200. Both sides are now fixed in a coordinated pair.

**Cross-module contract verified:**
- identity/app.py POST /users → 201
- main.ts shell:create-user checks res.ok (200–299)
- main.ts shell:create-user sends `{ username, password, email: \`${username}@genos.local\` }`
- identity/app.py UserCreate expects: username (min 3), email (EmailStr), password (min 10)
- Synthetic email `${username}@genos.local` satisfies EmailStr validation. SOUND.

**Residual DRY violation (SHELL-M1, prior audit):**
`shell:unlock` and `identity:login` IPC handlers are still 100% duplicate logic (lines
118-136 vs 140-158). Not a regression; not introduced by this fix. Still open.

---

## P1-4: sync/app.py — route reorder (list before wildcard)

### Status: APPROVED — routing ambiguity eliminated

**What the fix did:**
Moved `GET /files/list/{path:path}` to be declared BEFORE `GET /files/{path:path}`.

Current order in the file (verified):
1. Line 133: POST /files/upload
2. Line 146: GET /files/list/{path:path}
3. Line 153: GET /files/{path:path}
4. Line 163: DELETE /files/{path:path}

FastAPI/Starlette registers routes in declaration order. A request to
`GET /files/list/foo` now correctly matches the specific `/files/list/{path:path}`
route rather than being consumed by the wildcard `/files/{path:path}`.

SYNC-H1 from prior audit: RESOLVED.

**Residual findings (not introduced by this fix):**
- SYNC-L1: delete_file() does not handle 404 from MinIO — still open.
- SYNC-L2: list_files() uses `__dict__` instead of `dataclasses.asdict()` — still open.

---

## P1-6: qp_relay.c — RCU restructuring

### Status: APPROVED WITH ONE ADVISORY

**What the fix did:**
`zc_gw_relay_packet()` now holds `rcu_read_lock()` for the entire duration that
`entry` is accessed, including the header translation and forwarding path.

**RCU lifetime analysis:**
- `rcu_read_lock()` acquired at line 223.
- `entry` looked up via `qp_find_rcu()` at line 224 (uses `hash_for_each_possible_rcu`).
- Entry fields read (dst_gid, dst_qpn, dst_lid) and written (fwd_packets, fwd_bytes,
  last_used_ns) while under RCU read lock.
- `rcu_read_unlock()` at line 300, AFTER all entry accesses.
- Return path on entry==NULL correctly releases the lock before returning -ENOENT.

**Atomic stats update under RCU read lock:**
`atomic64_inc(&entry->fwd_packets)` and `atomic64_add(pkt_len, &entry->fwd_bytes)` are
safe under concurrent writers via atomic operations. `entry->last_used_ns` write at
line 298 is NOT atomic — it is a bare u64 write. On 64-bit ARM (DPU/FPGA target), this
is naturally atomic, but it is architecturally not guaranteed. ADVISORY: use
`WRITE_ONCE(entry->last_used_ns, ktime_get_ns())` for explicitness.

**Destroy path (zc_gateway_destroy):**
Uses `hash_for_each_safe` + `hash_del` under `table_lock` then `kfree_rcu(e, rcu)`.
`kfree_rcu` defers the free until all RCU readers complete — no UAF. APPROVED.

**Registration path (zc_gw_qp_register):**
Uses `hash_add` under `table_lock` (not an RCU-aware add). Readers use
`hash_for_each_possible_rcu`. This is a common pattern: writes hold the spinlock and
use `rcu_assign_pointer` (or equivalent), reads use RCU. However, `hash_add` is not
RCU-safe without `spin_lock` on the write side. The spinlock IS present here, so the
mutual exclusion between concurrent registrations is correct. Readers only need to
be careful not to dereference a partially-initialized entry — since the entry is
fully initialized before `hash_add`, this is safe. APPROVED.

**Latency threshold check:**
Line 305 checks `elapsed_ns > 800` for FPGA path. The comment says `<800ns` target.
`> 800` fires the warning when latency EXCEEDS 800ns — CORRECT. No off-by-one.

**fabric_proto_t cross-module contract:**
`entropy_classifier.h` forward-declares `typedef enum fabric_protocol fabric_proto_t`
without defining the enum. `qp_relay.h` defines the actual enum. The forward declaration
in entropy_classifier.h is only valid if the TU that includes entropy_classifier.h also
includes qp_relay.h (or vice versa). `entropy_classifier.c` includes only
`entropy_classifier.h` — it uses `fabric_proto_t` in `entropy_classify_route()` return
type, but the enum definition comes from the forward declaration only. In C, returning
an incomplete enum is technically valid (sizeof is implementation-defined), but it can
cause issues if the compiler needs to know the underlying integer type for the return.
ADVISORY: `entropy_classifier.h` should include `qp_relay.h` directly instead of
forward-declaring, or both should include a shared `fabric_types.h`.

---

## Summary Matrix

| Fix    | File                                  | Status   | Critical Residuals |
|--------|---------------------------------------|----------|--------------------|
| P0-1   | entropy_classifier.c                  | APPROVED | LUT-SHORT advisory (pre-existing) |
| P0-2   | mr_registry.c + vdram.h              | APPROVED | old_rkey naked read in rotate (MEDIUM) |
| P0-3   | xkabi_capabilities.c                  | APPROVED | RFC-C1, XK-H1 still open (pre-existing) |
| P0-5   | main.ts + identity/app.py             | APPROVED | SHELL-M1 DRY (pre-existing) |
| P1-4   | sync/app.py                           | APPROVED | SYNC-L1, SYNC-L2 (pre-existing) |
| P1-6   | qp_relay.c                           | APPROVED | last_used_ns WRITE_ONCE advisory |

All six fixes are architecturally sound and safe to commit. Three residual items
(naked old_rkey read, WRITE_ONCE advisory, fabric_proto_t forward-decl) are new findings
introduced by this review and should be tracked as follow-up work items.
