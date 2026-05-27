# Playbook: SKILL_SC_MILESTONE_GATE_DESIGN_001 — SUPER C Milestone Gate Design

## Skill ID
SKILL_SC_MILESTONE_GATE_DESIGN_001

## Version
1.0.0

## Layer
governance

## Domains
- gating
- validation
- quality

---

## Purpose

Ensure every SUPER C milestone has REAL pass/fail gates before implementation begins.

A milestone gate is a script that executes against disk-and-binary reality and
returns exit 0 only when every closure condition is met. Gates that exit 0 on
incomplete work, swallow failures, or check file-presence in place of function
are not gates — they are scaffolds masquerading as gates. This skill exists so
the v31 → v31.1 pattern (Gold gate initially exit-0 informational despite 7
FAIL probes — fixed in W1-C by inverting polarity and removing the swallow) is
never repeated.

The skill enforces a single contract: BEFORE the first line of milestone
implementation code is written, the agent has authored a Gate Matrix that
names every gate, what it asserts, what would prove it false, how it detects
no-regression on prior milestones, and how it refuses to lie when a blocker
is present.

---

## When to Use

| Trigger                                                                | Required? |
|------------------------------------------------------------------------|-----------|
| Any milestone touching parser, sema, type system, import, linker       | MANDATORY |
| Any milestone touching boot, optimizer, language surface, AI runtime   | MANDATORY |
| Any milestone that produces a tag (e.g., `v31.0`, `v23.1.A`)           | MANDATORY |
| Any Gold / Platinum sovereignty closure work item                      | MANDATORY |
| Any milestone that adds or replaces an existing gate                   | MANDATORY |
| Fixes touching > 1 file with shared failure class                      | RECOMMENDED |
| Trivial typo / comment / doc-only changes                              | NOT REQUIRED |

Invoke this skill at the start of `one-shot-execution-planning` §8 (Gate Plan).
Output is the input to that section. Do NOT skip ahead to coding — a missing
or weak gate matrix is the single highest-frequency cause of post-tag rework
in the SUPER C audit history (`v0_v21_drift_audit` 2026-05-15 surfaced 4
artifacts that all traced back to gate gaps).

---

## Required Gate Matrix

Every milestone produces a matrix in `docs/plans/<milestone>_gate_matrix.md`
with EXACTLY the following 10 fields per gate. Missing any field invalidates
the matrix and blocks implementation.

| #  | Field                       | Description                                                                                                          |
|----|-----------------------------|----------------------------------------------------------------------------------------------------------------------|
| 1  | `gate_id`                   | Unique identifier matching pattern `<milestone>_<scope>_<index>` (e.g., `v31_1_gold_03`).                            |
| 2  | `gate_script`               | Absolute repo-relative path to the bash/python script that runs the probe (e.g., `scripts/gates/superc_active_path_gold.sh`). |
| 3  | `gate_type`                 | One value from the Gate Types enum (§ Gate Types, 8 values).                                                         |
| 4  | `asserts`                   | The exact post-condition the gate proves. Stated as a falsifiable claim, not a description.                          |
| 5  | `fails_on_pre_fix`          | The expected output / exit code BEFORE the milestone work lands. If gate is new, capture this at gate-author time.   |
| 6  | `passes_on_post_fix`        | The expected output / exit code AFTER the milestone closes. Must be measurable, not aspirational.                    |
| 7  | `blocker_link`              | The blocker register row(s) (e.g., `GOLD_BLOCKER-04`) that this gate proves closed. `NONE` only for hygiene gates.   |
| 8  | `regression_surface`        | List of prior gates / behaviors / files this gate or its target could break. Empty list is invalid; write `NONE_KNOWN` plus rationale. |
| 9  | `false_pass_defense`        | The specific mechanism that prevents the gate from passing on incomplete work (see § No Fake Gates, 5 signals).      |
| 10 | `post_tag_validation`       | The exact command to re-run after the milestone tag is cut, to confirm the gate still passes against the tagged state. |

Rules:
- All 10 fields are MANDATORY. `NONE` is allowed only for `blocker_link` on
  hygiene gates and only when paired with a rationale comment.
- `gate_script` must EXIST on disk at the time the matrix is written. If a
  new gate script is required, authoring it is the first implementation step
  per `one-shot-execution-planning` §10 step 1.
- `fails_on_pre_fix` and `passes_on_post_fix` are not optional. A gate
  whose pre-fix behavior is unknown is a gate whose post-fix behavior is
  unverifiable — it cannot prove the milestone closed anything.
- `regression_surface` of `NONE_KNOWN` requires the rationale to cite a
  primary source (e.g., "gate is leaf-only; near_term_success.sh does not
  invoke it; verified by `grep -n '<gate_id>' scripts/gates/near_term_success.sh`
  → zero matches").

---

## Gate Types

A gate must be classified as exactly ONE of the following 8 types. The type
determines the structural rules the gate must obey.

| Enum                     | Description                                                                                              | Example                                                         |
|--------------------------|----------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------|
| `closure`                | Proves a blocker is closed. Mandatory exit-1 on blocker presence. Mandatory exit-0 only on full closure. | `superc_active_path_gold.sh` (v31.1 enforcing form).            |
| `regression`             | Proves a previously-passing behavior still passes. Asserts against a captured pre-tag baseline.          | `near_term_success.sh` enforcing 1856/0 floor.                  |
| `native_attribution`     | Proves the change landed in the NATIVE compiler, not a scaffold. Cites file + function + line.           | `active_sc_compilation_no_seedc` probe in v31.1 Gold gate.      |
| `false_pass_defense`     | Proves the gate refuses to pass on incomplete work (e.g., empty input, missing artifact, stub diagnostic). | `scc_check_sema_level_not_parse_floor` probe.                 |
| `dependency_audit`       | Proves the active path has no forbidden dependency (no Python, no seedc-delegation, no third-party C).    | `non_superc_dependency_audit.sh` (v31.1 enforcing form).        |
| `command_surface`        | Proves the binary's user-facing command surface matches the milestone contract.                          | `scc_command_surface_gate.sh` (v31.1 enforcing form).           |
| `evidence_present`       | Proves the milestone produced the required evidence packet on disk (release note, final report, etc.).   | Hygiene check that `release/notes/<tag>.md` exists.             |
| `post_tag_replay`        | Proves the milestone is reproducible from the tagged commit. Runs the entire gate suite against `git checkout <tag>`. | Tag-time CI replay.                                            |

Rules:
- Gates must NOT span types. If a probe asserts both closure and regression,
  split it into two probes within the same script or two separate scripts.
- Every milestone MUST include at minimum one `closure`, one `regression`,
  one `native_attribution`, one `false_pass_defense`, and one
  `evidence_present` gate. The other three types are conditional on scope.
- `post_tag_replay` is REQUIRED for any milestone producing a tag.

---

## No Fake Gates

A "fake gate" is any gate that returns exit 0 without actually proving its
asserted post-condition. The following 5 signals indicate a fake gate. If any
signal is present, the gate is invalid and must be rewritten before the
milestone proceeds.

### Signal 1 — Exit-0 informational

The gate's exit code is hard-coded to 0 regardless of probe results, or the
script `|| true`'s the probe, or the probe runs only as `echo` output with no
threshold check. Diagnostic: `grep -E 'exit 0$|\|\| true|^echo' <gate>.sh` —
investigate every match.

**Reference case:** v31 baseline `superc_active_path_gold.sh` returned exit 0
with 2 PASS / 7 FAIL because results were printed but never tallied into the
exit code. Fixed in v31.1 W1-C by introducing a FAIL counter and `exit $((FAIL > 0))`.

### Signal 2 — File-presence-as-functional-check

The gate `[ -f path/to/file ]` and concludes the function works. File
presence proves nothing about behavior — a 0-byte file passes the check.

**Defense:** Every file-presence check MUST be paired with a content assertion
(`grep -q '<expected substring>' file` AND `wc -c file` ≥ minimum) OR a
functional invocation (`<binary> <subcommand> && <output check>`).

### Signal 3 — Scaffold-counted-as-implementation

The gate accepts a stub, placeholder, parse-floor, or `TODO` comment as
evidence the feature is implemented. Diagnostic: search the artifact under
test for `TODO`, `STUB`, `SCAFFOLDED`, `lives in <other-tree> today`, or
`parse-err count` markers.

**Reference case:** v31 baseline `scc_compiles_active_path` passed because
the probe only checked `scc check --help` exited 0; it did not detect that
`scc_entry.c:8342-8347` literally states the feature "lives in seedc today
and is not wired into scc until Stage 4 semantic self-host." v31.1 added the
literal substring check.

### Signal 4 — Exit-0 informational on Gold readiness

Subset of Signal 1, but specifically dangerous: the gate is positioned in
documentation or CI dashboards as a Gold-readiness signal, yet exits 0
regardless of blocker state. Downstream readers (humans + agents) treat
exit 0 as Gold-ready and tag against false confidence.

**Reference case:** v31 `non_superc_dependency_audit.sh` and
`scc_command_surface_gate.sh` were both marked "informational only" in
their headers but appeared in the Gold readiness section of the
`v31_active_path_gold_gate_report.md`. v31.1 W1-C inverted polarity: both
now exit 1 when the milestone contract is violated, so the dashboard
cannot be misread.

### Signal 5 — Gate runs without asserting

The gate verifies that another gate or tool *executes*, not what it
*asserts*. A wrapper that runs `bash inner_gate.sh && echo "PASS"` passes
whenever `inner_gate.sh` exits 0, regardless of what `inner_gate.sh`
actually checked. If `inner_gate.sh` is itself a fake gate (Signals 1-4),
the wrapper inherits the lie.

**Defense:** When wrapping or invoking another gate, the wrapper MUST
assert against the inner gate's OUTPUT, not its exit code alone. Where
the inner gate's contract is "refuse to lie on a known blocker," the
wrapper must invert the test: `! bash inner_gate.sh` (i.e., the wrapper
passes only when the inner gate correctly hard-FAILs).

**Reference case:** v31.1 W1-C renamed Silver-gate probes `*_executes` →
`*_enforces` and flipped polarity from `bash gate.sh` to `! bash gate.sh`
so that the Silver gate now proves the enforcing gates correctly detect
reality, not just that they ran without crashing.

---

## Hard Rule

Implementation of a milestone MAY NOT begin until the Gate Matrix exists in
`docs/plans/<milestone>_gate_matrix.md`, every gate has all 10 fields filled,
the matrix has been screened against the 5 Fake-Gate Signals with a written
verdict per gate, and the matrix has been advisor-reviewed per
`one-shot-execution-planning` §11.

A milestone that produces a tag WITHOUT a matching gate matrix is a
post-tag-rework event waiting to surface. The audit history confirms this:
every drift the `v0_v21_drift_audit` surfaced traced to a milestone whose
gate plan was unwritten, weak, or fake-positive.

**No exceptions for:**
- "trivial" milestones (the v31 W1-C surface was assumed trivial; it was not)
- "documentation-only" tags (release notes claim closure; gates prove it)
- "follow-up" milestones to a parent (parent's gate matrix does NOT cover
  the follow-up's scope)

**One exception, narrowly:** a milestone that adds only a non-functional
asset (e.g., adds a single SVG to a README) MAY substitute a 3-line
abbreviated matrix with `evidence_present` only. The abbreviation MUST be
flagged in the release note.

---

## Failure Mode This Skill Prevents

This skill exists because v31 SCAFFOLDED four gates with exit-0 informational
posture despite the underlying milestone contract being unmet. The error
pattern was identical across all four: the gate scripts ran, printed
diagnostics, and returned exit 0 regardless of whether the asserted
post-condition held.

Primary source: `superc-v1/docs/reports/v31_1_evidence/W1-C_gate_enforcement.md`
records the v31 baseline and the v31.1 enforcing rewrite. The before/after
numbers are unambiguous:

| Gate                                    | v31 baseline                              | v31.1 enforcing                           |
|-----------------------------------------|-------------------------------------------|-------------------------------------------|
| `superc_active_path_gold.sh`            | 2 PASS / 7 FAIL — exit 0 (swallowed)      | 0 PASS / 9 FAIL — exit 1                  |
| `superc_active_path_silver.sh`          | 21 PASS / 0 FAIL — exit 0                 | 21 PASS / 0 FAIL — exit 0 (polarity flip) |
| `non_superc_dependency_audit.sh`        | 5 PASS / 0 FAIL — exit 0 (informational)  | 4 PASS / 3 FAIL — exit 1                  |
| `scc_command_surface_gate.sh`           | 4 PASS / 0 FAIL — exit 0 (informational)  | 4 PASS / 8 FAIL — exit 1                  |

The damage was contained because the v31 final report itself was honest
(`v31_final_report.md` flagged the gates as SCAFFOLDED), and the v31.1
Gold-closure work item W1-C corrected the gate scripts in-place before the
next downstream consumer (Gold tag) acted on the false signal. Had the
gates been used as automated promotion criteria, v31 would have shipped
GOLD-claimed while the underlying $(SEEDC) dependency, 8 active Python
tools, parse-floor `scc check`, and 18 ACTIVE_BLOCKER inventory rows
remained.

The corrective pattern from W1-C is now codified in this skill:
1. Every gate that appears in a milestone report's readiness section MUST
   exit non-zero when its asserted post-condition fails (Signals 1, 4).
2. Every gate that wraps another gate MUST assert against the inner gate's
   OUTPUT and may need to invert polarity when the inner gate is itself a
   "refuse to lie" probe (Signal 5).
3. Every gate's pre-fix and post-fix expected behaviors MUST be captured
   when the gate is authored, not inferred later (Required Gate Matrix
   fields 5, 6).
4. Every milestone tag MUST be followed by a `post_tag_replay` of the full
   gate suite against the tagged commit (Gate Type 8, Required Gate Matrix
   field 10).

If this skill is followed, the v31 → v31.1 corrective sprint does not need
to recur. If a future audit surfaces a recurrence, this skill must be
revised — see § Continuous Refinement.

---

## Inputs

| Input                  | Source                                                            | Required? |
|------------------------|-------------------------------------------------------------------|-----------|
| milestone definition   | `docs/plans/<milestone>_one_shot_plan.md` §1 + §2                 | MANDATORY |
| blocker register       | `docs/reports/<milestone>_gold_blocker_register.md` or equivalent | MANDATORY |
| dependency inventory   | `docs/reports/<milestone>_active_dependency_inventory.md`         | MANDATORY |
| prior gate inventory   | `scripts/gates/` directory listing + `near_term_success.sh` body  | MANDATORY |

If any input is missing, gate matrix authoring is blocked. The first action
is to produce the missing input via the upstream skill (one-shot planning,
blocker triage, dependency inventory audit).

---

## Outputs

| Output                  | Location                                                       |
|-------------------------|----------------------------------------------------------------|
| gate matrix             | `docs/plans/<milestone>_gate_matrix.md` (10-field table)       |
| pass/fail contract      | embedded in matrix `asserts` + `fails_on_pre_fix` + `passes_on_post_fix` |
| required evidence       | embedded in matrix `evidence_present` rows                     |
| false-pass prevention   | embedded in matrix `false_pass_defense` column + screening verdict |
| post-tag validation     | embedded in matrix `post_tag_validation` column + tag-time CI hook |

The matrix is the single source of truth for the milestone's closure
contract. Release notes and final reports reference it, do not duplicate it.

---

## Steps

### Step 1 — Load inputs

Read milestone definition, blocker register, dependency inventory, and
prior gate inventory. Verify each input is current (timestamp within the
last milestone cycle). If stale, refresh before proceeding.

### Step 2 — Enumerate gates

For every blocker in the register, every dependency the milestone touches,
and every command surface the milestone changes, list a candidate gate.
Group candidates by Gate Type (8 enum values). Drop duplicates only when
they assert the identical post-condition.

### Step 3 — Fill all 10 fields per gate

Write the matrix in `docs/plans/<milestone>_gate_matrix.md`. Every gate
row has all 10 fields. Empty cells are not allowed — write `NONE` plus a
rationale comment only where explicitly permitted (see § Required Gate
Matrix rules).

### Step 4 — Author missing gate scripts

For any `gate_script` path that does not yet exist on disk, author the
script before continuing. Capture `fails_on_pre_fix` by running the new
script against current disk state and recording the output verbatim.

### Step 5 — Screen against the 5 Fake-Gate Signals

For each gate row, walk the 5 signals (Exit-0 informational, File-presence
as functional, Scaffold counted as implementation, Exit-0 informational
on Gold readiness, Gate runs without asserting). Record a per-gate verdict
column: `CLEAN` or `RISK + signal-N + mitigation`.

### Step 6 — Wire into near_term_success or flagship suite

Any gate marked `regression` or `closure` MUST be invoked from the
milestone's flagship gate suite (typically `near_term_success.sh` or the
milestone-specific successor). Verify with
`grep -n '<gate_id>' scripts/gates/near_term_success.sh` — zero matches is
a wiring error unless the gate is explicitly leaf-only (rationale required).

### Step 7 — Advisor review

Per `one-shot-execution-planning` §11, call `advisor()` on the completed
matrix. Surface any signal-screening verdict of `RISK` for advisor review.
Disagreement with advisor on a RISK verdict requires written primary-source
evidence and re-screening.

### Step 8 — Lock and proceed

Once Step 7 returns CLEAN-APPROVED, the matrix is locked. Implementation
proceeds per `one-shot-execution-planning` §10. Changes to the matrix
during implementation require re-running Steps 5 + 7.

### Step 9 — Post-tag replay

Immediately after the milestone tag is cut, execute every gate row's
`post_tag_validation` command against the tagged commit. Record results in
the milestone's final report. Any exit-non-zero on `post_tag_validation`
is a tag-time defect and triggers immediate corrective sprint planning.

---

## Failure Modes and Mitigations

| Failure                                                  | Mitigation                                                                                |
|----------------------------------------------------------|-------------------------------------------------------------------------------------------|
| fake gate passes despite known blockers                  | Screen every gate against the 5 Fake-Gate Signals (Step 5). Reject any `RISK` verdict.    |
| file-presence check counted as functional check          | Apply Signal 2 defense: pair file-presence with content assertion or functional invocation. |
| scaffold counted as implementation                       | Apply Signal 3 defense: grep artifact for SCAFFOLDED / STUB / parse-floor markers.        |
| exit-0 informational gates lie about Gold readiness      | Apply Signals 1 + 4 defenses: every readiness-section gate exits non-zero on contract violation. |
| gate authored but not wired into flagship suite          | Step 6 grep check. Wiring errors block tag.                                               |
| pre-fix expected output never captured                   | Step 4 captures pre-fix output at gate-author time. Post-fix delta is unprovable otherwise. |
| post-tag replay skipped, regression discovered later     | Step 9 is mandatory. Tag-time defects must trigger a corrective sprint, not be silenced.  |

---

## Related Skills

- `SKILL_TRUTH_STATE_CHECK_001` — verify the truth file the matrix derives
  blocker counts from is current.
- `SKILL_DRIFT_DETECTION_001` — detect drift between gate matrix and
  actual disk state between milestone cycles.
- `SKILL_PROOF_MATRIX_001` — broader proof traceability that the gate
  matrix feeds into.
- `one-shot-execution-planning` (`.claude/skills/`) — §8 (Gate Plan)
  consumes this skill's output as its input.

---

## Validation

`TEST_SKILL_SC_MILESTONE_GATE_DESIGN_001_001` verifies:

1. A matrix missing any of the 10 required fields per gate is rejected.
2. A `gate_type` outside the 8-enum set is rejected.
3. A gate that exits 0 with at least one FAIL probe is detected as Signal 1
   and the matrix is flagged `RISK`.
4. A gate using `[ -f path ]` without a paired content/functional assertion
   is detected as Signal 2 and flagged `RISK`.
5. A gate whose target artifact contains `SCAFFOLDED` / `STUB` / `parse-floor`
   markers without a defense check is detected as Signal 3 and flagged `RISK`.
6. A gate marked as appearing in a Gold-readiness report section but with
   exit-0-on-FAIL behavior is detected as Signal 4 and flagged `RISK`.
7. A wrapper gate that asserts only on exit code of an inner gate (no
   output assertion or polarity inversion) is detected as Signal 5 and
   flagged `RISK`.
8. Post-tag replay command is non-empty for every milestone that produces a tag.
9. The v31 → v31.1 W1-C before/after numbers reproduce when the test
   harness replays the gate-rewrite sequence on the captured fixture.

See `08_verification/skill_tests/TEST_SKILL_SC_MILESTONE_GATE_DESIGN_001_001.yaml`.

---

## Continuous Refinement

After every milestone that uses this skill:

1. Note any gate that passed but later required corrective rework.
2. Identify which of the 5 Fake-Gate Signals (or a new signal) the gate
   exhibited.
3. If a new signal is discovered, add it as Signal 6+ here, increment
   skill version, and add a corresponding `validation_tests` entry.
4. Update the Reference Case in the corresponding signal section with the
   new milestone evidence.

Version: 1.0.0 — initial from SC-MISS-001, codifying the v31 → v31.1 W1-C
corrective sprint that converted 4 SCAFFOLDED exit-0 gates into ENFORCING
exit-1 gates. See `superc-v1/docs/reports/v31_1_evidence/W1-C_gate_enforcement.md`
for the full before/after evidence packet.
