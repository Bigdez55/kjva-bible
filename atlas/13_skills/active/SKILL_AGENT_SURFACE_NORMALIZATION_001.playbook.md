# Agent Surface Normalization Playbook

## Skill ID
SKILL_AGENT_SURFACE_NORMALIZATION_001

## Purpose
Normalize all agent-related Claude surfaces, not only canonical `universal/agents` files, into a queryable registry and role index.

## Trigger Conditions
- User says agents were missed.
- Agent acquisition needs to include repo-local agents, memory, sessions, or coordination docs.
- The system needs to distinguish agent definitions from agent operational context.

## Hard Constraints
- Do not treat `universal/agents` as the only agent source.
- Classify agent surfaces into `universal_agents`, `repo_agents`, `agent_memory`, `agent_sessions`, and `agent_root_doc_or_related`.
- Deduplicate by category and hash while preserving all source occurrences.
- Keep agent-memory and session files as context/evidence unless explicitly promoted into active skills or personas.
- Do not treat the external runtime Skill tool registry as the full ATLAS skill library.
- Repository-native `13_skills/active/SKILL_*.yaml` entries are applied by reading YAML/playbooks, even when they are not tool-callable in Claude, Codex, Gemini, or another agent runtime.

## Workflow

### Observe
- Identify the exact user correction or requested acquisition/refinement scope.
- Inventory existing repo artifacts before creating anything new.
- Separate raw source evidence from normalized operational canon.
- Separate tool-callable runtime skills from repository-native playbook disciplines.

### Orient
- Classify sources, misses, reusable patterns, and existing skill overlap.
- Decide whether to create a new skill, improve an existing skill, consolidate duplicates, or add only a ledger/regression entry.

### Decide
- Select the minimum durable artifacts needed: active skill, playbook, ledger, router binding, registry update, regression case, or report.
- Define validation commands before claiming closure.

### Act
- Preserve source evidence.
- Create or update skills and ledgers.
- Wire router/registry entries when operational invocation is required.
- Run validation and report proven results.

## Required Outputs
- Agent surface registry
- Role-oriented index
- Category counts
- Source occurrence list
- Top-level agent registry link
- Tool-callable versus playbook-applied distinction
- Validation results

## Validation Checklist
- Existing skills were checked before creating new ones.
- New skills have active YAML, playbook, ledger, aliases, related skills, and required outputs.
- Router bindings exist when the skill should be invoked from natural language.
- Registry sync, regression, and drift checks are run when repo artifacts change.
- Final response distinguishes raw preservation, normalized canon, and tested behavior.
- Final response distinguishes skills actually called as runtime tools from repository-native playbooks applied as disciplines.
