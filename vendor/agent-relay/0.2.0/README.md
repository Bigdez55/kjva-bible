# Agent Relay 0.2.0

Installable, provider-neutral execution-continuity service. One authoritative
local database; cooperating local workers over a private Unix socket and optional
remote workers over mutual TLS. Python 3.11+, POSIX, standard-library runtime.
No LLM or provider API credential is required by Relay itself.

**Start with `INSTALL_FOR_CODING_AGENT.md`.** Install alongside 0.1.0, never over an
existing prefix or an unidentified live database. The offline installer starts
only disposable verification processes; no persistent service or migration is
performed implicitly.

## What changed

| Original gap | Executable implementation added |
|---|---|
| G24 — provider discovery/lifecycle | `relay-mcp`, the installed `mcp-stdio-v1` adapter: MCP initialization, canonical Agent.md identity, scoped tools, durable sessions, context-hash acknowledgments, explicit reset invalidation, graceful closure and cold successor recovery. |
| G27 — partition discipline | Optional TLS 1.3 mutual authentication, certificate-to-grant binding, owner-only administration kept local, transaction-time authorization, stable request IDs and no offline writable authority. Real socket tests drop a reply after commit and reject an old worker after lease turnover. |
| G30 — migration/final acceptance | Actual 0.1.0/schema-1 to schema-2 staged migration, byte-preserved history, source fencing, fresh target credentials, recovery-only destination, controlled rollback before activation, and a release-pinned candidate/evidence/reviewer acceptance evaluator. |

The event encoding remains schema 1; only the store/schema metadata advances to 2.
Migration never rewrites old event hashes or upgrades historical PASS records into
new-candidate evidence. The exact 0.1.0 wheel and its original test source are
retained in `compat/` for migration and compatibility verification.

## Runtime capabilities retained

Versioned owner intent and immutable requirements; explicit scoped decisions;
task dependency admission; resource leases and fencing; candidate-bound context;
write-ahead actions; managed file compare-and-set writes; bounded approved command
execution; receipt deduplication and uncertain-outcome holds; protected registered
unittest oracles; evidence-based completion; replay, backups and restore holds;
losslessly compressed content-addressed blobs; bounded request/response and journal
budgets; explicit integrity scrubs. These are working modules, not placeholders.

## Install and verify

```sh
python3 tools/verify_package.py
python3 tools/install.py --prefix "$HOME/.local/share/agent-relay/0.2.0"
P="$HOME/.local/share/agent-relay/0.2.0"
"$P/bin/python" tools/run_checks.py --expect-installed --out /tmp/relay-020-check
"$P/bin/python" tools/run_legacy_checks.py --out /tmp/relay-020-compat
```

The full suite uses the local `openssl` executable to generate temporary TLS test
certificates. Those certificates, keys and review keys are never shipped. Runtime
TLS uses Python's `ssl`, not the openssl command. See `evidence/RELEASE_VERIFICATION.json`
for the actual installed candidate, counts, results and unexecuted deployment work.

## Evidence is not a label-editing mechanism

The original `contracts/ORIGINAL_G01_G46.json` is unchanged, including its archived
NOT_RUN statuses. Current runs generate `evidence/verification.json` and
`evidence/gate_coverage.json`. Every gate has explicit test IDs in
`contracts/LOCAL_GATE_POLICY.json`, byte-identical to the installed policy.

`relayctl certify` rejects source-only runs, mismatched runtime/source/test/runner
bytes, omitted/failed/skipped tests, weakened policies and expired/forged/reused
reviews. Remaining deployment boundaries require explicit expiring review. A
reviewed exception is **EXCEPTED**, never relabeled PASS. No owner review or
production approval is pre-signed in this package.

```sh
"$P/bin/relayctl" certify --evidence /tmp/relay-020-check/verification.json \
  --policy contracts/LOCAL_GATE_POLICY.json --output /tmp/relay-020-evaluation.json
```

Exit 0 means ready in the stated profile with any required reviewed exceptions;
exit 3 means held for review or missing/failed behavioral evidence; exit 2 means
invalid inputs. A held evaluation is intentional, not a package-install failure.

## Actual supported boundary

Only `mcp-stdio-v1` can be registered as an implemented provider adapter. Its tools
are checked by Relay; a provider's separate native shell and private compaction
are not intercepted or certified. Actual Codex/Claude installations must be checked
on the target host. Network fault tests use real TLS and separate processes on one
machine, not two physical hosts. There is no active-active controller or replicated
SQLite mode. The authority's database must be on a local filesystem.

The owning OS account and approved commands are trusted. This is not a hostile-code
sandbox. HMAC review records protect local review integrity, not publisher identity
or proof of human authorship. No physical-power-loss, macOS hardware, 24-hour soak,
or unidentified pre-0.1 standalone-store migration certification is claimed.
An unpatched SQLite library uses rollback-journal EXTRA durability and rejects WAL;
it is not mislabeled as a patched-WAL run.

## Navigation

`docs/ADAPTERS.md` — provider setup and exact tool/session contract.
`docs/NETWORK.md` — remote worker topology, certificates and reconnect rules.
`docs/MIGRATION.md` — plan, staged migration, reconciliation, activation, rollback.
`docs/ACCEPTANCE.md` — pinned policy, reviewed boundaries and evidence semantics.
`docs/API.md`, `docs/RECOVERY.md`, `docs/SECURITY_AND_SCOPE.md` — retained API and limits.
`docs/GATE_STATUS.md` — generated per-gate executed evidence and remaining boundaries.
