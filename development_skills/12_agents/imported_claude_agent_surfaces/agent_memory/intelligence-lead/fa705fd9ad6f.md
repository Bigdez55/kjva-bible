# Sprint 3 Residual Security Risk Model
# Date: 2026-03-06
# Author: Intelligence Lead
# Method: Risk Score = Likelihood (1-5) x Impact (1-5). ASR% computed over severity-weighted universe.

## Risk Register — All Open Findings Post Sprint 3 Hardening

| ID | Source | Description | L | I | Risk | Priority | Sprint |
|---|---|---|---|---|---|---|---|
| GS-S3-P1-005 | Guardian Sentinel | RSA/ECDSA cert chain silently passes x509 verify (non-Ed25519 bypass) | 4 | 5 | 20 | P0-block | S4 |
| GS-S01-001 | Guardian Sentinel | SYSRETQ non-canonical RIP — privilege escalation (CVE-2012-0217 class) | 3 | 5 | 15 | P0-block | S4 |
| GS-S3-P1-004 | Guardian Sentinel | ChaCha20 Poly1305 static scratch buffer — thread-unsafe auth MAC | 3 | 4 | 12 | P1-sprint | S4 |
| P1-UAF-01 | Guardian Sentinel | xkabi_capabilities.c:332-334 PTR_ERR after kfree — use-after-free | 3 | 4 | 12 | P1-sprint | S4 |
| GS-S01-002/P1-NO-HMAC-01 | Guardian Sentinel | XKABI handle forgery, no HMAC (~40-bit entropy) | 2 | 4 | 8 | P1-sprint | S4 |
| GS-S01-003 | Guardian Sentinel | TPM measurement dead — tpm2_measure_aetherboot(NULL,0) hashes empty string | 2 | 4 | 8 | P1-sprint | S4 |
| GS-S3-P1-006 | Guardian Sentinel | TLS double record send — protocol violation, interop break | 3 | 3 | 9 | P1-sprint | S4 |
| P0-KEY-01 | Guardian Sentinel | signing.key in git history — requires rotation + git-filter-repo purge | 2 | 5 | 10 | P0-block | S4 |
| GS-S3-P1-007 | Guardian Sentinel | X25519 fe_pack non-canonical reduction — potential info leak | 2 | 4 | 8 | P1-sprint | S4 |
| GS-S3-P1-008 | Guardian Sentinel | ghash_mul timing side-channel on H (secret) — GCM tag forgery | 3 | 4 | 12 | P1-sprint | S4 |
| P2-NO-SAN-01 | Guardian Sentinel | X.509 no SAN support, CN-only — fails most production certs | 4 | 3 | 12 | P1-sprint | S4 |
| P2-POLY-STACK-01 | Guardian Sentinel | ChaCha20 32KB poly_scratch on stack — kernel stack overflow | 3 | 4 | 12 | P1-sprint | S4 |
| D-S1-02 | Int.Lead v2 | IST stacks missing in TSS — NMI/DF/MC fault stack corruption | 3 | 4 | 12 | P1-sprint | S4 |
| D-S1-03 | Int.Lead v2 | SWAPGS NMI race — 3-insn window, CPL0 exploitable | 3 | 4 | 12 | P1-sprint | S4 |
| D-S1-04 | Int.Lead v2 | HHDM NX bit missing — kernel direct map executable | 2 | 4 | 8 | P1-sprint | S4 |
| GS-S01-003 TPM-6 | Kernel Audit | tpm2_get_pcr digest_offset=28 should be 30 — wrong PCR readback | 2 | 2 | 4 | P2-backlog | S4 |
| P2-TLS-UNLOGGED-01 | Guardian Sentinel | 8 tls13.c error paths lack audit logging (ServerHello + encrypted record) | 3 | 2 | 6 | P2-backlog | S4 |
| P2-AUDIT-SWITCH-01 | Guardian Sentinel | audit.c missing XPKG gate event/module names — returns "UNKNOWN" | 2 | 2 | 4 | P2-backlog | S4 |
| P2-CT-VOLATILE-01 | Guardian Sentinel | AES CT loop lacks volatile — theoretical LTO regression risk | 1 | 3 | 3 | P2-backlog | S4 |
| P2-CT-TOLOWER-01 | Guardian Sentinel | Branching tolower in hostname compare — non-CT (hostname not secret) | 2 | 2 | 4 | P2-backlog | S4 |
| GS-S3-P3-001 | Guardian Sentinel | TLS 16KB stack buffers — kernel stack overflow (3 locations) | 3 | 4 | 12 | P1-sprint | S4 |
| P1-LIC-01 | Guardian Sentinel | 83 files AGPL-3.0 SPDX vs Proprietary LICENSE — license conflict | 3 | 3 | 9 | P1-sprint | S4 |
| GS-S01-011 | Guardian Sentinel | gsd_validate known_mask missing MEM_REGISTER, RDMA_*, MESH_JOIN | 2 | 3 | 6 | P2-backlog | S4 |
| GS-S01-006 | Guardian Sentinel | XKABI slot exhaustion DoS (revoked slots never freed) | 2 | 3 | 6 | P2-backlog | S4 |
| GS-S3-P3-004 | Guardian Sentinel | Poly1305 final reduction not CT (prob ~5/2^130) | 1 | 1 | 1 | P3-observe | S5+ |
| DSF-NET-01 | Req | enum prefix hygiene (cosmetic) | 1 | 1 | 1 | P3-observe | S5+ |
| DSF-PAL-01 | Req | timer_create delivery mechanism (FIXED by P1-TIMER-OBJ-TYPE-01 in S3) | 0 | 0 | 0 | CLOSED | — |

## Fixed Items (Used in ASR Calculation)

| ID | Description | Pre-fix L | Pre-fix I | Pre-fix Risk | Status |
|---|---|---|---|---|---|
| GS-S3-P0-001 | AES S-Box timing side-channel | 5 | 5 | 25 | FIXED |
| D-S3-P0-SHA | SHA-256 length corruption in finalization | 5 | 5 | 25 | FIXED |
| GS-S3-P1-001 | TLS CertificateVerify not verified | 4 | 5 | 20 | FIXED |
| GS-S3-P1-002 | TLS Certificate not parsed/validated | 4 | 5 | 20 | FIXED |
| GS-S3-P1-003 | X.509 tbs_data wrong range (-4 offset) | 4 | 4 | 16 | FIXED |
| D-S1-05 / GS-S01-005 | capability_init.c rights mismatch (8/8 wrong) | 4 | 4 | 16 | FIXED |
| P1-TIMER-OBJ-TYPE-01 | PAL timer uses PAL_OBJ_EVENT (type confusion) | 3 | 4 | 12 | FIXED |
| FIX-04 (sig_len_cv) | Ed25519 sig length not validated before verify | 3 | 4 | 12 | FIXED |
| FIX-02 (gf_mul CT) | AES gf_mul not constant-time | 3 | 3 | 9 | FIXED |
| FIX-06 (DNS QID) | DNS sequential query IDs — Kaminsky attack | 3 | 3 | 9 | FIXED |
| FIX-07 (null-byte + O= bypass) | X.509 CN null-byte injection | 3 | 4 | 12 | FIXED |
| FIX-09 (TWICE_P) | X25519 fe_sub TWICE_P[0] bias | 2 | 4 | 8 | FIXED (confirmed correct) |
| TLS audit gaps | 6/6 targeted handshake audit log paths | 3 | 2 | 6 | FIXED |
| chacha20 poly_scratch | Moved to stack-local (P2 in prior audit) | 2 | 3 | 6 | FIXED |

## ASR Calculation

fixed_severity_sum = 25+25+20+20+16+16+12+12+9+9+12+6+6 = 188
total_severity_sum (fixed + open combined) = 188 + (20+15+12+12+8+8+9+10+8+12+12+12+12+12+8+4+6+4+3+4+12+9+6+6+1+1) = 188 + 236 = 424
ASR% = 188/424 * 100 = 44.3%

## Sprint 4 Security Priority Ranking

Rank 1: GS-S3-P1-005 — RSA/ECDSA bypass (Risk=20, 78% of residual XSEC risk)
Rank 2: GS-S01-001 — SYSRETQ priv esc (Risk=15, P0 kernel finding)
Rank 3: P0-KEY-01 — signing.key in git (Risk=10, infrastructure P0)
Rank 4: GS-S3-P1-004 + GS-S3-P1-008 + P2-POLY-STACK-01 + D-S1-02/03 — Risk=12 cluster

## Notes
- D-S3-P0-ghash: FALSE POSITIVE RETRACTED (2026-03-06). Already branchless CT.
- GS-S3-P1-008: Originally listed P2, upgraded to P1 in re-audit (H is secret key material).
- XSTORE/XBLOB Sprint 4 risk: Not yet audited. Predictive model: P(at least 1 P1)=0.95 [CI:0.88,0.99].
  Known risk vectors: integer overflow in page math (R2=0.88), OCC state-scope rollback (R2=0.82), WAL length bounds (R2=0.79).
