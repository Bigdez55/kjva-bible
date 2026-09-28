# ESS Agent Relay 0.1.0

**Installable, provider-neutral single-host execution-continuity runtime.**

This delivery contains executable source, an offline-installable wheel, regression tests,
a real process-death recovery demonstration, a coding-agent installation handoff, and
machine-generated evidence. It does not require a model, API key, cloud service, or third-party
runtime dependency. Python 3.11+ and linked SQLite 3.37+ on a local POSIX filesystem are required.

## Start here

Read `INSTALL_FOR_CODING_AGENT.md`. From the extracted package directory:

```sh
python3 tools/verify_package.py
python3 tools/install.py --prefix "$HOME/.local/share/ess-agent-relay/0.1.0"
```

The installer creates a NEW virtual environment, installs the included wheel without network
access, and runs the installed package's disposable recovery self-test. It refuses an existing
prefix. It does not initialize a live store, start a persistent service, create a global command,
change Git branches, migrate a database, or touch any previous Relay installation.

To initialize a new, separate operator-controlled store and run it in the foreground:

```sh
R="$HOME/.local/share/ess-agent-relay/0.1.0/bin/relayctl"
H="$HOME/.local/share/ess-agent-relay/control"
"$R" --home "$H" init
"$R" --home "$H" serve
```

Use a second terminal for `"$R" --home "$H" doctor --scrub` and commands. `serve` is manual-dispatch
by default; `serve --auto-dispatch` explicitly allows the service to dispatch already-authorized
prepared actions serially. Neither mode starts an AI agent.

## What actually executes

* Durable immutable event journal, transactional projections/outbox, command idempotency,
  scoped expiring HMAC worker credentials, explicit operator decisions, and typed requirements.
* Independent tasks, dependency checks, hierarchical resource leases, attempt fencing,
  renew/release, and a least-attempted ready-work selector.
* Task-specific context containing current owner intent, approved sources, open obligations,
  unknown effects, and evidence handles. Worker memories cannot make themselves instructions.
* Managed compare-and-set file writes, fixed operator-approved process recipes, bounded subprocess
  execution, durable pre-effect state, receipt deduplication, and conservative reconciliation.
* Exact source/candidate manifests, multi-repository revision vectors, immutable registered
  unittest oracles, real subprocess test execution, and evidence-bound acceptance.
* Private Unix-socket service, CLI and Python client, integrity doctor, offline backup,
  recovery-held restore, event replay, and lossless compressed content-addressed blobs.

The journal is authoritative; snapshots are optional derived artifacts. Stored bodies are UTF-8
and conditionally zlib-compressed, referenced by SHA-256 and read only when needed. UTF-32 is not
used as a supposed compression mechanism. There is no model-state serialization claim, bespoke
kernel dependency, automatic semantic memory promotion, or automatic log deletion.

## Trust and deployment profile

This version is **single host, one operator-owned service, trusted/cooperating local workers**.
Worker API capabilities prevent accidental or API-level cross-workflow escalation. They do not
isolate malicious Python, commands, or another process running as the SAME OS user who can read
`owner.key`. The process supervisor is not a sandbox. Do not expose the Unix socket through a
network proxy or execute untrusted repositories/oracles without an external isolation layer.

The managed-file adapter can establish that the desired bytes exist; it cannot prove which
process originally wrote them. Generic commands with uncertain outcomes are held for operator
reconciliation, never automatically retried. This is not universal exactly-once execution.

Source capture performs two stable passes, not an atomic filesystem snapshot. Accepted candidates
are not automatically merged, pushed or deployed. Native provider lifecycle hooks, hostile-code
isolation, distributed authorities, physical power-loss behavior and legacy migration are not
certified or silently substituted with mocks. See `docs/SECURITY_AND_SCOPE.md`.

## SQLite behavior

`--journal auto` selects WAL only when the linked library matches the documented fixed-version
allowlist. Otherwise it selects DELETE rollback journaling with `synchronous=EXTRA`. Explicit WAL
on a known unpatched build is rejected. Connections are closed explicitly and configuration is
read back. The shipped evidence states the actual selected mode; a safe fallback is not a WAL
certification. Use a local filesystem, not NFS/SMB or a cloud-synced control directory.

## Verification and traceability

`evidence/verification.json` records individual executed tests, source/test hashes, environment,
installed module path and failures. `evidence/gate_coverage.json` maps them back to the unchanged
46 original contracts in `contracts/ORIGINAL_G01_G46.json` without renumbering or weakening them.
Local tests are not automatically promoted to full original gate passes.

`evidence/installed_selftest.json` records actual socket-service restart, executor and controller
SIGKILL after a durable effect but before its receipt, independent-task progress, cold manual-client
handoff, stale-fence rejection, application persistence verification and acceptance.
`evidence/stress.json` and the matching CSV record the duration, load, operation counts and raw
latencies of the bounded contention run. They are not a 24-hour soak or power-loss test.

See `docs/API.md`, `docs/RECOVERY.md`, `docs/ARCHITECTURE.md`, and the installation handoff.
