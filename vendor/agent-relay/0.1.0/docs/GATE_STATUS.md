# Original gate mapping and actual local evidence

The installed wheel passed **111/111 shipped automated tests**, with no skipped tests. The methods exercise local aspects of **43 of the 46 original contract IDs**. This is not 43 fully certified production gates and is not a claim of 46/46.

The original `contracts/ORIGINAL_G01_G46.json` is preserved unchanged, including its historical NOT_RUN state. Current evidence is generated in `evidence/gate_coverage.json`. Read both the local-test column and the remaining-boundary column. Original meanings were not replaced to inflate pass counts.

G24 (native provider lifecycle), G27 (multi-host) and G30 (legacy migration/final acceptance) have no corresponding executed local tests in this release. G02 has relevant new regression tests but lacks the original audited source/suite required for compatibility equivalence. G32 safely rejects unpatched WAL; it is not a patched-WAL run. G39 is local key rotation plus an explicit external-fencing attestation, not distributed fencing proof.

| ID | Original title | Executed local test references | Original contract disposition |
|---|---|---:|---|
| G01 | Canonical path safety | 9 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G02 | Preserve original protections | 4 | BLOCKED_MISSING_ORIGINAL_SOURCE |
| G03 | Intent revision authority | 3 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G04 | Requirement preservation | 2 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G05 | Reopen scope | 3 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G06 | Typed domain records | 7 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G07 | Completion gate consistency | 4 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G08 | Evidence candidate binding | 5 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G09 | Admission dependencies | 1 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G10 | Context mandatory coverage | 3 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G11 | Superseded-memory adversary | 1 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G12 | Forced context reset | 2 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G13 | Effect write-ahead | 6 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G14 | Command idempotency | 5 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G15 | Functional vertical slice | 3 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G16 | Informational impostor | 1 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G17 | Fake-success and backend loss | 2 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G18 | Independent concurrency | 6 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G19 | Conflicting resource writes | 8 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G20 | Concurrent source invalidation | 2 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G21 | Cross-repository observation | 1 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G22 | Cross-repository candidate vector | 1 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G23 | Partial integration recovery | 1 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G24 | Provider discovery and lifecycle | 0 | NO_ENABLED_NATIVE_ADAPTER |
| G25 | Rate-limit handoff | 1 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G26 | Process and stale worker recovery | 8 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G27 | Partition discipline | 0 | OUT_OF_PROFILE |
| G28 | Privacy and export restore | 8 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G29 | Bounded hot-path performance | 4 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G30 | Migration and final acceptance | 0 | BLOCKED_MISSING_ORIGINAL_SOURCE |
| G31 | Exact source and diagnostic provenance | 2 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G32 | Patched storage and explicit durability preflight | 3 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G33 | Connection lifecycle under failure | 1 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G34 | Atomic preparation and artifact publication | 8 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G35 | Out-of-order and late authenticated receipts | 5 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G36 | Cancellation and authorization-change race | 3 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G37 | Deduplication expiry and ambiguous absence | 3 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G38 | Event replay and schema evolution | 4 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G39 | Backup restore cannot resurrect authority | 3 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G40 | Action-context freshness and actual delivery | 3 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G41 | Capability and information-boundary bypass | 6 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G42 | Acceptance oracle and verifier integrity | 8 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G43 | Fairness and bounded recovery scheduling | 4 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G44 | Uninstrumented performance and scrub contract | 1 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G45 | Capture race and candidate completeness | 5 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |
| G46 | Historical evidence and signed trust boundary | 2 | PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION |

Full per-test IDs, exact original required behavior and the remaining gap for each row appear in `evidence/gate_coverage.json`. Test counts overlap: one real test may exercise several contract IDs. Do not add row counts as if they were independent tests.

The first externally timed benchmark attempt was interrupted before completion and is not a benchmark PASS. Its post-interruption integrity check is recorded separately. A later completed 60-second workload supplies the actual contention results. Both observations are retained.
