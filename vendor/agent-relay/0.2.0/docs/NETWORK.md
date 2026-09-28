# Optional remote workers: one authority, mutual TLS

Topology: workers on local/remote machines connect to ONE Relay service. Its
SQLite database stays on a local filesystem. No worker owns a replica, consensus
node, offline write queue or autonomous failover authority. The same service lock
covers Unix and TLS listeners. There is no active-active or network-filesystem mode.

## Provision before exposing a listener

Use an operator-managed private CA and per-worker client certificates. The server
certificate must contain the hostname/IP used by the client. Server and client
require TLS 1.3 and mutual certificate verification. Client identity is additionally
bound to a current Relay worker grant by SHA-256 of its DER certificate. Keep
private keys and configuration files owner-only, use short-lived certificates,
restrict network reachability, and revoke a peer/grant when retiring a worker.
This package does not operate a CA, auto-renew certificates or implement OCSP.

Server configuration (all paths absolute, JSON file/key owner-only):

```json
{"version":1,"host":"127.0.0.1","port":9443,"cert":"/private/tls/server.pem","key":"/private/tls/server.key","ca":"/private/tls/ca.pem"}
```

Use a deliberately approved interface address for other hosts; localhost is safer
for initial checks. Start explicitly:

```sh
"$P/bin/relayctl" --home "$H" serve --tls-config /private/tls/listener.json
```

The private `network.status.json` records the actual bound port and authority ID.
Operator commands remain on the local Unix socket. Authorize a client fingerprint:

```sh
openssl x509 -in /private/tls/worker.pem -outform DER | openssl dgst -sha256
"$P/bin/relayctl" --home "$H" call peer.register --command-id peer-register \
  --data '{"fingerprint":"REPLACE_WITH_64_LOWERCASE_HEX_DIGEST","grant":"coding-worker"}'
```

The digest is public identity material, not the private key. Each peer certificate
is bound to one grant. A fresh certificate/grant is the rotation path. Revocation:

```sh
"$P/bin/relayctl" --home "$H" call peer.revoke --command-id peer-revoke \
  --data '{"fingerprint":"REPLACE_WITH_64_LOWERCASE_HEX_DIGEST","reason":"Worker retired"}'
```

## Worker configuration

```json
{"version":1,"host":"relay.internal","port":9443,"server_name":"relay.internal","cert":"/private/tls/worker.pem","key":"/private/tls/worker.key","ca":"/private/tls/ca.pem","token_file":"/private/worker.token"}
```

```sh
"$P/bin/relayctl" remote --config /private/worker-tls.json version
"$P/bin/relay-mcp" --remote-config /private/worker-tls.json --adapter coding-agent
```

Never copy `owner.key`, relay.sqlite3 or a backup onto workers for offline writes.
Each remote request checks its worker token, generation, grant expiry/revocation,
peer fingerprint and task scope at the authority. Revocation is checked even on a
replayed command ID. A handcrafted owner token is rejected on the TLS listener.

## Partition rules and exact proof

A failed pre-send connection reports REMOTE_UNAVAILABLE. A lost response after
sending may have begun reports REMOTE_OUTCOME_UNKNOWN. The client does not silently
retry. Reconnect with the SAME logical command ID and exact payload to inspect or
obtain the recorded response; a changed payload is rejected. This command replay
is not permission to repeat an UNKNOWN external effect.

Only the authority's clock assigns/expires leases. A returning worker is checked
against current fences; an expired worker cannot renew, prepare a new effect, or
publish under an obsolete attempt. Eligible unrelated tasks continue independently.
No response or lease expiry is taken as proof of process death.

The included tests use real certificates, actual TLS handshakes, separate daemon
and MCP processes, a real dropped post-commit reply, reconnection, revocation and
stale attempt rejection. The fault proxy is test-only, not a production hook.
These were executed on one machine using loopback. Before a physical two-host
rollout, repeat from the actual worker host, verify hostname/CA and authority ID,
exercise an intentional network disconnection in staging, and retain that
host-specific evidence. Do not call loopback results physical two-host proof.
