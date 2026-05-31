# Playbook: Trigger Router and Auto Invocation

## Skill ID
SKILL_TRIGGER_ROUTER_001

## Purpose
Route natural language to the correct Apex skill bundle without requiring users to remember skill IDs. The runtime model is verb-first, noun-refined, and single-surface across natural speech and `/atlas:*` aliases.

## Trigger Conditions
- User asks naturally for a build, audit, refactor, UI wiring fix, stale-doc reconciliation, or skill improvement.
- A command needs to infer required skills from intent.
- A trigger needs deterministic routing across root verb, noun branch, modifier, target, output, proof, and corrective layers.
- User asks to acquire missing skills or agents from `.claude` directories.
- User asks to invoke, use, run, activate, or apply all skills.
- User says this thread should create, improve, refine, or consolidate skills.

## Required Inputs
- User request or command text.
- Target repo, artifact, feature, or workflow when applicable.
- Current source-of-truth files and validation gates when available.

## Canonical Rules
- Preserve source-of-truth ranking.
- Do not claim completion without validation evidence.
- Record misses in the skill refinery ledger when discovered.
- Use `13_skills/skill_refinery/trigger_router.yaml` as the canonical catalog and `37_command_protocol/trigger_router.yaml` as the compiled runtime copy.
- Treat `/atlas:*` commands as aliases into the Atlas noun/target branch.
- Use proprietary names: Atlas Graph Engine and Atlas Knowledge Vault.
- Do not use external graph/vault product names as SUPER C Atlas subsystem names.
- Route `.claude`, agent-surface, and thread-refinery requests to their dedicated active skills.
- Treat `invoke all skills`, `use all skills`, `run all skills`, `activate all skills`, `all skills`, `all skills and agents`, `full skill stack`, and `universal skills` as universal skill invocation.
- Universal skill invocation activates portable capability coverage, not every imported project-specific skill or agent.
- Suppress project-specific constraints unless the target/domain explicitly binds them.
- Do not confuse external runtime `Skill(...)` tool availability with repository-native `SKILL_*.yaml` playbook availability.
- A `SKILL_*` entry that is not tool-callable must still be applied by reading its YAML/playbook when the router selects it.
- Machine-code emit constants are high-risk compiler artifacts. If the request mentions ARM64/AArch64 opcodes, instruction words, emit constants, LDUR/STUR/LDR/STR encoding, or emitted-constant SIGSEGVs, route to `SKILL_APEX_VERIFIED_MACHINE_ENCODING_001`.

## Universal Skill Invocation

When all-skills mode is active, route through the universal coverage matrix:

- Intake and trigger routing
- Context packet
- Truth-state check
- Planning and specs
- Architecture
- Build and implementation
- Data and retrieval
- Graph and knowledge
- Security and compliance
- Testing and proof
- Documentation and handoff
- Skill refinement

Do not treat `.claude/universal`, `.codex/universal`, or imported assistant folders as automatically universal. Those directories may contain project-specific assets copied into a common surface. Use them as available sources, then activate only portable skills plus project-specific skills bound by the current target.

Do not reduce all-skills mode to the current agent runtime's registered Skill tool list. Runtime-registered skills are optional callable helpers. The ATLAS canon lives in `13_skills/active/` and is applied as repository-native discipline when selected.

## Workflow

### Observe
- Identify the user goal, repo/project state, relevant sources, and required artifacts.
- Inspect code, docs, schemas, ledgers, or router config before making claims.
- Normalize slash-command aliases and natural-language variants into the same router text surface.

### Orient
- Map the request to selected root verb, noun branch, target, modifiers, proof triggers, corrective overrides, related skills, source-of-truth rank, and validation gates.
- Identify missing backbone components, stale docs, untested behavior, or recurrence risk.

### Decide
- Choose the smallest complete artifact set that satisfies the intent.
- Define outputs, tests, evidence, and stop rules before execution.

### Act
- Produce Triggered intents.
- Produce selected root, selected noun, selected target, active modifiers, active output contract, proof requirements, and corrective override.
- Produce Skill bundle.
- Produce universal skill coverage matrix when all-skills mode is active.
- Produce selected portable skills and suppressed project-specific skills when all-skills mode is active.
- Distinguish tool-called skills from repository-native playbooks applied as disciplines.
- Produce Required artifacts.
- Produce Validation gates.
- Update ledgers and regression cases if a miss or new failure pattern is discovered.
- For acquisition/refinery requests, distinguish raw preservation, normalized operational canon, router wiring, registry sync, and validation.

## Output Format
- Triggered intents
- Selected root
- Selected noun
- Selected target
- Active modifiers
- Active output contract
- Proof requirements
- Corrective override
- Skill bundle
- Required artifacts
- Validation gates

## Validation Checklist
- Source documents and current repo truth were checked.
- Required output sections are present.
- Router intents and related skills are recorded.
- `/atlas:*` aliases and natural Atlas phrases resolve through the same branch.
- Proprietary Atlas Graph Engine and Atlas Knowledge Vault names are used in semantic outputs.
- Agent-related acquisition covers `universal_agents`, `repo_agents`, `agent_memory`, `agent_sessions`, and root/coordination docs when the user asks for all agents.
- All-skills invocation covers portable capability classes and does not blindly load project-specific imported skills.
- Machine-encoding requests activate oracle-backed verification before any emitted constant lands.
- Project-specific skills are activated only when the target/domain binds them; otherwise they are listed as suppressed or out of scope.
- Thread-refinery closure checks whether new skills, improved skills, consolidated skills, ledgers, and regression cases are required.
- Tests or manual verification are listed honestly.
- Final report distinguishes proven, partial, and planned claims.

## Source Documents
- handoff_v7_repo_native
- handoff_v5_trigger_router

## Related Commands
- /apex:route

## Related Workflows
- 05_workflows/platform_build_auto_invocation.md
- 05_workflows/existing_repo_deep_audit.md
