# Sprint 25 Council Data Infrastructure — Detail Notes (2026-03-08)

## Files Created

| File | Purpose | Tier |
|------|---------|------|
| `council/runtime/artifacts/fs_artifact_store.py` | Content-addressed artifact ledger | Silver |
| `council/substrate/council_register.c` | XORCHESTRA service registration at boot | Substrate |
| `council/substrate/council_xstore_io.c` | XSTORE namespace guard (stub Sprint 25) | Bronze I/O |
| `council/substrate/council_xblob_io.c` | XBLOB SHA-256 I/O (stub Sprint 25) | Bronze I/O |
| `tests/test_sprint25.py` | 30-test integration suite (30/30 pass) | Tests |

---

## FSArtifactStore Architecture

### Phase 1 persistence
- Root: `/tmp/genos_artifacts/{artifact_id}.json`
- Provenance: `/tmp/genos_artifacts/provenance/{artifact_id}.json`
- Atomic writes via `tempfile.mkstemp + os.fdopen + fsync + os.replace`
- Idempotent: same content always yields same SHA-256 id; second put is a no-op
- Corrupt files quarantined to `.corrupt` on startup scan (never deleted — audit trail)

### Canonicalisation rule
- `json.dumps(envelope, sort_keys=True, ensure_ascii=True)` encoding to UTF-8
- Excludes `artifact_id` (assigned post-hash) and `_stored_at` (storage timestamp)

### Index structures (in-memory, rebuilt from disk)
- `_artifacts`: primary dict keyed by artifact_id
- `_by_agent`, `_by_type`, `_by_task`: secondary index lists
- `_provenance`: graph dict `{parent: str|None, children: list[str]}`

### Phase 2 XSTORE key schema (for Sprint 27 reference)
```
artifacts/{id[:8]}/{id}                  -> ArtifactMetadata JSON
artifacts/by-task/{task_id}/{seq}        -> artifact_id
artifacts/by-agent/{agent}/{date}/{seq}  -> artifact_id
artifacts/by-type/{type}/{date}/{seq}    -> artifact_id
provenance/{id}/parent                   -> parent_id
provenance/{id}/children/{seq}           -> child_id
```

---

## council_xstore_io.c Namespace Rules

Three authorised namespace prefixes:
1. `soul:{agent_name}:` — agent-scoped SoulManager keys (agent-exclusive)
2. `artifacts:` — FSArtifactStore metadata index (all Council agents permitted)
3. `journal:` — EventJournal (all Council agents permitted, append-only enforced at app layer)

`council_xstore_namespace_check(agent_name, key)` is the security gate.
Any write that fails this check returns `PAL_ERR_PERM` and emits a console audit log.

---

## council_xblob_io.c SHA-256 Strategy

- `pal_sha256` declared as `__attribute__((weak))` — links to PAL implementation if available
- If `pal_sha256 == NULL` (no PAL implementation linked), software SHA-256 fallback activates
- Software SHA-256 is RFC 6234-compliant; NOT hardware-accelerated — Sprint 27 mandates PAL impl
- Output: 32-byte binary hash; `xblob_bin_to_hex()` for console logging (first 16 hex chars)

---

## council_register.c Service Table

| Service | Health | Port | Start Timeout | Deps |
|---------|--------|------|---------------|------|
| soulmgrd | TCP_PROBE | 18610 | 10s | none |
| eventjournald | TCP_PROBE | 18611 | 10s | none |
| gaterunnerd | TCP_PROBE | 18612 | 10s | none |
| councild_broker | PROC | — | 10s | none |
| ahkid | TCP_PROBE | 18600 | 10s | soulmgrd, eventjournald, broker |
| ruthd | TCP_PROBE | 18601 | **15s** | soulmgrd, eventjournald, broker |
| sarahd | TCP_PROBE | 18602 | 10s | soulmgrd, eventjournald, broker |
| ezrid | TCP_PROBE | 18603 | 10s | soulmgrd, eventjournald, broker |
| abigaild | TCP_PROBE | 18604 | 10s | soulmgrd, eventjournald, broker |

ruthd gets 15s budget: JWT handshake + gate chain init + 16 subagent coroutine spawn.

---

## Critical Python Runtime Finding (CONFIRMED 2026-03-08)

**Python 3.14 removed `asyncio.get_event_loop()` from non-async contexts.**

- `asyncio.get_event_loop().run_until_complete(coro)` raises `RuntimeError: There is no current event loop in thread 'MainThread'` on Python 3.14
- Correct pattern: `asyncio.run(coro)` — always use this in sync test code
- Apply to: all test helpers that invoke async SoulManager / eventjournald from sync pytest methods
- Check existing tests (`test_sprint24.py`) for the same pattern — migrate if found

---

## XSTORE/XBLOB Sprint 27 Wiring Plan

When XSTORE C API is available:
1. Replace `council_xstore_put` stub body with `xstore_exec(handle, "PUT", key, value, value_len)`
2. Replace `council_xstore_get` stub body with `xstore_query(handle, "GET", key, out_buf)`
3. Replace `council_xblob_put` stub body with `xblob_write(content, len, out_sha256)`
4. Replace `council_xblob_get` stub body with `xblob_read(sha256_hash, out_buf, buf_size, out_len)` + re-hash integrity check
5. FSArtifactStore: replace `/tmp/genos_artifacts/` file backend with XStorePool + XBLOB calls
6. Migration: existing `/tmp/genos_artifacts/*.json` must be imported via one-time migration script before cutover
