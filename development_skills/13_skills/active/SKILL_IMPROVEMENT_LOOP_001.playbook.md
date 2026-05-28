# Playbook: SKILL_SC_IMPROVEMENT_LOOP_001
# SUPER C Continuous Skill Improvement Loop

## Skill ID
SKILL_SC_IMPROVEMENT_LOOP_001

## Title
SUPER C Continuous Skill Improvement Loop

## Layer
governance

## Domains
meta-skill, continuous-improvement, governance

---

## Purpose

Every miss, surprise, user correction, or planning failure must improve the
skill system. SUPER C skills are not static — they evolve in response to every
failure mode that surfaces in real execution. The improvement loop is the
governance discipline that turns each painful surprise into a permanent
regression guard.

The loop has four obligations, in order:

1. **Log the miss** in the central Miss Log so it is durable and searchable.
2. **Identify the offending skill** (or absence of a skill) responsible for
   allowing the miss.
3. **Patch the skill** by adding a new failure mode, a regression prompt, and
   a version-history entry.
4. **Bump the skill version** so downstream consumers know a new lesson is
   encoded.

If any obligation is skipped, the loop has failed and the next occurrence of
the same miss is virtually guaranteed. This skill exists specifically to
prevent the "same miss recurs" failure mode that defines a stagnant skill
system.

---

## Trigger Events (10 items)

This skill MUST be invoked when any one of the following occurs. Each trigger
is a sufficient condition — only one needs to fire.

| #  | Trigger Event                                | Example                                                  |
|----|----------------------------------------------|----------------------------------------------------------|
| 1  | User correction                              | User says "no, that's wrong" or "you missed X"           |
| 2  | Blocker surprise                             | A blocker surfaces mid-execution that was not flagged    |
| 3  | Milestone overpromise                        | A Gold/SEALED claim that does not match the gate state   |
| 4  | Gate failure                                 | A required gate fails after a "ready" declaration        |
| 5  | Contradicted report                          | A status report contradicts evidence in the repo         |
| 6  | Fragmented handoff                           | Agent A handoff to Agent B lost context or scope         |
| 7  | Late blocker discovery                       | A blocker found late that should have surfaced in preflight |
| 8  | Skill silently bypassed                      | A skill that should have run was not invoked             |
| 9  | Repeated user instruction                    | User has to give the same correction more than once      |
| 10 | Reviewer / advisor / red-team finding adopted | An external review flags a process gap                   |

Any one of these triggers obligates the agent to run the full loop below
before continuing substantive work.

---

## Required Miss Log Path

All miss entries live in a single canonical file:

```
development_skills/_miss_log/SUPER_C_MISS_LOG.md
```

Rules for the miss log:

- One file, append-only. Never delete or rewrite past entries.
- Each entry is a Markdown section with a stable anchor ID (`SC-MISS-NNN`).
- IDs are monotonic and zero-padded to three digits. `SC-MISS-001` is the
  founding entry (v31 Gold closure surprise).
- The file lives under `development_skills/_miss_log/` — the leading
  underscore keeps it sorted at the top of the directory listing and signals
  "infrastructure, not a skill".
- If the directory does not yet exist, the first invocation of this skill
  creates it.

---

## Each Entry Fields

Every miss log entry MUST contain the following fields, in this order. Missing
any field invalidates the entry and triggers a re-run of the loop.

| Field             | Type        | Description                                                             |
|-------------------|-------------|-------------------------------------------------------------------------|
| `miss_id`         | string      | `SC-MISS-NNN`, monotonic, zero-padded                                   |
| `date`            | ISO 8601    | UTC date the miss was logged                                            |
| `trigger_event`   | enum        | One of the 10 trigger events above (use the table number + name)        |
| `summary`         | string      | One-sentence description of what was missed                             |
| `root_cause`      | string      | Why it happened — the absent guard, not the symptom                     |
| `offending_skill` | id or `NONE`| The skill ID that should have caught it; `NONE` means a new skill is needed |
| `skill_patch`     | string      | The concrete change made (failure mode added, regression prompt added)  |
| `version_bump`    | string      | The version delta on the offending skill (e.g. `1.0.0 → 1.0.1`)         |
| `regression_prompt` | string    | The exact prompt-line that future runs MUST surface                     |
| `evidence`        | path list   | Files / commits / reports that demonstrate the miss                     |
| `status`          | enum        | `open`, `patched`, `verified`, `recurred`                               |

A miss starts at `open`, moves to `patched` when the skill update lands,
moves to `verified` once a subsequent run exercises the regression prompt
without re-triggering the miss, and moves to `recurred` if it happens again
(at which point a new miss entry MUST be created with a back-link).

---

## Required Entry for SC-MISS-001 (verbatim per order §8)

This entry is mandatory and must appear at the top of the miss log. It is the
founding entry of the SUPER C improvement loop.

```markdown
## SC-MISS-001 — v31 Gold closure surprise

- **miss_id:** SC-MISS-001
- **date:** 2026-05-17
- **trigger_event:** 3 — Milestone overpromise (also 2 — Blocker surprise)
- **summary:** A v31 Gold closure was declared ready before a known blocker
  was surfaced, causing rework and late-stage red-team intervention.
- **root_cause:** No formal improvement loop existed to ensure prior misses
  fed back into preflight skills. Red-team preflight was not invoked, and
  there was no Miss Log to consult before issuing the execution order.
- **offending_skill:** SKILL_SC_RED_TEAM_PREFLIGHT_001 (already created as
  the direct response); SKILL_SC_IMPROVEMENT_LOOP_001 (this skill — created
  as the meta-response so misses can no longer go unrecorded).
- **skill_patch:** Created SKILL_SC_IMPROVEMENT_LOOP_001 v1.0.0; created
  SUPER_C_MISS_LOG.md; added regression prompt requiring miss-log consultation
  before any Gold / SEALED declaration.
- **version_bump:** SKILL_SC_IMPROVEMENT_LOOP_001 0.0.0 → 1.0.0 (initial);
  SKILL_SC_RED_TEAM_PREFLIGHT_001 0.0.0 → 1.0.0 (initial, same incident).
- **regression_prompt:** "Before declaring v_X Gold / SEALED, consult
  SUPER_C_MISS_LOG.md and run SKILL_SC_RED_TEAM_PREFLIGHT_001. Any open miss
  whose offending_skill is in the dependency chain blocks the declaration."
- **evidence:**
  - execution order §8 (v31 Gold)
  - this skill (SKILL_SC_IMPROVEMENT_LOOP_001) and its sibling
    SKILL_SC_RED_TEAM_PREFLIGHT_001
- **status:** patched
```

This entry must appear verbatim (modulo formatting) at the top of the miss
log. Subsequent entries follow the same template.

---

## Required Skill Versioning

Every skill patch driven by this loop MUST update the offending skill's YAML
in two places:

1. **`version:` field** — bumped per semver discipline:
   - `PATCH` (`1.0.0` → `1.0.1`) — failure mode added, regression prompt
     added, no behavioral change to existing steps.
   - `MINOR` (`1.0.0` → `1.1.0`) — a new step or new output is added.
   - `MAJOR` (`1.0.0` → `2.0.0`) — backwards-incompatible change to inputs,
     outputs, or required behavior.

2. **`improvement_history:`** — a new entry appended with:
   ```yaml
   - version: <new_version>
     reason: >
       <miss_id> — <one-line description>. Added <failure_mode> /
       <regression_prompt>.
   ```
   The `<miss_id>` MUST match an entry in the miss log. This creates a
   bi-directional link: the miss log points to the skill version, and the
   skill version points back to the miss.

Additional rules:

- The miss log entry's `version_bump` field MUST exactly match the version
  delta recorded in the skill's `improvement_history`.
- A skill that has been updated without a version bump is considered
  silently mutated and is itself a fresh miss (`trigger_event: 8 — Skill
  silently bypassed`).
- The very first version of a brand-new skill is `1.0.0`, with an
  `improvement_history` entry that cites the founding miss (typically a
  `NONE` `offending_skill` that motivated the new skill).

---

## Failure Mode This Skill Prevents

The single most corrosive failure mode in a skill-driven system is:

> **The same miss recurs.**

When the same surprise happens twice, three things are true:

1. The first occurrence was painful but tolerable.
2. The second occurrence proves the system did not learn.
3. The agent loses trust — every future "this is ready" claim is suspect.

This skill prevents that failure mode by making the loop mandatory and
auditable. Specifically, it neutralises the four known failure modes
captured in this skill's YAML:

| Failure Mode              | How This Skill Prevents It                                  |
|---------------------------|-------------------------------------------------------------|
| `miss never logged`       | Trigger Events §1-§10 obligate logging on every occurrence  |
| `skill never updated`     | The loop requires a concrete `skill_patch` field per entry  |
| `same miss recurs`        | The regression prompt becomes a preflight check for that class |
| `regression prompt missing` | The miss log entry is invalid without one — re-runs the loop |

If a future incident maps to one of those four failures, this skill itself
becomes the offending skill and must be patched with a new failure mode,
new regression prompt, and a version bump — closing the loop on the loop.

---

## Loop Procedure (operational checklist)

When a trigger event fires, run these steps in order. Do not skip.

### Step 1 — Halt substantive work

Stop writing code, stop closing the gate, stop drafting the report. The loop
runs first.

### Step 2 — Open / create the miss log

```bash
MISS_LOG="development_skills/_miss_log/SUPER_C_MISS_LOG.md"
mkdir -p "$(dirname "$MISS_LOG")"
[ -f "$MISS_LOG" ] || cat > "$MISS_LOG" <<'EOF'
# SUPER C Miss Log

Append-only log of misses, surprises, corrections, and planning failures.
Each entry follows SKILL_SC_IMPROVEMENT_LOOP_001 schema.
EOF
```

### Step 3 — Allocate the next `miss_id`

Find the highest existing `SC-MISS-NNN` and increment. Pad to three digits.
If the log is empty, the first entry is `SC-MISS-001`.

### Step 4 — Identify the offending skill

Ask: which skill, had it been invoked correctly, would have caught this?

- If the answer is an existing skill → that is the `offending_skill`.
- If no existing skill covers the case → `offending_skill: NONE` and a new
  skill must be authored.

### Step 5 — Draft the entry

Use the field schema in "Each Entry Fields". Every field is required.

### Step 6 — Patch the offending skill

- Append the new failure mode to `known_failure_modes` in the YAML.
- Add the regression prompt to the playbook (a numbered step that future
  runs MUST execute before declaring success).
- Bump `version` per semver discipline.
- Append `improvement_history` entry referencing `miss_id`.

### Step 7 — Append the entry to the miss log

Add the new entry to `SUPER_C_MISS_LOG.md` under the existing entries.
Set `status: patched`.

### Step 8 — Verify on next run

The next run of the offending skill MUST hit the regression prompt. If it
does and the miss does not recur, update the entry's `status` to `verified`.
If the miss recurs, open a new miss entry with `trigger_event: 8` (or the
appropriate trigger) and back-link to the original.

### Step 9 — Resume substantive work

Only after Steps 1-7 are durable on disk may substantive work resume.

---

## Inputs

| Parameter         | Type   | Required | Description                                            |
|-------------------|--------|----------|--------------------------------------------------------|
| `trigger_event`   | enum   | yes      | Which of the 10 trigger events fired                   |
| `summary`         | string | yes      | One-sentence description of the miss                   |
| `offending_skill` | id     | yes      | Skill ID, or `NONE` if a new skill is needed           |
| `evidence`        | paths  | yes      | At least one file, commit, or report demonstrating it  |

---

## Outputs

| Artifact              | Location                                              |
|-----------------------|-------------------------------------------------------|
| Miss log entry        | `development_skills/_miss_log/SUPER_C_MISS_LOG.md`    |
| Failure mode update   | Offending skill `.yaml` (`known_failure_modes`)       |
| Regression prompt     | Offending skill `.playbook.md` (new numbered step)    |
| Skill patch           | Offending skill `.yaml` + `.playbook.md`              |
| Version history bump  | Offending skill `.yaml` (`version` + `improvement_history`) |

---

## Validation

`TEST_SKILL_SC_IMPROVEMENT_LOOP_001_001` verifies:

1. A simulated trigger event produces a valid miss log entry with all
   required fields.
2. The offending skill's YAML receives a new `known_failure_modes` entry
   and a version bump.
3. The offending skill's playbook receives a new regression-prompt step.
4. A re-run of the offending skill exercises the regression prompt and
   prevents recurrence of the simulated miss.
5. The `version_bump` field in the miss log entry exactly matches the
   `improvement_history` delta in the offending skill.

See [08_verification/skill_tests/TEST_SKILL_SC_IMPROVEMENT_LOOP_001_001.yaml](../../08_verification/skill_tests/TEST_SKILL_SC_IMPROVEMENT_LOOP_001_001.yaml).

---

## Related Skills

- `SKILL_SC_RED_TEAM_PREFLIGHT_001` — sibling skill created from the same
  founding miss (SC-MISS-001); preflight challenges feed candidate misses
  to this loop.
- `SKILL_FIND_BEFORE_CREATE_001` — consulted when a miss requires a new
  skill, to confirm no existing skill already covers the gap.
- `SKILL_PROOF_MATRIX_001` — supplies evidence rows that document a miss
  during gate review.
- `SKILL_DRIFT_DETECTION_001` — surfaces drift-class misses that this loop
  then turns into permanent regression prompts.

---

## Anti-patterns (do not do this)

- **Logging a miss without patching a skill.** A log entry without a patch
  is documentation, not learning. The loop has failed.
- **Patching a skill without logging the miss.** The patch loses its
  provenance and the regression prompt is forgotten in the next refactor.
- **Bumping the version without an `improvement_history` entry.** Breaks
  the bi-directional link between miss and version.
- **Treating "advisor said so" as patch justification without a miss
  entry.** Even advisor / red-team findings adopted into a skill MUST be
  logged as a miss (trigger event §10) so the lineage is preserved.
- **Silently re-using `SC-MISS-001`.** IDs are monotonic and unique
  forever. The founding entry is sacred.

---

## Governance Note

This is a **meta-skill**. It governs how all other skills evolve. Any
proposed change to this skill itself follows the same loop:

1. The miss that motivates the change must be logged.
2. The proposed change must add a `known_failure_modes` entry to this
   YAML.
3. The version of this skill bumps.
4. The new behavior becomes mandatory for all future skill patches.

There is no exception. The loop applies to the loop.

---

## Recorded Trigger Events

- **SC-MISS-001 (2026-05-17, v31 cycle):** Gold closure was requested even though evidence already proved structural blockers. Triggered creation of the 6-skill governance system. Skill set v1.0.0 closed.
- **SC-MISS-002 (2026-05-17, v31.2 cycle):** Sub-wave B2 silently sidestepped earlier sub-wave A5's BLOCKED_BY_MISSING_PRIMITIVE verdict via parse-only workarounds. Triggered patches to AGENT_EXECUTION_ORDER (Wave-Sequencing Contract) and RED_TEAM_PREFLIGHT (Row 16). Skill set v1.1.0.
- **SC-MISS-003 (2026-05-17, v31.3 cycle):** Skill knowledge derived from documentation, source-file scaffolds, and build-graph greps rather than from empirical compiler-binary probes. v31.2 final report claimed "scc lacks run subcommand" when `scc run-jit` was dispatched at scc_entry.c:6094; v31.2 claimed certain intrinsics had "prior canonical usage" when 0/6 had codegen recognition. Triggered patches to AGENT_EXECUTION_ORDER (Empirical Surface Probe Mandate), RED_TEAM_PREFLIGHT (Rows 17-19), DEPENDENCY_SOVEREIGNTY (Check 7b+7c), and NO_SURPRISE_PLANNING (Stage IV-I Taxonomy). Skill set v1.2.0.
- **v31.3 First Wave-Sequencing Contract regression-PASS (2026-05-17):** A-wave I4+A6 surfaced `__store_u8__` codegen BLOCKED; main thread HALTED B-wave SHA-256 runtime closure rather than authoring parse-only workarounds. This is the FIRST empirical demonstration of the contract preventing SC-MISS-002 recurrence.
