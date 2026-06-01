# one-shot-execution-planning

<!-- Source: migrated from ~/.claude/skills/one-shot-execution-planning/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: one-shot-execution-planning -->

**Summary.** Forces deep preflight planning before implementation on any milestone touching parser, sema, import, type system, linker, optimizer, boot, language surface, AI runtime, or supply chain code. Activate when a coding agent is about to begin a non-trivial fix or feature, when an Execution Order is issued, when multiple files appear to share a failure class, or when prior sessions show symptom-chasing loops. This skill demands a One Shot Plan be produced and advisor-reviewed BEFORE any code is edited. The goal is surgical implementation, clean gate passage, and honest seals — not speed.

# One Shot Execution Planning — Operational Skill

**DIRECTIVE: Plan deeply. Code surgically. Gate strongly. Seal honestly.**

This skill is the antidote to the reactive loop pattern that emerged
during the v21 campaign: patch one symptom → run gates → discover the
next blocker → tag a narrow win → repeat. The audit that revealed a
single shared E_ARG_COUNT root cause affecting 13 files (and that one
6-line native fix produced an 8-PASS-bump) is empirical proof that
better preflight root-cause analysis would have prevented several
loops. This skill exists so that pattern does not repeat.

This is not a documentation excuse. Every section below produces a
required artifact, a required gate, or a required checklist item.

---

## 1. Purpose

Force every non-trivial implementation milestone to be preceded by a
written, advisor-reviewed One Shot Plan that maps the root cause,
dependencies, regression surface, fixtures, gates, and unlock
forecast — BEFORE editing any production source file.

The plan is not the milestone. The plan is the proof that the agent
understands the problem deeply enough to implement it surgically.

---

## 2. When to use this skill

**MANDATORY for any work touching:**
- parser (lexer, parser, AST construction, recovery)
- sema (type system, kind inference, signature walking, scope/resolution)
- import (allow-list, module roots, import rewriting)
- type system (kind table, primitives, references, slices, generics)
- linker (in-process, external, object format)
- optimizer (any optimization pass)
- boot (bootloader, AetherBoot, ELF parser, XISC loader)
- language surface (new syntax, new keywords, new operators)
- AI runtime (model integration, inference, sovereign LM)
- supply chain (dependencies, schemas, governance, lock layers)

**RECOMMENDED for:**
- any fix touching > 1 file
- any fix where prior session showed symptom-chasing pattern
- any fix where ≥ 2 files appear to share a failure class
- any Execution Order issued by the user

**NOT REQUIRED for:**
- trivial typo / comment fixes
- documentation-only changes (release notes, reports, README)
- test fixture additions that don't change production behavior

---

## 3. Mandatory preflight questions

Before drafting the One Shot Plan, the agent must answer each of these
in writing. "Don't know yet" is a valid answer at this stage; it
becomes the first investigation step in §4.

1. **What is failing?** Quote exact diagnostic output from the audit
   or test harness. Do not paraphrase. Do not work from memory.
2. **How many files are affected?** Get the count from the audit log
   or `grep -c`. Do not estimate.
3. **Do the failing files share a class?** (PARSE_FAIL, SEMA_FAIL,
   IMPORT_FAIL, etc.) If yes → §4 root cause map is required.
4. **Is this likely one shared root cause, or many independent
   causes?** Cite evidence either way.
5. **What does PASS look like for this milestone?** Define the
   closure condition before starting (e.g., "PASS count ≥ N",
   "wasm_target.sc moves PARSE_FAIL → SEMA_FAIL or better",
   "all E_ARG_COUNT diagnostics with ref-typed callees gone").
6. **What is the minimal reproducer?** If none exists yet, the first
   work item is creating one.
7. **What was tried in prior sessions?** Read the relevant prior
   release notes and final reports. List what was already discovered.
8. **What can break?** List ≥ 3 prior gates / behaviors that the
   intended change could regress.

---

## 4. Root cause map

Required when ≥ 2 files share a failure class.

For each failing file:
| File | Class | Diagnostic excerpt | Construct cited | Hypothesised root cause |

Then:
- **Shared root cause hypothesis** — state explicitly: ONE shared
  cause, or N independent causes? Evidence?
- **If shared:** locate the single producer (function + file + line)
  responsible for the symptom across all sites.
- **If independent:** rank by unlock value (per §9) and fix in
  isolation.

The root cause map is what would have prevented multiple v21.3.x
loops. **Symptom chasing is forbidden** when multiple files exhibit
the same class — locate the shared producer first.

---

## 5. Dependency map

For each unit of implementation work, state what must exist before it
can land:

| Implementation step | Depends on | Owner | Status |

Implementation must respect this dependency graph. Skipping a
dependency is a sign that the plan is incomplete.

---

## 6. Regression risk map

For every prior gate / file / behavior the change could break:

| Behavior at risk | Detection gate | Mitigation | Verified post-change? |

This map is built BEFORE editing. If a behavior at risk has no
detection gate, building that gate becomes a required prerequisite
artifact.

---

## 7. Fixture plan

Required: minimal repro fixtures for every blocker class.

For each blocker:
| Blocker | Fixture file | Expected pre-fix output | Expected post-fix output | Witness assertion |

Rules:
- Fixtures live under `tests/fixtures/<category>/` or
  `tests/<category>/<milestone>/probes/`.
- Pre-fix output must be captured BEFORE editing.
- Post-fix output must be captured AFTER editing and matched against
  the expected.
- If a minimal fixture cannot be made yet, document why (e.g.,
  "requires v21.5 fixed-array type form to express the failing
  construct without unrelated parser noise").

---

## 8. Gate plan

Build the gate matrix BEFORE writing the fix.

For every blocker:
| Gate | Asserts | Fails on (pre-fix) | Passes on (post-fix) | Wired into near_term_success? |

Four required gate categories:
1. **Proves the fix** — fixture compiles cleanly, diagnostic absent.
2. **Proves no regression** — prior behavior preserved.
3. **Proves native behavior** — fix is in the native compiler, not
   a scaffold (cites the native owner file + function + line).
4. **Proves no fake PASS** — artifact written, rc=0, no forbidden
   diagnostic tokens in output.

Gates that don't yet exist must be authored as part of the milestone.

---

## 9. Unlock forecast

State the EXPECTED outcome before measuring.

| Metric | Pre-fix | Post-fix (expected) | Post-fix (actual) — fill at seal |
|---|---|---|---|

Required dimensions:
- audit PASS count (or equivalent)
- per-class counts (PARSE_FAIL, IMPORT_FAIL, SEMA_FAIL, UNKNOWN)
- phase movement per affected file:
  LEX clean → PARSE clean → IMPORT clean → TYPE clean → SEMA clean
  → OBJECT emitted → LINKED → REALIZED

A fix that moves a file from PARSE_FAIL to SEMA_FAIL is a real win
even if PASS count is unchanged. Phase movement is a first-class
metric, not a consolation prize.

---

## 10. Implementation sequence

Step-by-step order in which code is edited.

1. Author missing gates (so failures are immediately detectable)
2. Author minimal fixtures (so the bug is reproducible)
3. Capture pre-fix evidence (so the delta is provable)
4. Apply the fix — smallest surgical change that closes the root
   cause
5. Rebuild, re-run gates
6. Capture post-fix evidence
7. Update baseline / class snapshot if class movement occurred
8. Write release note + final report (with native-vs-scaffold table)
9. Commit + (if authorized) tag
10. Post-tag re-run of full gate

Out-of-order execution must be justified explicitly. Skipping step 2
(fixture before fix) is forbidden unless §7 documented why a fixture
cannot exist yet.

---

## 11. Advisor review requirement

The advisor() tool MUST be called at the following points:

1. **After §4 (root cause map)** — before committing to ONE-cause or
   N-causes interpretation
2. **After §6 (regression risk map)** — before editing
3. **Before declaring done** — verify the seal claims are honest
4. **If the implementation produces a result outside the unlock
   forecast** — surface the discrepancy

Advisor feedback is not optional. Disagreement with advisor must be
documented with primary-source evidence; ignoring it without
documentation is a violation.

---

## 12. Red team review requirement

Either:
- a follow-behind auditor agent, OR
- explicit self-red-team in the final report

must answer:
- Could the PASS bump be hidden by a classifier gap?
- Could a stale assertion mask a regression?
- Could the fix produce false positives elsewhere (silenced kind
  checks, etc.)?
- Is the scaffold-vs-native attribution honest?
- Could "PASS count" be inflated by emit-direct treating empty
  inputs as valid?

Each question gets a YES / NO + evidence citation.

---

## 13. No passive deferral rule

The word "defer" is forbidden as an escape hatch.

If work cannot be completed in the current milestone, it remains an
ACTIVE BLOCKER with:
- root cause (or "investigation pending")
- owner (named function/file/line OR named investigation step)
- implementation path (sequence of fixes)
- required gates (which existing or new gates prove closure)
- sequence position (which milestone closes it)
- closure condition (exact, measurable)

Sequencing work is allowed and encouraged. Pretending work is
"deferred" when it is actually abandoned is forbidden.

Allowed language: active blocker, sequenced next, implementation
queue, closure path, required prerequisite, fix plan, owner,
evidence gate, must be completed.

Forbidden: "defer X to later" without the six-field record above.

---

## 14. No shortcut rule

This skill does not exist to delay implementation. It exists to make
implementation surgical.

If the One Shot Plan is taking longer than the implementation itself
would have taken — that is usually a sign the implementation was
going to fail. The plan surfaces the failure cheaply.

Forbidden shortcuts:
- Writing the One Shot Plan AFTER coding (post-hoc rationalisation).
- Skipping §4 root cause map when ≥ 2 files share a class.
- Skipping §7 fixture plan because "we'll add fixtures later."
- Skipping §11 advisor review because "the fix is obvious."
- Approving a tag before §12 red team review.

A plan that says "this is a single isolated bug" must cite primary
evidence for the isolation claim. "It seems isolated" is not evidence.

---

## 15. Final readiness checklist

Before implementation begins, verify ALL of the following:

```
[ ] §3  Preflight questions answered with primary-source citations
[ ] §4  Root cause map filled (or N/A if single-file)
[ ] §5  Dependency map filled
[ ] §6  Regression risk map filled
[ ] §7  Fixture plan written; missing fixtures authored as
        prerequisite work
[ ] §8  Gate plan written; missing gates authored as prerequisite
        work
[ ] §9  Unlock forecast captured
[ ] §10 Implementation sequence drafted
[ ] §11 Advisor reviewed §4 + §6
[ ] §13 No passive deferral language
[ ] §14 No shortcut taken
[ ] §17 Pre-flight empirical baseline verified from documented PWD;
        discrepancies with handoff surfaced
[ ] §18 Every handoff file:line bug + architectural claim empirically
        re-verified at HEAD; discrepancies resolved
[ ] §19 Post-implementation A/B verification record produced for any
        "pre-existing failure", flake, or "harness-not-source" claim;
        predecessor-SHA output + HEAD output captured side-by-side
        before session-close pre-seal
```

If any box is unchecked, implementation is BLOCKED until it is.

---

## 16. Required output template

The agent MUST produce a document at
`docs/plans/<milestone>_one_shot_plan.md`
following this exact structure (see also
`docs/templates/ONE_SHOT_EXECUTION_PLAN_TEMPLATE.md` for the
copy-ready form):

```
# One Shot Execution Plan — <milestone>

## 1. Mission
What is failing and why this milestone exists.

## 2. Current Baseline
Current tag, current PASS count or equivalent, current failing
files, current phase classes.

## 3. Failure Map
Every file affected by the blocker, grouped by failure class.

## 4. Shared Root Cause Analysis
ONE-cause or N-causes? Evidence?

## 5. Dependency Map
What must exist before this fix can land.

## 6. Implementation Options
≥ 3 options when the fix is complex: minimal, canonical,
architectural.

## 7. Selected Implementation Path
Which option, and why.

## 8. Regression Risk Map
What can break.

## 9. Fixture Plan
Per-blocker fixtures.

## 10. Gate Plan
Which gates prove the fix, no regression, native behavior, no fake
PASS.

## 11. Unlock Forecast
Expected outcome dimensions.

## 12. Implementation Sequence
Step-by-step coding order.

## 13. Stop Conditions
When to stop before coding further.

## 14. Closure Condition
Exact definition of done.

## 15. Advisor Decision
Advisor's response on §4 + §6, recorded verbatim.

## 16. Red Team Review
Auditor or self-red-team Q&A.

## 17. Final Report Requirements
Evidence required before seal.

## 18. Active Blocker Records
Six-field records for every blocker NOT closed in this milestone
(per doctrine §3 — sequencing language only, no passive deferral).
Each record: root cause, owner, implementation path, required
gates, sequence position, closure condition.
```

---

## 17. Pre-Flight Empirical Baseline Verification

**DIRECTIVE: Trust no baseline number until you reproduce it from the
documented working directory.**

This section is MANDATORY before §3 preflight questions are answered.
Baseline numbers in handoff documents are NOT empirical until the
current agent reproduces them. The empirical lesson:
`scc_smoke` reports `127/0` ONLY when invoked from `compiler/scc/`;
the SAME script invoked from `superc-v1/` reports `1/122`. A handoff
that says "scc_smoke: 127/0" without specifying the PWD requirement
will silently mislead any agent who skips empirical re-verification.
An agent could then spend hours "fixing" non-existent regressions.

### 17.1 Mandatory baseline verification steps

Before drafting the One Shot Plan, run each of the following and
record the actual outputs in the plan:

1. **Identify the EXACT PWD required by each gate, test, smoke
   harness, or audit script.** Do NOT trust the handoff's implicit
   working directory. For every gate cited in the handoff, locate
   the script (`find . -name <script>` or similar) and read its
   header / source to determine the PWD it requires. If the script
   uses relative paths, the PWD requirement is load-bearing.
2. **Run baseline gates from documented PWD before any design.**
   Run scc_smoke (or equivalent) from the PWD the script requires,
   AND from at least one other plausible PWD (e.g., repo root) to
   confirm the PWD-sensitivity. Record both outputs.
3. **Capture actual numbers:**
   - actual `scc_smoke` PASS / FAIL count from documented PWD
   - actual `gold_gate` (or equivalent integration gate) PASS count
   - actual reproduction signal for each named blocker
     (e.g., SCC_O1_DUMP output, segfault RC, parser diagnostic)
4. **Compare to handoff claims:**
   | Metric | Handoff claim | Empirical reading | PWD used | Match? |
   |---|---|---|---|---|
5. **Surface discrepancies.** If any handoff number differs from the
   empirical reading by more than measurement noise, HALT design
   and surface to user/advisor with: (a) the handoff text verbatim,
   (b) the empirical command + output, (c) the PWD used, (d) the
   delta. Do not silently re-baseline.

### 17.2 Baseline section in the One Shot Plan

The One Shot Plan template §2 "Current Baseline" MUST include:
- working directory for each cited gate (absolute path)
- exact command invoked
- exact output captured (or relevant excerpt)
- date / commit hash at which the baseline was captured

A baseline citation without these four fields is INCOMPLETE and the
plan is not ready for advisor review.

### 17.3 What this rule does NOT allow

- Inheriting a baseline number from a prior session report without
  re-running the gate at HEAD.
- Citing a PASS count that was captured before the current uncommitted
  edits without re-running.
- Assuming the handoff's PWD when the script's source disagrees.
- Treating "I ran it once and it worked" as proof that the PWD is
  correct for THIS session.

---

## 18. Handoff Re-Verification Mandate

**DIRECTIVE: Every named bug, every file:line target, every
architectural claim in a handoff is a HYPOTHESIS until empirically
re-verified at HEAD.**

This section is MANDATORY before §4 root cause map is filled.
Handoff documents frame the problem; inheriting that framing without
empirical re-verification can mis-design the fix. The empirical
lesson: a handoff named 4 specific bugs at file:line targets.
SCC_O1_DUMP confirmed 3 of the 4 at HEAD, but the parser-vs-sema
location of Bug 4 was UNCERTAIN and required investigation. Designing
the fix against the handoff's framing would have aimed at the wrong
file.

### 18.1 Mandatory handoff re-verification steps

For every claim in the handoff, the agent MUST produce empirical
evidence at HEAD before the One Shot Plan §4 is considered complete.

1. **For every named file:line bug in a handoff:**
   - Read the file at the cited line at HEAD (commit hash recorded).
   - Run an empirical probe (minimal fixture + diagnostic harness)
     that exercises the bug.
   - Confirm the bug is PRESENT at HEAD and BEHAVES as the handoff
     claims (same diagnostic text, same RC, same SCC_O1_DUMP shape,
     etc.).
   - Record the probe command, probe input, and observed output.
2. **For every architectural claim ("X lives in parser",
   "Y is computed in sema", "Z is dispatched from bridge"):**
   - `grep -n` the relevant identifier across the cited subsystem.
   - Read the matched function(s) to confirm the claim.
   - If the identifier lives in a different subsystem than the
     handoff claims, that is a DISCREPANCY and §18.2 fires.
3. **For every cited gate / fixture / smoke case:**
   - Locate the file. Confirm it exists at HEAD.
   - Read the assertion. Confirm it asserts what the handoff claims.
4. **For every closure condition cited:**
   - Confirm the gate/probe that would prove closure actually exists
     (or is in §8 gate plan as a prerequisite).

### 18.2 Discrepancy handling

If any re-verification step contradicts the handoff:
1. **Halt design.** Do not draft §4-§10 against unverified framing.
2. **Surface to user/advisor.** Provide:
   - the handoff text verbatim
   - the empirical command + output
   - the file:line read at HEAD
   - the apparent discrepancy
3. **Investigate the discrepancy until resolved.** Either:
   - the handoff was correct and the re-verification was wrong
     (re-run with care), OR
   - the handoff was wrong and the framing must be revised in §4.
4. **Record the resolution in the One Shot Plan §4** with empirical
   citation.

### 18.3 What this rule does NOT allow

- Trusting "Bug 4 is in parser" without grep + read confirmation.
- Drafting the fix sequence against the handoff's framing when
  any handoff claim has not been empirically re-verified.
- Treating "the prior agent said X" as primary-source evidence.
- Silently revising the handoff's framing in the One Shot Plan
  without surfacing the discrepancy first.

### 18.4 Re-Verification table in the One Shot Plan

The One Shot Plan §3 "Failure Map" MUST include a re-verification
table for every handoff claim:

| Handoff claim | File:line cited | Probe / grep used | HEAD result | Match? | Discrepancy resolution |
|---|---|---|---|---|---|

A failure-map row without HEAD-empirical confirmation is INCOMPLETE
and the plan is not ready for advisor review.

---

## §19 Post-Implementation Empirical A/B Verification

### Mandatory rule
Before declaring milestone complete, run the identical failing/passing gate
at BOTH:
- (a) the pre-commit-state SHA (e.g., `git stash` source + rebuild)
- (b) the current HEAD

Record both raw outputs side-by-side.

### When required
- Any claim that asserts a failure is "pre-existing" rather than "introduced by this work"
- Any flake observed under contention
- Any "harness bug, not source bug" attribution
- Session-close pre-seal

### What the A/B proves
- If predecessor ALSO exhibits the failure → claim "pre-existing" is verified
- If predecessor does NOT exhibit the failure → current work IS the regression source; revert or refine before continuing
- Either way: produces an auditable verification artifact

### Forbidden
- Dismissing flake as "intermittent" without running the A/B
- Asserting "pre-existing" based on a memory file or prior session report alone — those describe a point-in-time observation
- Skipping the A/B because "it would take a few minutes" — minutes is the budget

### Workflow
1. Detect the failure / flake during current work
2. Capture exact reproduction (command, expected vs actual)
3. `git stash` current source changes (or `git checkout <pre-commit-SHA> -- <files>`)
4. Rebuild artifacts to predecessor state
5. Re-run the exact reproduction; capture output
6. Restore current source (`git stash pop` or `git checkout HEAD -- <files>`); rebuild
7. Append A/B record to closure report

### Empirical anchor
v31.5.I.F1.a session — advisor caught the author declaring "gold_gate flake is pre-existing harness retry-storm" without running the A/B. The A/B (deferred to next session due to permission constraints) is the only honest verification. The closure report §3 now documents the claim as UNVERIFIED rather than asserting it as proven.

### Cross-references
- `sc-empirical-surface-probe` (the probe methodology itself)
- `gate-harness-process-isolation` (when the A/B isolates harness as source)
- `gate-contention-isolation` (when the A/B isolates contention)

---

## Skill enforcement summary

| Rule | Required artifact | Required gate | Required checklist item | Required report section |
|---|---|---|---|---|
| Preflight questions | One Shot Plan §3 | — | §15 box 1 | §17 of final report |
| Root cause map | One Shot Plan §4 | — | §15 box 2 | §17 of final report |
| Dependency map | One Shot Plan §5 | — | §15 box 3 | §17 of final report |
| Regression risk map | One Shot Plan §6 | gate per behavior at risk | §15 box 4 | §17 of final report |
| Fixture plan | fixture file(s) | new gate per fixture | §15 box 5 | §17 of final report |
| Gate plan | new gate scripts | wired into near_term_success | §15 box 6 | §17 of final report |
| Unlock forecast | One Shot Plan §9 + actuals | PASS-count gate | §15 box 7 | §17 of final report |
| Implementation sequence | One Shot Plan §10 | — | §15 box 8 | §17 of final report |
| Advisor review | One Shot Plan §15 | — | §15 box 9 | §17 of final report |
| No passive deferral | full doc scan | claim hygiene gate | §15 box 10 | §17 of final report |
| No shortcut | post-hoc audit | — | §15 box 11 | §17 of final report |
| Pre-flight baseline verification | One Shot Plan §2 (PWD + cmd + output + commit) | baseline-from-documented-PWD gate | §15 box 12 | §17 of final report |
| Handoff re-verification | One Shot Plan §3 re-verification table | per-handoff-claim probe gate | §15 box 13 | §17 of final report |
| Post-implementation A/B verification | A/B verification record (predecessor-SHA output + HEAD output, side-by-side) | identical-gate-run-at-both-SHAs | §15 box 14 | §17 of final report |

Every rule maps to an enforceable artifact. None of this is decorative.

---

## Continuous refinement

After every milestone that uses this skill:
1. Note any plan section that proved underspecified
2. Update the relevant section here
3. Add the new failure mode to the gate plan template
4. Increment skill version

Version: 1.2.0 — adds §19 Post-Implementation Empirical A/B
Verification, surfaced during v31.5.I.F1.a closure session
(2026-05-26):
  - LESSON 3: Advisor caught the author asserting "gold_gate flake is
    pre-existing harness retry-storm" without running the A/B at the
    predecessor SHA. The only honest verification of a "pre-existing"
    claim is to run the identical gate at both (a) the pre-commit
    state and (b) HEAD, side-by-side. Memory files and prior session
    reports describe a point-in-time observation — they cannot stand
    in for empirical re-confirmation at HEAD. Closure reports must
    document such claims as UNVERIFIED unless the A/B record is
    present.

Version: 1.1.0 — adds §17 Pre-Flight Empirical Baseline Verification
and §18 Handoff Re-Verification Mandate, surfaced during
GB-FIELD-LOWERING-001 closure session (2026-05-26):
  - LESSON 1: scc_smoke reports 127/0 only from compiler/scc/;
    1/122 from superc-v1/. Handoff PWD assumption was load-bearing
    and unstated. PWD-sensitivity of every gate must be empirically
    re-verified before design.
  - LESSON 2: Handoff named 4 specific file:line bugs; SCC_O1_DUMP
    confirmed 3 but parser-vs-sema location of Bug 4 was UNCERTAIN.
    Every handoff claim is a hypothesis until empirically
    re-verified at HEAD.

## §10 — Empirical Pre-Check Between Phases (v1.3 anchor: F1.runtime episode)

When a multi-phase plan depends on a prior phase's claim (e.g., "F1.c2
helper already lands the dispatch arm" — but does it really?), the next
phase MUST re-verify empirically BEFORE authoring its design. Read the
current source, dump the AST/IR, run a probe — do NOT trust the handoff
or the prior session's progress report at face value.

Anchor: F1abc session progress report claimed F1.c (kind_compound_assign
field-LHS) had landed in commit `e161b77a`. Phase 6 of the F1.runtime →
H.8 plan empirically verified this BEFORE designing F1.c2 — and found
`lower_field_compound_assign` did NOT exist. Phase 6 then implemented it
+ wired the dispatch + closed the gap. Without the empirical pre-check,
the plan would have assumed the helper existed and moved on, leaving
`p.pos += 1` patterns in m7s_parse.sc silently dropping in H.7.

Same pattern protected against:
- The "F1.d void RET" hypothesis. Empirical probe in Phase 7 REFUTED it
  (helper ends with `ret` unconditionally; RC=42 not 99). Saved ~100 LOC
  of speculative codegen change.
- The Pass 4.20 sub-pass B regression in Phase 3. The struct_stack_alloc
  gate caught it pre-commit because the empirical probe ran against the
  new build, not the assumed shape.

**Rule:** every plan phase opens with a verify-the-prior-phase step that
either confirms or refutes the assumed state. The fixed cost (~5 minutes
of probe + read) saves ~hours of speculative debug downstream.

Version: 1.3.0 — refined 2026-05-26 from 1.0.0
- v1.3.0 (2026-05-26): Added §10 "Empirical Pre-Check Between Phases".
  Anchored to F1.runtime → F1.c2 → F1.d → H.8 plan execution where every
  phase pre-check empirically refuted or confirmed the prior phase's
  claim, preventing speculative implementation drift.
- v1.0.0 (2026-05-13): initial from v21.3.D corrective sprint.

Trigger for revision: any milestone where the One Shot Plan failed
to surface a root cause the implementation later revealed.
