# Coding-agent installation handoff — Agent Relay 0.1.0

## Required outcome

Install and validate the supplied executable package without replacing, downgrading or mutating
any existing Relay, agent, repository, branch, worktree, identity file or live state store.
The installed distribution is `agent-relay`; the import namespace is `agent_relay`; the CLI is
`relayctl`. This is a separate runtime, not an in-place repair or schema migration of an
unidentified earlier `relay.py` or `relay.db`.

Do not install into `byte`, overwrite `byte/relay`, `.byte-orchestration/runtime/relay.db`, or create
an additional model/orchestration tier. Do not make this service dependent on Byte either: its
contracts and client are provider-neutral. Existing gateways may integrate explicitly later.
Preserve the owner's existing `Agent.md` and native provider instructions; do not replace them with
this package's developer instructions.

## 1. Verify the package before execution

Use the provided outer ZIP SHA-256 to detect transfer damage. Compare it through the delivery channel.
After extraction, inspect `MANIFEST.sha256.json` and run:

```sh
python3 tools/verify_package.py
```

Hashes establish consistency, not a publisher signature or proof against an attacker who replaces
both the package and its manifest. This utility imports no package source before verifying it.
Read `evidence/verification.json`, `evidence/installed_selftest.json`,
`evidence/gate_coverage.json` and `docs/SECURITY_AND_SCOPE.md`.

## 2. Install offline into a NEW prefix

```sh
python3 --version
python3 tools/install.py --prefix "$HOME/.local/share/agent-relay/0.1.0"
```

Use Python 3.11 or newer with `venv`, `ensurepip`, and SQLite enabled. The installer uses only the
included wheel and stdlib. A missing `venv`/`ensurepip` fails with an actionable error; it does not
fetch packages or modify the operating system. Existing prefixes are refused. An unsuccessful
installation leaves its newly created prefix for inspection; it never deletes existing directories.

Installation verifies source and wheel hashes, installs with `--no-index --no-deps`, confirms the
import comes from the new prefix, and runs `relayctl selftest` against NEW disposable state. The
self-test deliberately kills its own disposable processes, not an existing Relay. Evidence is
written to `<prefix>/installation.json` and `<prefix>/installed-selftest.json`.

## 3. Validate from the installed package

```sh
P="$HOME/.local/share/agent-relay/0.1.0"
"$P/bin/relayctl" --version
"$P/bin/relayctl" selftest --output /tmp/relay-installed-check.json
"$P/bin/python" tools/run_checks.py --expect-installed --out /tmp/relay-acceptance
```

The output path for `selftest` must not already exist. `run_checks.py` imports the INSTALLED runtime
and uses the shipped tests; it does not add `src/` to the import path. It verifies package integrity
before importing the target. Inspect the recorded installed module path and all individual results.
Do not substitute counts from a different commit, interpreter, environment or binary.

## 4. Initialize only an explicitly selected NEW control directory

```sh
P="$HOME/.local/share/agent-relay/0.1.0"
H="$HOME/.local/share/agent-relay/control"
"$P/bin/relayctl" --home "$H" init
"$P/bin/relayctl" --home "$H" doctor --scrub
"$P/bin/relayctl" --home "$H" serve
```

`init` refuses an existing directory. Choose a short, local, owner-controlled path: the Unix socket
path including `/relay.sock` must be fewer than 100 bytes. Do not use a network mount, synced folder,
legacy state path, repository worktree, or removable drive whose loss is outside the approved profile.

Run `serve` as the owning OS user, not with sudo. Do not install autostart until the owner approves
that service lifetime. Stop with Ctrl-C/SIGTERM and run offline maintenance only after the service exits.
The default daemon does NOT dispatch effects without an operator `dispatch` request. Auto-dispatch
is an explicit optional switch for previously approved actions.

## 5. Establish actual authority and acceptance requirements

In a second terminal, use `examples/bootstrap_application.py` only with `--base` pointing to a NEW
disposable demo directory to see a complete client integration. For real work, register the owner's
actual directive, immutable requirements, current approved sources, repo roots and protected oracles;
then create narrowly scoped tasks and worker grants. See `docs/API.md` for exact payloads.

Keep `owner.key` out of agent context, process arguments, Git, screenshots, logs and provider uploads.
Create worker token files with the `token` command. Supply only the worker token to the cooperating
agent. Every retry of the SAME logical command must reuse its command ID and identical payload;
never reuse an ID for a different payload. Do not retry UNKNOWN external effects.

## 6. Existing installation integration is a separate controlled change

Identify the actual installed executable, package root, branch, commit, dirty files, database schema,
backup procedure and operating authority before proposing a bridge. Compare exact old interfaces
with the new RPC API. Original v1 tests and legacy store migration are not included in this delivery.
Never mark G02/G30 passed by running only these new tests. No existing DB should be opened just
because a file is named `relay.db`.

Connect existing agents through the public API in their existing operating roles. This runtime does
not supply Codex/Claude hooks, observe hidden compaction, or bypass existing tool permissions.
Expose only the scopes supported by the installed integration and record it as cooperative until an
actual external enforcement boundary is installed and tested.

## Report back with evidence, not a blanket maturity label

Record installed version and wheel hash, Python and SQLite versions, journal mode, installed import
path, test count and failures, self-test checks, control-home path (not credentials), integration
changes made, and remaining original gate gaps. Preserve the actual gate names and acceptance text.
A local PASS is not a physical-power-loss, multi-host, long-endurance or real-provider certificate.
