# Capability Creation — build/refine the capability a checklist item needs

> A skill DESCRIBES; a tool/MCP/plugin DOES. When the production-readiness checklist
> needs an executable capability we lack, **create it**; when it's weak, **refine it.**
> The checklist drives capability creation, not just grading. Born from MISS-002
> (skill-coverage was read as capability — 367 skills, ~6 read-only MCP tools).

## The maturity ladder (a capability must climb it)
`DESCRIBED` (skill only) → `ROUTED` (skill wired to a command) → `EXECUTABLE` (tool/
command/service implemented) → `WIRED` (probe-verified CALLED at runtime) → `TESTED`
(WIRED + regression). **`capability_status: HAVE` requires WIRED+** — never just DESCRIBED.

## When to use
A corpus item's `capability_status` is MISSING/PARTIAL; a probe reports a capability not
WIRED; an existing tool/skill is weak; you're asked to make the platform DO something
(not just describe it).

## Workflow
1. **find-before-create.** Search `capabilities/registry.yaml`, `skills.registry.yaml`,
   MCP `server-factory.ts` TOOL_LIST, and `commands.registry.yaml` for an existing
   capability first (`SKILL_FIND_BEFORE_CREATE_001`).
2. **Pick the creation path** by capability type:
   - **Skill (knowledge):** copy a `platform/systems/50_skill_os_templates` template →
     register in `skills.registry.yaml` → route in `trigger_router.yaml` →
     `validate_skill_router_integration.py`.
   - **MCP tool (executes):** `SKILL_MCP_TOOLING_AUTOMATION_001` → add a TOOL_LIST entry
     + a `handleTool` case in `apps/backend/mcp/src/server-factory.ts` (import a real
     function from `src/tools/<name>.ts`).
   - **Slash-command/plugin:** add to `commands.registry.yaml` + a router rule + an
     owning skill.
   - **Service / API route:** `SKILL_NEW_PLATFORM_SERVICE_001` / a Next route under
     `apps/frontend/shell/src/app/api`.
3. **Build REAL code.** No stub, no demo payload, no TODO. Write capabilities must be
   path-confined (no traversal), tenant-scoped where a tenant applies, input-validated;
   destructive/remote actions require an explicit confirm flag (e.g. a git tool defaults
   to commit-only, pushes only with `push:true`).
4. **Register it.** Add a `CAP_*` to `capabilities/registry.yaml` (owning skill, executor,
   source file, `probe`, status).
5. **Probe-verify WIRED.** Write/extend a probe (or a verify script that prints success
   / a `wired_audit` run) proving the capability is actually CALLED at runtime — not just
   present. Only then flip the corpus `capability_status` MISSING→HAVE, **because the
   probe passed**, never by hand.
6. **Refine, don't duplicate.** A weak capability gets hardened (version bump / better
   validation), logged in its ledger — not replaced by a parallel copy.

## Worked example (this build)
ATLAS lacked the user-named write capabilities. Built as real probe-verified tools:
- `CAP_REPO_GIT_WRITEBACK` → `atlas_repo_commit_push` MCP tool + `POST /api/repos/[id]/commit`
- `CAP_REPO_FILE_WRITE` → `atlas_repo_file_write` MCP tool + `POST /api/repos/[id]/files`
- `CAP_KNOWLEDGE_NOTE_WRITE` → `atlas_knowledge_note_write` + `POST/PUT /api/knowledge`
Each has a `verify_*.mjs` runtime check; its `capability_status` flips to HAVE only when
the probe confirms WIRED.

## Anti-patterns
| Anti-pattern | Correct move |
|---|---|
| "We have a skill for X, so X is covered" | Skill = knowledge; build the executor; probe-verify WIRED |
| Ship a demo/stub route, call it built | Real runtime-callable code + verify script prints success |
| New capability duplicates an existing one | find-before-create first |
| Flip capability_status HAVE by hand | Flip only because a probe passed |
| Unsafe write tool (traversal / auto-push) | Path-confine, tenant-scope, explicit confirm flag |

## Related
`SKILL_DEFINITION_OF_DONE_GATE_001`, `SKILL_PRODUCTION_READINESS_AUDIT_001`,
`SKILL_MCP_TOOLING_AUTOMATION_001`, `SKILL_FIND_BEFORE_CREATE_001`,
`SKILL_WIRED_NOT_DEFINED_001`, `SKILL_IMPROVEMENT_LOOP_001`.
