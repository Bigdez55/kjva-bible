# Skill Lifecycle — Promotion and Demotion Contract

**Version:** 1.0.0
**Status:** active
**Authority:** This document is the binding contract for how skills move between lifecycle states. `validate_skill_router_integration.py` and `auto_promote_tier.py` enforce it.

---

## The Five Lifecycle Locations

Every skill exists in exactly one location at any moment. The location reflects its current state.

```
skill_refinery/  ←  incubator (drafts, proposals, golden examples)
       │
       │  (1) author creates SKILL_*.yaml + .playbook.md after refinery work
       ▼
   candidate/    ←  awaiting review for promotion to active
       │
       │  (2) promote_skill.py validates and moves
       ▼
    active/      ←  production — invokable, tracked, registry+router-gated
      ╱ ╲
     ╱   ╲
    ╱     ╲
   ▼       ▼
deprecated  superseded
  (no replacement)   (replaced by a successor skill)
```

| Location | Status field | Tier permitted | What lives here |
|---|---|---|---|
| `skill_refinery/` | (none — not yet a skill) | (none) | Drafts, correction ledgers, improvement proposals, anti-patterns, golden examples |
| `candidate/` | `experimental` | `experimental` | Skill files awaiting first-time promotion to active |
| `active/` | `active` | `starter` / `active` / `refining` / `hardened` / `apex` / `one-shot-apex` | Production skills |
| `deprecated/` | `deprecated` | (frozen at time of deprecation) | Retired skills with no replacement |
| `superseded/` | `superseded` | (frozen at time of supersedence) | Skills replaced by a newer canonical entry |

---

## Transitions

### T1 — `skill_refinery/` → `candidate/`

**Trigger:** Author has stabilized a draft and wants peer review before production.

**Who:** Human author (manual).

**Script:** none — author creates the files directly under `candidate/SKILL_<CONCEPT>_<NNN>.yaml` + `.playbook.md`.

**Gates:**
- File names match canonical pattern (`SKILL_[A-Z0-9_]+_\d{3}`)
- `skill_number` is in the correct provenance range (1–499 for `native`)
- `tier: experimental`, `status: experimental`
- Required base fields present (7 base fields per schema)
- Domain values from controlled vocab

**Validator:** `validate_tiered_schema.py --tier experimental --dir candidate/`

---

### T2 — `candidate/` → `active/`

**Trigger:** Reviewer approves the candidate skill for production.

**Who:** Human reviewer + `promote_skill.py`.

**Script:** `infrastructure/scripts/skill_lifecycle/promote_skill.py SKILL_<CONCEPT>_<NNN>`

**What the script does:**
1. Verifies skill file in `candidate/`
2. Runs full `validate_tiered_schema.py` against the file at `tier: starter` requirements
3. Adds entry to `skills.registry.yaml`
4. Adds routing entry to `trigger_router.yaml`
5. `git mv` the YAML + playbook from `candidate/` to `active/`
6. Updates skill's `tier:` to `starter` and `status:` to `active`
7. Initializes `improvement_metrics:` block with `invocation_count: 0`, `correction_count: 0`
8. Runs `validate_skill_router_integration.py` — must pass before commit

**Gates:**
- Skill file valid per starter-tier requirements
- No duplicate skill_id or skill_number in target location
- Registry + router updates are consistent
- All cross-references in playbook are valid

---

### T3 — `active/` (tier promotion within active)

**Trigger:** Telemetry shows the skill has stabilized at the next tier.

**Who:** `auto_promote_tier.py` (autonomous, runs daily).

**Script:** `infrastructure/scripts/skill_lifecycle/auto_promote_tier.py`

**Promotion criteria (computed from `improvement_metrics:`):**

| From → To | Required |
|---|---|
| `experimental` → `starter` | ≥10 invocations, `corrections_per_100_uses` ≤ 30, no `failure` outcomes in last 5 invocations |
| `starter` → `active` | ≥50 invocations, `corrections_per_100_uses` ≤ 10, `hard_constraints:` unchanged for 14 days |
| `active` → `hardened` | ≥200 invocations, `corrections_per_100_uses` ≤ 2, `validation_tests:` + `improvement_history:` present, 30-day stability |
| `hardened` → `apex` | ≥1000 invocations, `corrections_per_100_uses` ≤ 0.1, `ledger:` + `regression_cases:` present, 90-day stability, cross-runtime usage proven (telemetry from ≥2 of: claude, codex, gemini, mcp) |

**What the script does:**
1. Read every active skill's `improvement_metrics:` block
2. For each skill meeting next-tier criteria:
   - Bump `tier:` field
   - Append to `tier_promotion_history:` with date, trigger telemetry summary
   - Open a PR (one per promotion) for human confirmation
3. PRs auto-merge during the first 30 days require human approval; after that, patch-level promotions may auto-merge per Phase 8 safety rails

**Demotion** is also possible: if `corrections_per_100_uses` regresses by 2× during a 30-day window, the skill auto-demotes one tier and opens an investigation issue.

---

### T4 — `active/` → `superseded/`

**Trigger:** A newer canonical skill replaces this one.

**Who:** Human + `supersede_skill.py`.

**Script:** `infrastructure/scripts/skill_lifecycle/supersede_skill.py SKILL_<OLD>_<NNN> --by SKILL_<NEW>_<NNN>`

**What the script does:**
1. Verifies new skill exists in `active/` and is at `tier: active` or higher
2. Updates old skill's `status: superseded`, adds `superseded_by: SKILL_<NEW>_<NNN>`
3. `git mv` old skill from `active/` to `superseded/`
4. Removes old skill from `skills.registry.yaml` active section, adds to `superseded` section
5. Removes old skill from `trigger_router.yaml` routes
6. Adds redirect: any router phrase that pointed at the old skill now points at the new
7. Regenerates runtime projections (Phase 6) so the kebab name now serves the new skill's content
8. Logs the supersedence in `skill_refinery/master_ledger.yaml`

**Gates:**
- New skill must be at `active` tier or higher
- No active skill depends on the old skill (check `related_skills:` arrays)
- Telemetry continuity preserved (old skill's telemetry archived, new skill inherits routing)

---

### T5 — `active/` → `deprecated/`

**Trigger:** Skill is being retired with no replacement.

**Who:** Human + `deprecate_skill.py`.

**Script:** `infrastructure/scripts/skill_lifecycle/deprecate_skill.py SKILL_<CONCEPT>_<NNN> --reason "<text>"`

**What the script does:**
1. Verifies no active skill depends on this one
2. Updates `status: deprecated`, adds `deprecation_reason:`, `deprecated_on: <date>`
3. `git mv` from `active/` to `deprecated/`
4. Removes from `skills.registry.yaml` active section, adds to `deprecated` section
5. Removes from `trigger_router.yaml`
6. Deletes runtime projections (no `~/.claude/skills/<kebab>/` for this skill any more)
7. Any future invocation of the kebab name returns "skill deprecated, no replacement; see <reason>"

**Gates:**
- No active dependents
- Reason text required (non-empty)
- Telemetry preserved in archive

---

### T6 — `deprecated/` or `superseded/` → (none)

**Skills never come back from deprecated or superseded.** They are permanent retirees, preserved for audit only. To resurrect a concept, create a new skill with a new skill_number and a new ID. The deprecated skill remains as the historical record.

---

## What runs on every transition

Every transition script runs the following BEFORE committing:

```
1. validate_skill_router_integration.py   ←  the sacred invariant: active=registry=router
2. validate_tiered_schema.py              ←  schema matches tier requirements
3. validate_taxonomy.py                   ←  controlled vocabulary respected
4. detect_duplicates.py --strict          ←  no duplicate skill_id, skill_number, router key
5. validate_projection_coverage.py        ←  runtime shims consistent (Phase 6+)
```

If any gate fails, the transition is aborted and no files are changed. The script exits non-zero with a structured error report.

---

## Bootstrap state (post-Phase 0 through Phase 4)

When the Unified Skill Corpus plan completes Phase 4, the corpus will be:

- `active/` — 180 native + ~30 migrated user-level + 43 promoted external = ~253 skills
- `candidate/` — empty (no candidates yet)
- `experimental/` — empty
- `deprecated/` — empty
- `superseded/` — empty
- `skill_refinery/` — populated with correction ledgers, improvement proposals, anti-patterns, and now telemetry archives (Phase 8)

Phase 5 may rename ~30 skills (atlas/apex prefix stripping). Phase 7 may promote some `starter` external imports to `active` if telemetry warrants.

---

## Validator behavior

`validate_skill_router_integration.py` (existing, will be extended in Phase 9):

- Every `active/SKILL_*.yaml` is in `skills.registry.yaml`
- Every entry in `skills.registry.yaml` has a file in `active/`
- Every entry is routed in `trigger_router.yaml`
- No skill exists in two lifecycle dirs simultaneously
- `deprecated/` and `superseded/` skills are NOT in the registry or router
- `candidate/` skills are NOT in the active registry or active router section

---

## Change Log

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-05-26 | Initial promotion/demotion contract established |
