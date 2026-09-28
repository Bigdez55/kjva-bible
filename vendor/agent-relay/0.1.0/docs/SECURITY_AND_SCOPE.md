# Supported boundary and remaining work

## Supported and tested here

One local operator-owned service, private Unix-domain socket, transactional SQLite state, bounded
cooperating local clients and commands, independent tasks, revision/fence checks, managed file
compare-and-set, scope-checked context, real protected-by-API verifier registration and execution,
process-crash recovery, explicit backup/restore hold, and fail-closed source/evidence validation.
All execution evidence is in `../evidence/`, including the environment and package hash.

## What the local permission model does NOT protect against

The owner OS account is trusted. Another process running as that account may read the private key,
rewrite files, invoke direct library calls, or tamper with an oracle subprocess. Worker capabilities
protect API use, not the kernel or an administrator. The generic recipe process supervisor limits
argv, environment, time and output; it does not block arbitrary filesystem/network effects of its
registered executable. The unittest runner is not safe for hostile code. Do not give this service
unreviewed scripts, dependencies, repositories or test oracles.

To operate with hostile agents or multiple OS principals, first implement and test separate process
identities, service credentials unavailable to workers, external filesystem/network isolation and
signed/attested verifier receipts. That is not a configuration toggle in this version.

No TCP listener, HTTP transport, multi-host authority or active-active coordination is provided.
A proxy would enlarge the trust boundary and is unsupported. The local `flock` is not a distributed
lease or consensus algorithm. Local filesystems only; SQLite guarantees must not be extrapolated to
NFS, SMB, unreliable flash or arbitrary filesystems.

## Effect semantics

Only `file.write` and fixed operator-approved `command` recipes are implemented. A managed file
write records intent and payload before dispatch, checks the expected digest, publishes by rename
and fsync, then reads back. Recovery equality proves the desired state currently exists. It is not
proof of causal writer identity, nor an atomic transaction with an external service.

A command exit code is a transport/execution observation, not application acceptance. Command
failure/timeout or interrupted dispatch remains UNKNOWN unless a before-spawn failure is known.
There is no automatic unknown-command replay or invented HTTP deduplication contract. Local command
request dedup records are retained; there is no implemented remote idempotency TTL adapter.

## Capture and verifier limits

Every approved repository's files (including dirty/untracked/binary/mode information) are bounded
and read twice. Source changes between passes are rejected, but a two-pass capture is not an atomic
filesystem snapshot. Default excluded components: inspect `workspace.SKIP_DIRS`; exclusions
are stored in the manifest. Symlinks, hardlinks, unsafe names, secret-like files and case aliases are
rejected rather than followed. Limits: 5000 files, 16 MiB per file, 64 MiB total per capture. File
writes require existing safe parent directories. Repo roots may not overlap another registration.

Verifiers are immutable registered unittest sources and run against staged candidates. This version
requires real collected tests and rejects skipped/expected-failure/timeout/zero-test results. It does
not prove an arbitrary oracle expresses every user requirement. The owner must approve a meaningful
oracle. Requirements and tests cannot be silently dropped. No browser, deployment, or automatic
Git merge/ref-promotion adapter is provided. Acceptance is a Relay decision, not publication.

## Store, retention and restoration

Blobs are SHA-256 addressed, losslessly compressed when useful and bounded on decode. Default blob
payload quota is 1 GiB. Event-body quota is 256 MiB with a 64 MiB logical recovery reserve; new work is
held at quota. These are logical quotas, not exact disk-size/RSS bounds. Filesystem free space must
be monitored independently. Exhausting all physical disk may still prevent receipt persistence.
History is retained; no automatic archival/delete/rewrite compaction is implemented. A snapshot does
not remove events. Doctor scans full history/blobs only when explicitly requested and at daemon startup;
schedule periodic scrubs operationally. Heartbeats do not run a full history scrub.

Restore creates a NEW key and generation and starts RECOVERY_ONLY. It does not revoke an original
controller still running elsewhere, or revoke cached external credentials. The operator must stop/fence
that original authority outside this package and reconcile post-backup effects before releasing the
restore. The release explicitly records the attestation; it is not proof of external enforcement.
Original registered repository paths are retained. There is no transparent filesystem relocation or
legacy schema migration. Replay repairs projections from an intact journal; it cannot reconstruct
missing/corrupt journal bytes or blobs.

## Evidence limits

Executed platform details are in the reports. POSIX/macOS-targeted source is not a Mac hardware test.
SIGKILL leaves the operating system running; it is not physical power removal. The short contention
run is not a one-hour/8-hour/24-hour soak. Native provider startup, tool interception, compaction,
rate-limit behavior and live existing workspace integration have not been certified.

Unkeyed hash chains and manifests detect accidental inconsistency, not an attacker able to rewrite
both data and trust roots. These artifacts are not cryptographically signed publisher attestations.
