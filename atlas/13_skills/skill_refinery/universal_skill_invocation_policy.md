# Universal Skill Invocation Policy

## Purpose

This policy fixes the ambiguity between acquiring assistant-surface assets and invoking skills at runtime.

`invoke all skills`, `use all skills`, `run all skills`, `activate all skills`, `full skill stack`, and `universal skills` mean: activate the portable skill coverage matrix required for the current task.

They do not mean: load every imported `.claude`, `.codex`, `.gemini`, repo-local, or project-specific skill and agent verbatim.

They also do not mean: call every skill registered in an external agent runtime's `Skill(...)` tool.

## Canonical Rule

All-skills invocation is a universal routing mode, not a literal exhaustive import.

The router must:

- Select portable capability classes first.
- Select project-specific skills only when the request names or implies that project/domain.
- Suppress project-specific constraints from unrelated repos.
- Report which skill families were activated, which were suppressed, and why.
- Preserve imported assistant assets as available sources, not universal runtime law.

## Tool-Callable vs Playbook-Callable Skills

Some agent runtimes expose a small set of tool-callable skills through a `Skill` tool or similar registry. ATLAS also contains a larger repository-native skill library under `13_skills/active/` as `SKILL_*.yaml` plus `.playbook.md` files.

These are different invocation surfaces:

| Surface | What it means | Correct action |
| --- | --- | --- |
| External runtime registered skill | A skill name visible in the current agent's tool list. | Call it only when it is relevant and safe. |
| Repository-native active skill | A `13_skills/active/SKILL_*.yaml` + `.playbook.md` discipline. | Read the YAML/playbook and apply its workflow; do not expect it to be callable through the external `Skill` tool. |
| Imported assistant skill | A raw or normalized `.claude`, `.codex`, or `.gemini` asset. | Treat it as source evidence until promoted or target-bound. |

If a runtime says `SKILL_IPOS_TURBO_001` or another `SKILL_*` name is not tool-callable, that is not a failure to invoke the skill. The correct behavior is to apply the repository-native playbook discipline by reading its YAML/playbook through the filesystem.

Never reduce `invoke all skills` to the external runtime's registered skill list. That list is runtime-local and incomplete relative to ATLAS.

## Universal Coverage Matrix

When all-skills mode is active, cover these skill families:

| Family | Purpose |
| --- | --- |
| Intake and trigger routing | Parse intent, root verb, noun branch, modifiers, target, proof, and corrective signals. |
| Context packet | Gather relevant sources, repo state, prior decisions, constraints, and target scope. |
| Truth-state check | Verify current source-of-truth files, repo status, and canonical naming before acting. |
| Planning and specs | Convert intent into scope, non-goals, acceptance criteria, risks, and execution order. |
| Architecture | Map components, dependencies, data flows, interfaces, and implementation sequence. |
| Build and implementation | Apply the right engineering or document-production workflow for the selected branch. |
| Data and retrieval | Use Bookworm, repo twins, knowledge sources, and retrieval rules when relevant. |
| Graph and knowledge | Update or consult Atlas Graph Engine and Atlas Knowledge Vault when relevant. |
| Security and compliance | Check access boundaries, secrets, auth, privacy, and policy constraints. |
| Testing and proof | Run validation gates, regression checks, proof matrix updates, and evidence capture. |
| Documentation and handoff | Produce final report, coding-agent handoff, docs, and reusable artifacts. |
| Skill refinement | Log misses, update triggers/checklists, and add regression cases when behavior fails. |

## Execution Semantics

When an external agent receives `invoke all skills`:

1. Route the request through the universal coverage matrix.
2. Call only the external runtime skills that are safe, relevant, and non-destructive.
3. Read and apply repository-native `13_skills/active/SKILL_*.yaml` and `.playbook.md` files as disciplines.
4. Do not call destructive or setup skills such as `init`, recurring `schedule`, or config-changing tools unless explicitly requested.
5. Report the distinction between tool-called skills and playbook-applied disciplines.
6. Do not ask the user to name every `SKILL_*` manually when the router can select the relevant playbooks.

## Project-Specific Scope Rule

Project-specific imported skills and agents are scoped assets.

Examples:

- GEN.OS-specific skills activate when the request targets GEN.OS, kernel, compiler, SUPER C, or related canonical terms.
- Elson-specific skills activate when the request targets Elson, trading, portfolio, finance RAG, or related canonical terms.
- IPOS/transit skills activate when the request targets paratransit, VTA, KPI, dispatch, reports, contracts, or related canonical terms.
- Atlas skills activate when the request targets Atlas, Repo Twin, Atlas Graph Engine, Atlas Knowledge Vault, Proof Matrix, Skill Refinery, or related canonical terms.

If no target binds a project-specific skill, the router must treat that skill as available but suppressed.

## Acquisition Distinction

These are acquisition requests:

- `pull all new skills`
- `acquire all skills`
- `pull new skills from .claude .codex .gemini`
- `acquire all agents`
- `scan assistant surfaces`

These route to assistant-surface acquisition and normalization.

These are invocation requests:

- `invoke all skills`
- `use all skills`
- `run all skills`
- `activate all skills`
- `all skills`
- `full skill stack`
- `universal skills`

These route to universal skill invocation.

## Required Runtime Output

When all-skills mode is active, the response must include or internally produce:

- Universal skill coverage matrix.
- Selected portable skills.
- Project-specific skills activated by target.
- Project-specific skills suppressed as out of scope.
- Proof and validation gates.
- Skill-refinement actions if a miss caused the invocation.
