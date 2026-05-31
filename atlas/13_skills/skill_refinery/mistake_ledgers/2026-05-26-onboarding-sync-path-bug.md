# Mistake Ledger — 2026-05-26

## Entry: sync_to_child_repo.py ROOT path broken after monorepo restructure

**Date:** 2026-05-26
**Context:** kjva-bible T1 onboarding
**Root cause:** `sync_to_child_repo.py` used `parents[2]` to compute ROOT, which was correct when the script lived at `25_automation/sync_scripts/` (2 levels below repo root). After the 2026-05-04 monorepo restructure moved it to `infrastructure/scripts/sync_scripts/` (3 levels below repo root), `parents[2]` resolved to `infrastructure/` instead of the repo root. This caused:
  1. All ALLOWLIST paths (`13_skills`, etc.) to be looked up under `infrastructure/` → silently skipped (not found)
  2. `.claude/universal` and `.codex/universal` not synced → child repos had no skills/agents
  3. `install_slash_commands.sh` had the same `../../` depth bug → slash commands not installed

**Detection:** User observed `.claude` and `.codex` missing in kjva-bible after T1 onboarding ran.

**Fix applied:**
  1. `sync_to_child_repo.py`: `parents[2]` → `parents[3]`; ALLOWLIST converted from list to `dict[src_rel, dst_rel]` with correct post-restructure source paths; dest paths normalized to canonical child-repo names
  2. `install_slash_commands.sh`: `../../` → `../../..` and SRC updated to `platform/systems/37_command_protocol/slash_commands`

**Remediation for existing child repos:** Re-run sync with fixed script; manually install slash commands; add `CLAUDE.md` + `.claude/settings.json`

**Prevention:** SKILL_REPO_ONBOARDING_001 T1 precondition check should verify `.claude/universal` exists in the target after sync, not just that the sync script exited 0.
