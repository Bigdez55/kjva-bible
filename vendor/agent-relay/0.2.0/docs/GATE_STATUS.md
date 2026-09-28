# G01–G46: executable evidence and deployment acceptance — 0.2.0

Generated from the installed 0.2.0 wheel's current verification and immutable
policy. **167/167 tests passed, zero skipped, all 46 original IDs have passing
local behavioral tests.** The original byte-preserved 0.1.0 suite was separately
executed against installed 0.2.0: **111/111 passed**. That second run is regression
compatibility, not 111 additional distinct new tests.

## The three previously missing implementations

| Gate | Implemented behavior | Passing local test references |
|---|---|---:|
| G24 — Provider discovery/lifecycle | Installed MCP stdio sessions, canonical identity, exact delivered-context acknowledgment, reset invalidation, tool admission, EOF/kill/cold-successor recovery | 17 |
| G27 — Partition discipline | Opt-in mutual-TLS workers, certificate/grant binding, single authority, actual dropped post-commit reply, command-ID replay, expiry/reconnection/stale-fence rejection | 10 |
| G30 — Migration/final acceptance | Actual archived 0.1.0/schema-1 import, exact historical bytes, source fencing, fresh target credentials, process-death recovery, controlled rollback, evidence-bound acceptance | 27 |

Counts above are gate references and can overlap. They are not separate passing
production certifications. Detailed test names and unchanged requirement text are
in `../evidence/gate_coverage.json` and `../contracts/ORIGINAL_G01_G46.json`.

## Current acceptance result

The installed evaluator accepts **24 gates within the declared profile** and
holds **22 remaining deployment boundaries for explicit review**. No test failed;
no original ID lacks local tests. No user deployment reviews were created or
approved. `ready=false` is therefore an intentional operator/deployment hold, not
an unexecuted test suite. Failed, skipped, missing or altered tests cannot be
waived by reviewing another boundary.

`full_original_certification=false`: native vendor clients were not available,
network tests used actual TLS on loopback rather than two physical hosts, and
power-loss/endurance/macOS evidence is not supplied. A signed exception remains
an exception, never an unqualified PASS. See `ACCEPTANCE.md`.

The historical NOT_RUN fields in the original contract archive are preserved as
source history. Current results live in the generated evidence, not rewritten
historical records. Migration support is specifically 0.1.0/schema 1; earlier
unidentified standalone recorders are not silently imported.

## Per-gate disposition

| ID | Original title | Executed local tests | Local result | Deployment disposition |
|---|---|---:|---|---|
| G01 | Canonical path safety | 11 | PASS | NEEDS_REVIEW |
| G02 | Preserve original protections | 6 | PASS | NEEDS_REVIEW |
| G03 | Intent revision authority | 3 | PASS | PASS_IN_DECLARED_PROFILE |
| G04 | Requirement preservation | 3 | PASS | PASS_IN_DECLARED_PROFILE |
| G05 | Reopen scope | 6 | PASS | PASS_IN_DECLARED_PROFILE |
| G06 | Typed domain records | 9 | PASS | PASS_IN_DECLARED_PROFILE |
| G07 | Completion gate consistency | 4 | PASS | PASS_IN_DECLARED_PROFILE |
| G08 | Evidence candidate binding | 6 | PASS | PASS_IN_DECLARED_PROFILE |
| G09 | Admission dependencies | 1 | PASS | PASS_IN_DECLARED_PROFILE |
| G10 | Context mandatory coverage | 5 | PASS | NEEDS_REVIEW |
| G11 | Superseded-memory adversary | 1 | PASS | PASS_IN_DECLARED_PROFILE |
| G12 | Forced context reset | 4 | PASS | PASS_IN_DECLARED_PROFILE |
| G13 | Effect write-ahead | 8 | PASS | NEEDS_REVIEW |
| G14 | Command idempotency | 8 | PASS | PASS_IN_DECLARED_PROFILE |
| G15 | Functional vertical slice | 3 | PASS | NEEDS_REVIEW |
| G16 | Informational impostor | 1 | PASS | NEEDS_REVIEW |
| G17 | Fake-success and backend loss | 2 | PASS | NEEDS_REVIEW |
| G18 | Independent concurrency | 7 | PASS | PASS_IN_DECLARED_PROFILE |
| G19 | Conflicting resource writes | 10 | PASS | NEEDS_REVIEW |
| G20 | Concurrent source invalidation | 3 | PASS | PASS_IN_DECLARED_PROFILE |
| G21 | Cross-repository observation | 1 | PASS | PASS_IN_DECLARED_PROFILE |
| G22 | Cross-repository candidate vector | 1 | PASS | NEEDS_REVIEW |
| G23 | Partial integration recovery | 1 | PASS | NEEDS_REVIEW |
| G24 | Provider discovery and lifecycle | 17 | PASS | PASS_IN_DECLARED_PROFILE |
| G25 | Rate-limit handoff | 3 | PASS | PASS_IN_DECLARED_PROFILE |
| G26 | Process and stale worker recovery | 11 | PASS | PASS_IN_DECLARED_PROFILE |
| G27 | Partition discipline | 10 | PASS | NEEDS_REVIEW |
| G28 | Privacy and export restore | 10 | PASS | NEEDS_REVIEW |
| G29 | Bounded hot-path performance | 4 | PASS | NEEDS_REVIEW |
| G30 | Migration and final acceptance | 27 | PASS | PASS_IN_DECLARED_PROFILE |
| G31 | Exact source and diagnostic provenance | 11 | PASS | PASS_IN_DECLARED_PROFILE |
| G32 | Patched storage and explicit durability preflight | 3 | PASS | NEEDS_REVIEW |
| G33 | Connection lifecycle under failure | 2 | PASS | NEEDS_REVIEW |
| G34 | Atomic preparation and artifact publication | 9 | PASS | PASS_IN_DECLARED_PROFILE |
| G35 | Out-of-order and late authenticated receipts | 8 | PASS | PASS_IN_DECLARED_PROFILE |
| G36 | Cancellation and authorization-change race | 4 | PASS | PASS_IN_DECLARED_PROFILE |
| G37 | Deduplication expiry and ambiguous absence | 3 | PASS | NEEDS_REVIEW |
| G38 | Event replay and schema evolution | 7 | PASS | PASS_IN_DECLARED_PROFILE |
| G39 | Backup restore cannot resurrect authority | 7 | PASS | NEEDS_REVIEW |
| G40 | Action-context freshness and actual delivery | 8 | PASS | NEEDS_REVIEW |
| G41 | Capability and information-boundary bypass | 16 | PASS | NEEDS_REVIEW |
| G42 | Acceptance oracle and verifier integrity | 13 | PASS | NEEDS_REVIEW |
| G43 | Fairness and bounded recovery scheduling | 5 | PASS | PASS_IN_DECLARED_PROFILE |
| G44 | Uninstrumented performance and scrub contract | 1 | PASS | NEEDS_REVIEW |
| G45 | Capture race and candidate completeness | 5 | PASS | NEEDS_REVIEW |
| G46 | Historical evidence and signed trust boundary | 7 | PASS | PASS_IN_DECLARED_PROFILE |

## Remaining boundaries, unchanged by passing local tests

### G01

Local POSIX path/capture tests; macOS case-insensitive filesystem execution is not certified.

### G02

0.1.0 compatibility and migration are executed against the archived wheel. The earlier standalone audited recorder and its original 48-test suite are unavailable; equivalence to that older lineage is not certified.

### G10

Mandatory source/intent/obligation inclusion and budget failure are tested; actual model ingestion is not observable.

### G13

Several real/deterministic crash boundaries exercised; not physical power loss or every external adapter.

### G15

Real fixture application and durable SQLite readback/restart; no user browser/UI deployment.

### G16

A prose-only Python application impostor fails; no browser-page adapter tested.

### G17

Hardcoded success and backend loss fail the real fixture oracle; not the user production application.

### G19

Local hierarchical resource fences and stale acceptance rejection; no enforced Git/deployment publisher.

### G22

Multiple repository inputs captured in one vector; not an assembled deployed multi-repo application.

### G23

Partial two-resource effect recovery tested, not interrupted Git publication/deployment across repos.

### G27

Opt-in mutual-TLS remote-worker transport to ONE authority; real loopback partition/lost-reply tests. Not a physical two-host or active-active controller certification.

### G28

Scope checks, secret rejection and key-free backup tested; external one-authority enforcement needs operator fencing.

### G29

Incremental hot-path tests and bounded contention samples; not huge-history or 24-hour endurance certification.

### G32

Known unpatched WAL rejected; actual run uses rollback fallback. Patched WAL library was not installed/exercised here.

### G33

Connections close on tested success/failure/rollback paths with ResourceWarnings promoted to errors; no long soak.

### G37

Ambiguous file absence and unknown commands hold safely; no destination idempotency-TTL adapter.

### G39

Restore new local key/generation + recovery hold; external original-authority fencing is an operator attestation.

### G40

Actual serialized RPC context body is bound; hidden model prompts/compaction remain outside observation.

### G41

API scope checks only; same-UID code, filesystem/network and provider transfers are not sandboxed.

### G42

Immutable registered real oracle rejects skips/zero/fail/timeouts; malicious same-UID code can bypass OS-level isolation.

### G44

Raw benchmark intervals avoid full scrub; startup/manual scrub exists, periodic enforcement is operational.

### G45

Two stable full-source passes plus dirty/untracked/mode capture; not an atomic filesystem snapshot.

## Exact candidate

Runtime/source digest: `54eb245203e922561f8b8fd1cf8c078367f8794c752739ec67d8b4f5c63411d1`.

Test-tree digest: `52ab3ccde8deae3ec209e44d0cd3bc587c4c31d2842796da50fb742917cd8c11`.

Policy digest: `c8d07a8950051899bd67bbb8d04e5e75ac32e23b9a1cd23490d88d2dd246f173`.

No manual PASS records were used. Reproduce with the installation handoff.
