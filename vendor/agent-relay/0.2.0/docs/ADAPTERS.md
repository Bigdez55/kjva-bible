# Installed provider adapter — mcp-stdio-v1

## Enable only implemented behavior

Only `mcp-stdio-v1` is registrable. Registration pins the installed adapter and
relevant gateway implementation hashes. A name such as `claude-native` is rejected,
not treated as an already working integration. Client-reported product/version
strings are unverified labels, not vendor attestation.

Against an already bootstrapped workflow `w` with current Agent.md source `identity`:

```sh
"$P/bin/relayctl" --home "$H" call adapter.register --command-id adapter-registration \
  --data '{"id":"coding-agent","workflow":"w","identity_source":"identity","implementation":"mcp-stdio-v1"}'
"$P/bin/relayctl" --home "$H" call grant.create --command-id worker-grant \
  --data '{"id":"coding-worker","workflow":"w"}'
"$P/bin/relayctl" --home "$H" token coding-worker --out /absolute/private/worker.token
```

The adapter refuses an owner key. It uses worker-scoped authority only. Each MCP
process opens one durable session. Normal EOF closes it and releases owned leases
but does not erase unresolved actions. Abrupt death needs lease expiry or explicit
operator recovery; it never implies that an external effect failed.

## Native client setup

The following use vendor-documented stdio launch syntax (sources in SOURCES.md).
They are installation instructions, **not a claim that those vendor binaries were
executed in the release environment**. Use absolute paths appropriate to the host.
Commands modify the selected client's configuration; run only with approval.

```sh
codex mcp add ess-relay -- "$P/bin/relay-mcp" --home "$H" \
  --token-file /absolute/private/worker.token --adapter coding-agent
claude mcp add --transport stdio ess-relay -- "$P/bin/relay-mcp" --home "$H" \
  --token-file /absolute/private/worker.token --adapter coding-agent
```

Check the actual client version, its MCP server listing, identity received,
tool listing and a disposable claim/hydrate cycle before authorizing real work.
For a remote worker, replace `--home ... --token-file ...` with
`--remote-config /absolute/private/worker-tls.json`. Do not configure the TLS Relay
RPC port as an MCP HTTP URL: the protocols are different.

## Wire and tool contract

Pinned MCP protocol: **2025-06-18**. UTF-8, newline-delimited JSON-RPC 2.0 over
stdio. Initialization/initialized notification precedes tools. Only protocol output
goes to stdout. Input and tool responses are bounded. No sampling/model API is
called. `resources/read` provides the current scoped `relay://identity`.

| Tool | Purpose |
|---|---|
| relay_status / relay_ready / relay_get | Scoped current state, eligibility and typed records |
| relay_claim | Claim task with authority-checked resource leases |
| relay_hydrate | Deliver exact current intent, sources, obligations and action state |
| relay_acknowledge | Acknowledge received `body_hash`; no claim of comprehension |
| relay_prepare | Prepare a supported effect under the acknowledged current context |
| relay_heartbeat / relay_release | Renew or release current owned attempt |
| relay_context_reset | Invalidate prior session context acknowledgments |
| relay_close | Close the session and release leases without losing effects |

All mutation tools require a stable `command_id`; identical retries return the
prior response without repeating the mutation. `tools/list` is the canonical JSON
schema. Capture, dispatch, verifier registration and final acceptance remain
operator-mediated as appropriate; an adapter cannot invent new authority tools.

Order: claim → hydrate → acknowledge actual body_hash → prepare. A context reset,
source revision change, disabled adapter, different attempt, stale lease or wrong
hash rejects protected preparation. These checks also run on the raw Relay API,
so bypassing the MCP wrapper does not bypass its context epoch.

## Enforcement classification

ENFORCED: the adapter's own API calls, task scope, current context, stale-worker
fences and transaction-time authority checks at Relay.
COOPERATIVE: the owning OS account and its authorized native commands.
NOT OBSERVED: vendor-private prompt truncation or hidden compaction.
NOT INTERCEPTED: separate provider-native shell, built-in tools and other MCP
servers. Disable or constrain them in the provider/OS when stronger containment
is needed. Never label an unsupported compaction hook as installed.

The shipped tests launch the actual installed MCP subprocess; initialize it,
exercise its tools, invalidate context, kill it, start a cold successor and verify
stale authority rejection. Tests over TLS use a remote-config-only adapter with a
nonexistent local control path and assert that no local store is created.
