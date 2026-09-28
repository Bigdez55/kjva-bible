# Implemented architecture

`service.py` exposes the bounded private RPC boundary; `controller.py` validates authorization,
requirements, dependencies, context revisions, leases, prepared actions and acceptance. `store.py`
commits immutable event bodies, current projections, dedup records, outbox state and referenced blobs
in one SQLite transaction. Every acknowledged object reference resolves to the same committed store.

`dispatch.py` durably marks sending and claims execution before invoking `workspace.managed_write`
or a fixed process recipe through `execution.py`. A second execution claim is rejected even when a
client repeats the original start request. Missing results remain UNKNOWN. Reconciliation and receipts
record observations separately from verification and acceptance.

`workspace.py` captures actual source bytes/modes and repository metadata into a candidate vector.
`verification.py` stages immutable candidates and registered oracle blobs and invokes
`verifier_worker.py` in a bounded subprocess. Accepted evidence identifies the runtime runner,
interpreter, candidate and oracle. Candidate freshness is checked again at acceptance. No model text
can call a public endpoint that directly records a verifier PASS.

`selftest.py` drives the actual daemon through its socket and performs process-death and application
persistence drills. Tests exercise both public RPC and direct transaction functions. The contention
benchmark uses a real service, eight worker processes and actual transaction requests, not a sleep
wrapped in a success report.

Runtime hierarchy: workflow → task → attempt → action. Stable requirement/decision/source objects are
shared within a workflow. Multiple workflows are supported; no extra program hierarchy is falsely
claimed. A provider field labels an attempt and is not a permanent mission owner. There is no model
runtime, external vector-search dependency, native kernel ABI dependency or hidden background agent.

Current scope is additive deployment. Neither audited historical code lineage was silently overwritten
or certified. `contracts/ORIGINAL_G01_G46.json` preserves the original contract text and historical
NOT_RUN record. New evidence is separate and records what this implementation actually executed.


## 0.2.0 extension, same controller

`adapters.py` / `mcp.py` add durable sessions and bounded MCP stdio tools. Context
acknowledgments and reset epochs are checked again in the controller; the wrapper
is not the only gate. `network.py` adds opt-in mTLS worker transport; credentials
and certificate/grant bindings are checked within each shared store transaction.
The local service lock owns both listeners; workers do not replicate authority.

`migration.py` stages actual schema-1 state into schema 2 without changing event
encoding or hashes. `certification.py` uses installed policy and exact executed
inputs; reviewed exceptions are explicit and never converted to passing tests.

CANDIDATE_MANIFEST.json pins executable/test/contract inputs before testing. It
excludes generated results to avoid a circular hash. MANIFEST.sha256.json later
seals the complete delivery, including those results. Both are unsigned integrity
records, not publisher or hardware attestation.
