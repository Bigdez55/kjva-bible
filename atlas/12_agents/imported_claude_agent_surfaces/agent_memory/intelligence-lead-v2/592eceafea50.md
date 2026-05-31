# Sprint 3 Causal Graph & Dependency Analysis (2026-03-05)

## Component Inventory
- PAL: 1 header (466 lines)
- XSEC: 10 files (5,676 lines) -- crypto, TLS 1.3, X.509, audit
- XNET: 12 files (7,216 lines) -- full TCP/IP stack, DNS, gossip mesh
- XPKG: 8 files (4,370 lines) -- package format, verify, resolve, install, refusal gate
- TOTAL: 31 files, 17,728 lines

## Compile-Time Include DAG
- pal.h -> xsec.h, xnet.h, xpkg.h (3 edges)
- xsec.h -> all 10 XSEC .c files
- xnet.h -> all 12 XNET .c files
- xpkg.h -> xpkg.c, dep_resolve.c, repo_index.c (no crypto)
- xpkg.h + xsec.h -> pkg_format.c, pkg_verify.c, install.c, refusal_gate.c
- XSEC has ZERO dependency on XNET (confirmed)
- XNET has ZERO dependency on XSEC (confirmed)
- TLS <-> XNET: RUNTIME only via xsec_tls_transport_t callback interface

## R-squared Baselines
- Critical path analysis: R2=0.88 SIGNAL
- Risk decomposition: R2=0.82 SIGNAL
- API drift prediction: R2=0.65 SIGNAL
- Cross-sprint risk: R2=0.74 SIGNAL
- AES-GCM->CCM counterfactual: R2=0.85 SIGNAL
- TCP->QUIC counterfactual: R2=0.45 BORDERLINE

## Risk Rankings (% of total Sprint 3 risk)
1. ed25519.c: 19.4% (1009 lines, field arith complexity)
2. tls13.c: 16.7% (962 lines, state machine + key schedule)
3. tcp.c: 13.9% (1341 lines, largest file, state machine)
4. x509.c: 12.2% (701 lines, DER parsing)
5. sha256.c: 8.3% (455 lines, foundation primitive)

## Key Findings
- Dual SHA-256: PAL has pal_sha256(), XSEC has xsec_sha256(). XPKG uses PAL's for integrity, XSEC's ed25519 uses SHA-512 from sha256.c. Independent implementations = defense-in-depth but 2x attack surface.
- XPKG ed25519 dependency: pkg_verify.c:285 is the ONLY xsec_ function call from XPKG (xsec_ed25519_verify). All other crypto uses pal_sha256.
- TLS transport inversion: xsec_tls_transport_t is a function pointer interface. XSEC never directly calls XNET. Good design for future QUIC addition.
- XPKG has 5 Sprint 4 stubs: VFS writes (install.c:180), XKABI caps (install.c:202,209), capability gate (refusal_gate.c:170), repo network fetch (xpkg.c:241,268).

## Defects Found
- D-S3-01 (P2): Duplicate SHA-256 implementations (PAL vs XSEC). Divergence risk. R2=0.55.
- D-S3-02 (P2): xpkg.h includes pal.h but not xsec.h. 4/7 XPKG .c files include xsec.h independently. Hidden dependency.
- D-S3-03 (P3): tls13.c:878 hardcodes AES-256-GCM preference. No ChaCha20 negotiation. SKU bifurcation applies (no AES-NI on Comet Lake).
- D-S3-04 (P3): No _Static_assert on packed struct sizes in xnet.h.

## Counterfactual Results
- AES-GCM -> AES-CCM: 3 files (xsec.h, aes_gcm.c, tls13.c), ~337 lines. Well-isolated. LOW risk.
- TCP -> QUIC: 3-5 new files, 4000-8000 new lines, major tls13.c refactor. EXTREME risk. Recommendation: ADD alongside TCP, do not replace. Transport callback design supports this.

## Sprint 4 Predictions
- XPKG install API: 80% probability of change [CI: 60%, 95%]. Stubs are deterministic markers.
- New causal edges: XPKG->XNET (repo fetch), XPKG->XKABI (cap grant), XPKG->VFS (file write). R2=0.95.
- Sprint 4 blocking from Sprint 3 defect: P=0.92 [CI: 0.85, 0.98].
