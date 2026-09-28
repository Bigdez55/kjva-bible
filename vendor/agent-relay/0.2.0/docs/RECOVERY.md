# Operator recovery and maintenance

All commands name the separate control home explicitly. Never inspect an unidentified legacy DB.
`relayctl --home HOME status` reports open actions. `get action ID` and `get attempt ID` show durable
state. An expired attempt is not proof that its process died. PID records are observations, not safe
process-kill targets after PID reuse. Stop/fence the exact known process using its external supervisor.

## Lost acknowledgment

For a managed file action, use `relayctl --home HOME reconcile ACTION_ID`. It reads current bytes
without writing the file. Equality can settle desired-state achievement. Absence or different bytes
leaves UNKNOWN. Generic command actions cannot be automatically reconciled by guessing.

A scoped operator resolution requires a `decision.create` matching the action's CURRENT revision and
`operation="resolve"`, then `action.resolve` with that decision, an observed outcome and proof text.
This is an operator assertion, not independently verified test evidence. Inspect `docs/API.md` and
`controller.py` for exact fields. Never resolve to NOT_APPLIED merely because a response was lost.

Prepared but unsent actions can be stopped by workflow cancellation. Sent actions remain observable
and block final cancellation until settled. A valid late receipt remains ingestible after the worker
has lost authority. Conflicting receipts are quarantined. Release/reclaim preserves the task identity
and increases fences; stale worker mutations remain invalid.

## Restart, doctor and replay

Restart `relayctl --home HOME serve` after a process crash. A full scrub runs before requests are
admitted. No external effects are replayed. UNKNOWN effects must be reconciled first.

Stop the daemon before offline maintenance:

```sh
relayctl --home HOME doctor --scrub
relayctl --home HOME backup /absolute/NEW-backup-directory
relayctl --home HOME rebuild
```

`backup` and `rebuild` take the same local exclusive service lock and reject a running service.
Backup creates a NEW directory containing `relay.sqlite3` and `backup.json`, using SQLite's backup API, not an unsafe live copy of just the database file. It excludes
owner/worker secrets. Evidence data itself can still be sensitive; protect backup access.
`rebuild` restores current objects and request-dedup state from intact immutable events and validates
replay. It is not a remedy for lost journal/blob bytes.

## Restore

```sh
relayctl --home /absolute/NEW-control-home restore /absolute/backup-directory
relayctl --home /absolute/NEW-control-home serve
```

The new controller is RECOVERY_ONLY. Previous credentials are invalid in the restored instance.
Original registrations still name the original repository paths. Before `restore.resume`, independently
stop/fence the old authority and possible surviving effects, investigate writes since the backup,
settle ambiguous actions, and save a reconciliation report. Then submit:

```json
{"original_authority_fenced":true,"reconciliation_report":"Reference to the actual reviewed fencing and reconciliation evidence"}
```

Do not submit this attestation just to make the controller proceed. This release is local operator
recovery, not a distributed/nonrollback fencing service. An older backup cannot itself reveal every
external effect that happened after it was taken.
