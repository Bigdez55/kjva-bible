# Global Claude Repository Acquisition Playbook

## Skill ID
SKILL_GLOBAL_CLAUDE_REPOSITORY_ACQUISITION_001

## Purpose
Discover, preserve, classify, and normalize every `.claude` directory across the user repo estate without mistaking raw preservation for operational import.

## Trigger Conditions
- User asks to go through every `.claude` directory in every repo.
- User asks to acquire missing skills, agents, memories, plans, commands, or other Claude Code assets.
- A prior acquisition answer is challenged as incomplete.

## Hard Constraints
- Search every declared repo root and skip only explicit vendor/noise folders such as `.git` and `node_modules`.
- Preserve raw source files before normalization.
- Report category counts and unique hash counts; do not claim complete acquisition without category-level evidence.
- Separate raw preservation, normalized operational canon, router wiring, and validation.

## Workflow

### Observe
- Identify the exact user correction or requested acquisition/refinement scope.
- Inventory existing repo artifacts before creating anything new.
- Separate raw source evidence from normalized operational canon.

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
- Search roots
- Claude directory inventory
- Raw preservation manifest
- Skill candidate index
- Agent surface index
- Operational import decisions
- Router/registry updates
- Validation results

## Validation Checklist
- Existing skills were checked before creating new ones.
- New skills have active YAML, playbook, ledger, aliases, related skills, and required outputs.
- Router bindings exist when the skill should be invoked from natural language.
- Registry sync, regression, and drift checks are run when repo artifacts change.
- Final response distinguishes raw preservation, normalized canon, and tested behavior.
