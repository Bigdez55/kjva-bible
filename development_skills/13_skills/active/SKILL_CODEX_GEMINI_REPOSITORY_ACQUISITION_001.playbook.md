# Codex and Gemini Repository Acquisition Playbook

## Skill ID
SKILL_CODEX_GEMINI_REPOSITORY_ACQUISITION_001

## Purpose
Discover, preserve, classify, and normalize Codex/Gemini assistant surfaces across the OneDrive and GitHub repo estate without drifting into user-level caches or unrelated local folders.

## Trigger Conditions
- User asks to search Codex directories, Gemini directories, or assistant-specific directories across repos.
- User says the assistant is drifting away from OneDrive and GitHub repos.
- User asks to acquire missing Codex/Gemini skills, agents, prompts, commands, memories, or support files.

## Hard Constraints
- Default search roots are `/Users/desmondearly/Library/CloudStorage/OneDrive-Personal` and `/Users/desmondearly/Documents/GitHub`.
- Do not scan `~/.codex`, `~/.gemini`, `Downloads`, or unrelated home directories unless the user explicitly expands scope.
- Preserve safe raw text. Index binary, sensitive, cache, token, session, and state files without copying their contents.
- Separate acquisition evidence from operational imports and registry/router wiring.

## Workflow

### Observe
- Confirm the requested assistant surfaces: Codex, Gemini, or both.
- Declare search roots and exclusions before scanning.
- Inventory existing `16_knowledge/external_collateral/all_codex_gemini_dirs_*` outputs to avoid duplicate acquisition.

### Orient
- Classify discovered files as universal agents, universal skills, repo skill support, tools, index/version files, other text, binary/large, or sensitive/state.
- Compare discovered assets against active skills, imported agent registries, and router bindings.
- Identify what should be raw-preserved only versus normalized into active skills, agents, prompt library, or router targets.

### Decide
- Preserve raw-safe evidence first.
- Normalize only durable operational assets.
- Add or update active skills when a recurring workflow is missing.
- Add regression coverage when the miss was caused by scope drift, missing acquisition, or incomplete agent-surface normalization.

### Act
- Generate acquisition report, source index, file manifest, surface registry, and role index.
- Wire relevant targets into the canonical trigger router.
- Sync registries and run validation.
- Report copied count, indexed-only count, unique hash count, and category counts.

## Required Outputs
- Search roots
- Scope boundary and exclusions
- Codex/Gemini directory inventory
- Raw-safe preservation manifest
- Indexed-only sensitive/binary manifest
- Category and unique hash counts
- Operational import decisions
- Router/registry updates
- Validation results

## Validation Checklist
- Search scope stayed inside OneDrive and GitHub repo roots unless explicitly expanded.
- User-level `.codex`, `.gemini`, Downloads, and unrelated home folders were not scanned by default.
- Sensitive/state files were indexed-only, not raw-copied.
- Active skills and agent registries were checked before creating new artifacts.
- Registry sync, regression runner, skills validation, and drift check passed after changes.
