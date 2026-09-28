# RPC / CLI API version 1

All requests use a private Unix-domain socket. Use the supplied client rather than inventing a transport.
`relayctl --home HOME call OP --data @payload.json --command-id UNIQUE_ID`
For workers, put `--token-file /private/worker.token` before `call`. The owner credential is never printed.

Successful responses contain `{ "ok": true, "result": ... }`; rejected CLI commands exit 2 with a structured error. Each mutating logical request needs a stable command ID across retries. Identical ID/payload replays return the original result. Different payload with the same ID is rejected.

## Core commands

| Operation | Required payload fields | Optional fields |
|---|---|---|
| `workflow.create` | `directive`, `id` | `constraints` |
| `workflow.revise` | `directive`, `expected_rev`, `id`, `reason` | none |
| `workflow.cancel` | `id`, `reason` | none |
| `workflow.settle_cancel` | `id` | none |
| `requirement.add` | `id`, `text`, `workflow` | none |
| `requirement.dispose` | `decision`, `id` | none |
| `decision.create` | `id`, `operation`, `reason`, `target_id`, `target_kind`, `target_rev`, `workflow` | `ttl` |
| `source.put` | `expected_rev`, `id`, `source_kind`, `text`, `workflow` | none |
| `memory.add` | `id`, `origin`, `text`, `workflow` | none |
| `grant.create` | `id`, `workflow` | `ttl` |
| `grant.revoke` | `id` | none |
| `repo.register` | `id`, `root`, `workflow` | `exclude` |
| `repo.observe` | `id`, `revision` | none |
| `tool.register` | `argv`, `id`, `reason`, `repo`, `resources`, `workflow` | `allow_stdin`, `environment`, `timeout` |
| `task.create` | `id`, `requirements`, `resources`, `title`, `workflow` | `deps`, `repos`, `tools`, `verifiers` |
| `task.reopen` | `decision`, `id` | none |
| `task.claim` | `id`, `provider` | `ttl` |
| `work.next` | `provider`, `workflow` | `ttl` |
| `attempt.heartbeat` | `id` | `ttl` |
| `attempt.release` | `id`, `reason` | none |
| `context.hydrate` | `attempt` | `budget_bytes` |
| `action.prepare` | `args`, `attempt`, `context`, `id`, `type` | none |
| `action.start` | `id` | none |
| `action.receipt` | `details`, `id`, `outcome`, `receipt_id` | none |
| `action.resolve` | `decision`, `id`, `outcome`, `proof` | none |
| `task.accept` | `candidate`, `evidence`, `id` | none |
| `workflow.accept` | `id` | none |
| `snapshot.create` | none | none |
| `restore.resume` | `original_authority_fenced`, `reconciliation_report` | none |

Workers may use claim, work.next, heartbeat, release, context.hydrate, memory.add and action.prepare within their workflow; owner-only operations reject worker credentials. See the handlers for validation and allowed enums. Registrations are immutable unless an explicit revision operation exists. IDs are globally unique within each object kind.

## Service operations

`version {}` returns the authenticated runtime version. `status {"workflow":"w"}` returns current work,
open actions and active attempts. `get {"kind":"task","id":"t"}` exposes allowed scoped object types.
`work.ready {"workflow":"w"}` explains eligibility. `doctor {"scrub":true}` is operator-only.

`grant.token {"id":"worker"}` returns a sensitive credential to an operator. Prefer the safe CLI:
`relayctl --home HOME token worker --out /private/worker.token`. The file must not exist.

`verifier.register {"id":"oracle","workflow":"w","oracle_root":"/absolute/oracle","min_tests":3}`
captures real unittest source as an immutable protected-by-API oracle. It is operator-only. Supported
optional keys are `min_tests` (default 1) and `timeout` (default 60 seconds). An arbitrary verifier environment is not accepted. `candidate.capture
{"id":"c","attempt":"ATTEMPT_ID","context":"CONTEXT_ID"}` captures actual inputs for that current
attempt. `verify.run {"candidate":"c","verifier":"oracle"}` runs the real oracle and returns
`evidence` plus `report`. `action.dispatch {"id":"a"}` and `action.reconcile {"id":"a"}` are operator-only.

## A managed write

A task must include registered repo `app` in `repos` and a covering resource such as `repo/app`.
Prepare with worker credentials:

```json
{
  "id":"write-1", "attempt":"ATTEMPT_ID", "context":"CONTEXT_ID",
  "type":"file.write",
  "args":{"repo":"app","path":"note.txt","expected_sha256":"ABSENT","data_b64":"aGVsbG8K"}
}
```

For replacement, supply the SHA-256 of the exact existing bytes instead of `ABSENT`.
Data is base64 at the JSON boundary, decoded and losslessly stored as a bounded content-addressed blob.
Run `relayctl --home HOME dispatch write-1`; inspect its action/receipt. No generic file path or arbitrary
shell string can be supplied as a new command tool by a worker.

## An approved command recipe

An operator registers fixed argv, repo, resources and reason using `tool.register`. The registered
executable and file arguments are pinned; argv runs without a shell. Supply the tool ID on the task's
`tools` list. The worker prepares type `command` with `args={"tool":"TOOL_ID"}` and optional
`stdin` as a UTF-8 JSON string only when the recipe permits stdin. The command is still trusted code, not sandboxed.
Generic commands have no automatic remote deduplication or success/readback oracle.

## Acceptance

`task.accept` takes the task ID, candidate ID and list of actual evidence IDs. The controller derives
acceptability from requirements, dependencies, context versions, live source identity and executed
oracle results. A worker cannot manufacture verification evidence or register a weakened oracle.
`workflow.accept` additionally requires all tasks and outstanding requirements to be satisfied.

## Example

After starting a NEW explicit store, run:

```sh
/path/to/installed/bin/python examples/bootstrap_application.py \
  --home /absolute/control-home --base /absolute/NEW-demo-directory
```

The demo registers a real application, an independent three-test oracle, a worker and a task; it uses
the public socket API to capture, verify and accept actual durable behavior. No live source is imported.

