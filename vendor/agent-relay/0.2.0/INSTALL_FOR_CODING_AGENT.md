# Coding-agent installation handoff — Agent Relay 0.2.0

## Outcome and safety boundary

Install the supplied NEW version alongside the prior runtime. Verify the actual
installed wheel and all tests. Then choose either a NEW control store or the
explicit supported **0.1.0/schema-1 migration**. Never autodiscover, overwrite or
"upgrade" an unidentified `relay.db`. Never change branches, replace the owner's
Agent.md, or modify another agent's native configuration without approval.

The distribution is `agent-relay`, import namespace `agent_relay`, executables
`relayctl`, `relay-doctor`, and **`relay-mcp`**. This is the existing 0.1.0 code line
extended to 0.2.0, not another parallel redesign. `compat/` retains the exact prior
wheel and tests. No existing user database was opened during package construction.

## 1. Verify before importing code

Compare the ZIP checksum from the delivery channel. After extraction:

```sh
python3 tools/verify_package.py
```

Read `evidence/RELEASE_VERIFICATION.json`, `docs/GATE_STATUS.md` and
`docs/SECURITY_AND_SCOPE.md`. Integrity hashes are not publisher signatures.
Use Python 3.11+ with venv, ensurepip and SQLite. The complete test suite also needs
an `openssl` command that supports the disposable EC-certificate commands used in
`tests/integration_support.py`; the verified environment uses OpenSSL 3.5.5.
Do not silently skip TLS tests when that command is missing.

## 2. Offline additive installation

```sh
python3 tools/install.py --prefix "$HOME/.local/share/agent-relay/0.2.0"
P="$HOME/.local/share/agent-relay/0.2.0"
"$P/bin/relayctl" --version
"$P/bin/relayctl" adapter-info
```

The installer refuses an existing prefix, uses the included wheel with
`--no-index --no-deps`, confirms import origin, and runs a disposable installed
crash/recovery self-test. It does not open a live store, migrate, install autostart,
change provider configuration, or request a model/API credential. A failed install
leaves only its newly created prefix for inspection.

## 3. Reproduce installed and prior-interface checks

```sh
"$P/bin/python" tools/run_checks.py --expect-installed --out /tmp/relay-020-acceptance
"$P/bin/python" tools/run_legacy_checks.py --out /tmp/relay-020-compatibility
```

Run from the extracted package directory. Do not add `src` to PYTHONPATH in
installed mode. The first command records before/after runtime, test and runner
hashes and rejects any test failure, skip or cleanup error. The second executes
the byte-preserved original **111-test 0.1.0 suite** against installed 0.2.0 in an
isolated subprocess. It is not the unavailable earlier standalone 48-test suite.

## 4A. NEW store: explicit initialization

```sh
H="$HOME/.local/share/agent-relay/control-v2"
"$P/bin/relayctl" --home "$H" init
"$P/bin/relayctl" --home "$H" doctor --scrub
"$P/bin/relayctl" --home "$H" serve
```

Choose a short local path: including `/relay.sock` it must be under 100 bytes.
An existing directory is refused. Keep the control store outside worktrees,
network shares and cloud-synced folders. Run as the owner, not sudo. Autostart and
`serve --auto-dispatch` are separate explicit operator choices. By default only an
operator dispatch request executes a prepared effect.

Register the real directive, requirements, current Agent.md/ADRs/contracts,
repositories, protected verifier, scoped tasks and worker grant as in `docs/API.md`.
The disposable `examples/bootstrap_application.py` demonstrates a complete app.

## 4B. Existing 0.1.0 store: staged upgrade, never overwrite

Stop the old service and its autostart, preserve a verified backup and keep its
0.1.0 installation available. Confirm the source really is this package's schema 1.
Select an absent destination outside the old store:

```sh
OLD="/absolute/approved/old-control"
NEW="/absolute/approved/new-control"
"$P/bin/relayctl" migrate plan --source "$OLD" --destination "$NEW"
"$P/bin/relayctl" migrate prepare --source "$OLD" --destination "$NEW"
```

`prepare` holds the old authority, changes its worker generation, copies through
SQLite backup, preserves all historical event/blob bytes, appends a migration
record, and publishes a new-key **RECOVERY_ONLY** target. Nothing is dispatched.
Do not start both stores as active authorities. Read `docs/MIGRATION.md` before
reconciliation or activation. A preactivation rollback is explicit:

```sh
"$P/bin/relayctl" migrate rollback --source "$OLD" --destination "$NEW"
```

Rollback retires the target and returns the source to recovery-only; it does not
silently restart old work. Rollback after activation or later target commands is
refused to protect newer evidence/effects. Earlier standalone schemas are rejected.

## 5. Connect the installed provider adapter

Read `docs/ADAPTERS.md`. Register `mcp-stdio-v1` against the owner's canonical
Agent.md source. Issue a narrow worker token to a private file. Give the provider
only that token, never `owner.key`. The adapter is launched by the provider as:

```sh
"$P/bin/relay-mcp" --home "$H" --token-file /absolute/private/worker.token --adapter coding-agent
```

The command speaks MCP on stdin/stdout; it is not an interactive shell command.
The actual vendor's client configuration starts it. It provides durable sessions,
claim/hydrate/acknowledge/prepare/reset/release and scoped reads. It does not replace
or bypass native provider permissions. Its own protected tools require current
context; hidden vendor compaction and native shell calls are NOT observed.

## 6. Optional remote workers

`docs/NETWORK.md` describes the opt-in mutual-TLS listener. Keep ONE authority and
its database local; provision CA-issued server/client certificates, authorize each
client certificate fingerprint against its worker grant, and keep administration
on the local socket. A remote `relay-mcp --remote-config ...` connects without any
local Relay database. Mutations require stable command IDs. No blind retry or
independent offline write authority is provided.

## 7. Evaluate deployment acceptance, do not relabel results

```sh
"$P/bin/relayctl" certify --evidence /tmp/relay-020-acceptance/verification.json \
  --policy contracts/LOCAL_GATE_POLICY.json --output /tmp/relay-020-evaluation.json
```

Exit 3 is a review/evidence hold. Test failures cannot be waived. Remaining
boundaries need explicit candidate-bound, expiring reviewer decisions, described
in `docs/ACCEPTANCE.md`. No decisions are preapproved. `migrate activate` invokes
this same evaluator before it can release recovery mode; it also requires that
uncertain historical actions have been reconciled.

## Report back

Provide version, wheel/runtime/source/test/runner hashes, installed module path,
Python/SQLite/OpenSSL versions, exact counts, per-gate test references, explicit
reviewed exceptions and target-host adapter/network observations. Include no
credentials. Preserve the original contract text. Do not call loopback fault tests
physical multi-host certification or process exit physical power-loss testing.
