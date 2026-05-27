# RFC-002 v5.1 Signal Analysis Detail (2026-02-27)

## Change-by-Change Signal Scores

| # | Change | TEI | Gate | Verdict |
|---|--------|-----|------|---------|
| 1 | XISC opcode collision fix | +4.5 | PASS | RETAIN |
| 2 | FALLBACK_STATE thermal/fabricEnergy | +1.6 | PASS (marginal) | RETAIN |
| 3 | test_pf_select_tier (6 tests) | +2.2 | PASS | RETAIN |
| 4 | XKABI MAC 8B + rights u32 | -3.2 | REJECT | FIX REQUIRED |
| 5 | thermal_guardian async | +2.4 | PASS | RETAIN |
| 6 | RCU fix mr_registry | +3.8 | PASS | RETAIN (w/ note) |
| 7 | Entropy LUT 256 entries | -2.5 | REJECT | FIX REQUIRED |
| 8 | thermal_predictor daemon | +1.9 | PASS | RETAIN |
| 9 | provenance_client URL | +1.5 | PASS (marginal) | RETAIN |
| 10 | Makefile.rfc002 | +1.8 | PASS | RETAIN |

## CRITICAL FINDING DETAILS

### F1: XKABI Handle Layout Collision
- File: kernel/linux-validation/security/xkabi_capabilities.c
- encode_handle writes: [0:5] obj_id, [6:9] rights u32, [10:13] gen u32
- Then stores 8-byte HMAC at [8:15], overwriting rights bytes [8:9] and all of gen+reserved
- verify_handle reads *(u32*)&handle[6] => corrupted (rights_lo16 | hmac[0:1] << 16)
- Fix options: (A) shrink obj_id to 5 bytes, (B) extend handle to 24 bytes, (C) revert to 4-byte MAC

### F2: XKABI Audit Log u16 Truncation
- xkabi_audit_log(u64, u16, u32) signature truncates rights bits 16-23
- Lost rights in audit: NET_SEND(17), NET_RECV(18), GPU_EXEC(19), MESH_JOIN(20), ATTEST(21), DERIVE(23)
- Fix: change u16 to u32

### F3: Entropy LUT Formula Mismatch
- Comment: round(-f/256*log2(f/256)*256) => range [0,136], peak f=88
- Actual: range [0,1685], peak f=22. 254/256 mismatches.
- lut[1]=0 means uniform-random data (all freq=1) scores 0 entropy
- Routes dense ML gradient traffic to UET (sparse) instead of IB (dense)
- Fix: regenerate with correct formula, recalibrate thresholds

### F4: Missing synchronize_rcu in vdram_mr_free
- RCU_INIT_POINTER(NULL) then immediate vfree/kfree
- Concurrent readers may still hold pointer from rcu_dereference
- Fix: synchronize_rcu() or kfree_rcu() before freeing

## SECONDARY FINDINGS
- XISC_ALLGATHER (0x63) has no JIT handler => silent skip
- thermal_guardian falls back to random temps silently on non-NVIDIA hardware
- test_pf_select_tier re-implements kernel logic (structural drift risk)
- Makefile tools-check does not cover thermal_predictor.py
- FALLBACK_STATE thermal/fabricEnergy = undefined (not safe empty objects)
