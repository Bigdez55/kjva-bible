# Versioned migration and controlled rollback

## Supported lineage

Input: the supplied **Agent Relay 0.1.0, store/schema 1**, standard table layout.
Output: 0.2.0, store/schema 2, original event encoding/schema 1 unchanged.
No heuristic import of another `relay.py`, `.db`, native capability system or
unidentified standalone recorder. The exact original wheel is in `compat/`.

## Preparation

Stop the old daemon and autostart and take/verify an appropriate backup. Preserve
the old installation. Select a NEW destination outside the source; aliases into
the source and existing targets are rejected. Migration acquires both relevant
service locks as needed; it must not race a live service.

`migrate plan --source OLD --destination NEW` validates schema, integrity, event
chain, projections, receipts and stored blobs without changing DB contents.
`migrate prepare ...` then:

1. Writes a durable migration fence record and holds the old authority; rotates
   its worker generation without changing original event bytes.
2. Creates an unpublished target with a new owner key; copies a consistent SQLite
   backup, preserving committed source state and binary blobs.
3. Advances only store metadata to schema 2, rotates target generation, and holds
   the new authority in RECOVERY_ONLY.
4. Verifies the exact historical event-byte fingerprint and full replay; appends
   ONE migration record, with `historical_evidence_upgraded=false`.
5. Publishes the target by rename, retaining a migration manifest in both stores.

No model call, tool effect, publication, automatic acceptance or dispatch occurs.
A partial copy is held rather than treated as a successful cutover.

## Reconcile, evaluate, activate

The new authority may be started for recovery reads, late receipts, explicit
resolutions and revocation while held. Unknown effects remain UNKNOWN until
independent observation or a scoped owner resolution. Historical PASS records
remain historical and cannot certify changed code/oracles/candidates.

Run installed tests and `relayctl certify` with `contracts/LOCAL_GATE_POLICY.json`.
The runtime pins that policy; weakening a local copy is rejected. Review each
remaining boundary using the separate workflow in `ACCEPTANCE.md`. Failed or
missing tests cannot be waived. The migration command evaluates these exact
inputs again, not a manually edited readiness flag:

```sh
"$P/bin/relayctl" migrate activate --source "$OLD" --destination "$NEW" \
  --evidence /tmp/relay-020-acceptance/verification.json \
  --policy contracts/LOCAL_GATE_POLICY.json \
  --decisions /private/reviews/decisions.json --review-key /private/reviews/review.key \
  --reconciliation-report "Operator's actual inspection and effect-reconciliation record"
```

Activation also checks that the original authority is still held and unchanged,
that the target is recovery-only and that no unresolved historical action remains.
It revokes historical grants/releases historical attempts. Issue new scoped
worker credentials after activation. Keep the original store held and disable
its old service lifetime. An OS owner who intentionally reopens both authorities
is outside this cooperative single-authority trust boundary.

## Rollback

`migrate rollback --source OLD --destination NEW` is allowed before activation,
only when no later target command/receipt would be discarded. It checks the
original prefix and any migration suffix, including after an interrupted copy
with an unfinished marker. It first retires the target and rotates its generation;
then returns the original to RECOVERY_ONLY under another new generation.
No files/evidence are deleted. Use the archived 0.1.0 runtime for source recovery;
an operator must explicitly inspect/reconcile/resume it.

After target activation, or a later target receipt, rollback is refused. Preserve
both stores and recover forward. Restoring an old copy over newer evidence is not
a rollback. After an interrupted activation, inspect target mode/head first: a
committed activation is not repeated blindly and the original remains held.

Tests create source stores with the real archived wheel, migrate exact event/blob
bytes and real prior application-verifier PASS records, simulate interruption at
five boundaries, force real process exit during copy/publication, and prove safe
rollback/holds and rejection of unsafe late-receipt rollback.
