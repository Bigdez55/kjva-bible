# Playbook: SKILL_SC_RED_TEAM_PREFLIGHT_001
# SUPER C Red-Team Preflight

## Skill ID
SKILL_SC_RED_TEAM_PREFLIGHT_001

## Layer
governance

## Domains
red-team, adversarial-review, governance

---

## Purpose

Challenge every SUPER C execution order BEFORE it reaches a coding agent.

This skill exists because Gold-tier orders have been issued without an
adversarial preflight pass, and known blockers have surfaced AFTER bytes
were written. The cost of a 30-minute red-team is always less than the cost
of rolling back a Gold seal and re-running gates.

The skill operates on a draft execution order plus project state and emits
one of four verdicts. NO order may reach an implementation agent without a
verdict from this skill recorded in the order's preflight section.

Adversarial posture is mandatory. The reviewer must actively look for
reasons to BLOCK, not for reasons to approve. APPROVED is the rarest
verdict; APPROVED_WITH_CAVEAT is the expected default for non-trivial work.

---

## When to Use

| Trigger                                       | Required? |
|-----------------------------------------------|-----------|
| Every implementation handoff to a coding agent| YES       |
| Every Gold-tier seal order                    | YES       |
| Every order that touches parser / sema / IR   | YES       |
| Every order that crosses a sub-blocker        | YES       |
| Every order that mentions "v__.0" anchor tags | YES       |
| Every order issued after a failed gate run    | YES       |
| Pure doc-only change (no code, no gate change)| NO        |
| Test-only addition that cannot regress builds | NO        |

If in doubt: run it. This skill is cheap; a Gold rollback is not.

---

## Inputs

| Parameter        | Type    | Description                                                       |
|------------------|---------|-------------------------------------------------------------------|
| draft order      | doc     | The execution order being proposed, in its pre-handoff state      |
| project state    | yaml    | `19_truth_state/current.truth.yaml` + latest near-term gate count |
| prior reports    | dir     | Last 5 sealed-tag reports + last 3 honesty-queue deltas           |
| gate inventory   | list    | Every gate currently wired into `near_term_success.sh`            |

If any input is missing or older than the order being reviewed, the
verdict is automatically BLOCKED with reason `stale_inputs`.

---

## Required Challenge Matrix

The reviewer MUST work through all 15 challenges in order. For each
challenge, the output is one of: `PASS`, `CAVEAT`, `FAIL`, or `N/A` with
a single-sentence justification. `N/A` requires explicit reasoning, not
silence.

| #  | Challenge                                                                                   |
|----|---------------------------------------------------------------------------------------------|
| 1  | Are all named prerequisite blockers actually CLOSED (not deferred, not partially closed)?   |
| 2  | Does any cited parent tag exist on `main`, and does its child-gate count match its claim?   |
| 3  | Is every gate referenced in the order currently wired into `near_term_success.sh`?          |
| 4  | Does the order conflate "scaffold present" with "behavior verified"? (cf. v31 Gold surprise)|
| 5  | Are honest-disclosure deltas (DELTA-00x) acknowledged and addressed, not silently inherited?|
| 6  | Does the order ask for any deletion or destructive git operation on shared `main`?          |
| 7  | Does the scope match the issuing memo verbatim, or has it expanded mid-draft?               |
| 8  | Are the seal artifacts (tag, sub-tags, parent tag) ordered correctly (children BEFORE parent)?|
| 9  | Does the order cite empirical evidence (gate output, byte diff) or only intent claims?      |
| 10 | Is the agent given a concrete halt condition if a gate breaks mid-run?                      |
| 11 | Does any work require a new gate? If yes, is the gate authored BEFORE the work it gates?    |
| 12 | Are any "trusted but unverified" deps (clang cross, qemu, host libc) flagged for record?    |
| 13 | Does the order respect the GENOSCOPY-only scope rule (where it applies)?                    |
| 14 | Is the deliverable spec falsifiable, or is it phrased so any output can be called success?  |
| 15 | If this order succeeds, what does the NEXT order look like? (catches dead-end work)         |

Any matrix row marked `FAIL` forces the verdict to `BLOCKED`. A `CAVEAT`
on rows 1, 2, 3, 4, 5, or 8 forces verdict to at most `APPROVED_WITH_CAVEAT`
and the caveat MUST be written into the order before handoff.

---

## Required Question

After the matrix is complete, the reviewer MUST answer this one question
in writing, in plain language, BEFORE selecting a verdict:

> "If a coding agent runs this order start-to-finish and every command
>  succeeds, will the project be measurably and verifiably closer to
>  the milestone the order claims to advance — or will we have produced
>  a green log over a fundamentally unchanged state?"

The answer must reference at least one specific artifact (a tag, a gate,
a file path, a byte count) that would be different after the order runs.
"The seal would be tagged" is NOT a sufficient answer — that is the seal
of work, not the work itself.

If the reviewer cannot answer this without hand-waving, the verdict is
`BLOCKED` with reason `intent_without_artifact`.

---

## Required Output

The reviewer emits a structured red-team report with exactly one of four
verdicts. The report is written to:

```
audits/red_team/RTP-<order-id>-<YYYY-MM-DD>.yaml
```

Schema:

```yaml
red_team_preflight_id: RTP-<order-id>-<YYYY-MM-DD>
skill_id: SKILL_SC_RED_TEAM_PREFLIGHT_001
reviewer: <agent-or-human-id>
reviewed_at: <ISO8601 timestamp>
order_under_review:
  id: <order-id>
  draft_path: <path>
  issued_by: <author>
inputs_freshness:
  truth_state_age_hours: <int>
  gate_inventory_age_hours: <int>
  prior_reports_age_hours: <int>
challenge_matrix:
  - id: 1
    name: prerequisite_blockers_closed
    result: PASS | CAVEAT | FAIL | N/A
    justification: <one sentence>
  # ... rows 2 through 15
required_question:
  answer: <plain-language paragraph>
  cited_artifacts: [<tag>, <gate>, <path>, ...]
verdict: APPROVED | APPROVED_WITH_CAVEAT | BLOCKED | FAILED
verdict_reason: <one paragraph>
caveats_for_order:
  - <caveat that must be written into the order before handoff>
blocked_required_if_hits:
  - <list of any of the 5 BLOCKED-required conditions that fired>
recommended_next_step: <single concrete action>
```

### Verdict Definitions

- **APPROVED** — All 15 matrix rows PASS, required-question answer is
  artifact-grounded, no BLOCKED conditions hit. Order may be handed to
  coding agent unchanged. This verdict is rare; expect to see it on
  small, well-scoped slices.

- **APPROVED_WITH_CAVEAT** — All 15 rows PASS or CAVEAT, no FAIL, no
  BLOCKED conditions hit. Order MAY be handed off ONLY AFTER every
  caveat in `caveats_for_order` is written into the order text. The
  reviewer must verify the rewrite before the agent starts.

- **BLOCKED** — Any matrix FAIL, any BLOCKED-required condition hit,
  or required-question answer is not artifact-grounded. Order does NOT
  go to a coding agent. The issuing author must revise and re-submit
  for a fresh preflight.

- **FAILED** — Used ONLY when the preflight itself could not run:
  missing inputs, malformed order, inputs older than the order. This
  is a workflow defect, not an order defect. Returned to issuer with
  the missing-input list.

---

## BLOCKED Required If

The verdict MUST be `BLOCKED` (not `APPROVED_WITH_CAVEAT`) when any of
the following five conditions is present in the draft order. These are
non-negotiable. The reviewer has no discretion on these.

1. **Open prerequisite blocker.** Any named prerequisite blocker is
   currently in state `open`, `partial`, or `deferred`. Closing a
   blocker is a separate order; it cannot be bundled into a Gold seal.

2. **Parent-before-child seal.** The order proposes tagging a parent
   anchor (e.g. `v__.0.X`) before all child sub-tags (`v__.0.X.a`,
   `.b`, `.c`) exist on `main` with green gates. Per the v22.0.A4C1
   pattern, parent tagging is contingent on child completion.

3. **Scaffold-as-Gold.** The order treats the presence of a file
   (struct, stub, doc) as evidence of working behavior, without an
   empirical gate that exercises the behavior end-to-end. This is the
   v31 Gold-order surprise pattern and is explicitly forbidden.

4. **Gate authored after work.** The order requires a new gate to
   prove its claim, but proposes writing the gate AFTER the work it
   gates. Gates must exist and be wired into `near_term_success.sh`
   BEFORE the work they audit lands.

5. **Destructive git on shared main.** The order proposes
   `git reset --hard`, rebase-rewrite, `--force` push, or branch
   deletion on `main` during a window when parallel agents are known
   to be active. Per project memory, these operations are forbidden
   in that window; isolation must use `git stash`.

If any of these five fire, the BLOCKED verdict stands even if the
matrix is otherwise clean.

---

## Failure Mode This Skill Prevents

This skill exists because of **SC-MISS-001 — v31 Gold order surprise**.

What happened: a Gold-tier execution order for v31 was issued, the
coding agent began work in good faith, and partway through the run an
upstream blocker that should have been closed surfaced as still-open.
The agent's choices were (a) halt and discard work, (b) press on and
risk a false Gold seal over an unresolved blocker, or (c) escalate.
Escalation cost time; option (b) would have cost integrity.

Root cause: no adversarial preflight pass was performed on the order.
The blocker's open state was visible in the truth-state file, but the
order's author had not been forced to walk the prerequisite list with
an adversarial reviewer. The author trusted their own assumption that
the blocker was closed.

This skill makes that trust check non-bypassable. Matrix row #1
("Are all named prerequisite blockers actually CLOSED, not deferred,
not partially closed?") would have caught SC-MISS-001 before the
coding agent saw the order.

The cost of this preflight is on the order of 15–30 minutes of
reviewer time per order. The cost of the v31 Gold surprise was a
half-day of agent time plus a credibility hit on the seal log. The
ratio favors running this skill every time, without exception.

---

## Post-Run Actions

**If verdict is `APPROVED`:**
- Attach the RTP report to the order under `preflight:` section.
- Hand off to coding agent.
- Archive the RTP report under `audits/red_team/`.

**If verdict is `APPROVED_WITH_CAVEAT`:**
1. Rewrite the order text to incorporate every caveat in
   `caveats_for_order`. Caveats are not footnotes — they are part of
   the order body.
2. Re-run this skill on the rewritten order. The rewrite changes
   inputs, so a fresh preflight is required.
3. If the second pass returns `APPROVED`, hand off.
4. If the second pass returns `APPROVED_WITH_CAVEAT` with NEW caveats,
   the order is too complex for one slice — split it.

**If verdict is `BLOCKED`:**
1. Return the RTP report to the order's author.
2. Author addresses every `FAIL` row and every fired BLOCKED-required
   condition. Addressing may require closing a prerequisite blocker,
   re-scoping the order, or authoring a missing gate first.
3. Author resubmits the revised order for fresh preflight.
4. Do NOT hand off a BLOCKED order even with verbal sign-off. The
   verdict is the gate.

**If verdict is `FAILED`:**
1. Return to issuer with the missing-input list.
2. Issuer regenerates inputs (re-run truth state, refresh gate inventory).
3. Resubmit for preflight.

---

## Logging and Audit

Every preflight run, regardless of verdict, is appended to:

```
audits/red_team/PREFLIGHT_LOG.yaml
```

as a single line:

```yaml
- rtp_id: RTP-<order-id>-<YYYY-MM-DD>
  order_id: <order-id>
  verdict: APPROVED | APPROVED_WITH_CAVEAT | BLOCKED | FAILED
  blocked_conditions: [<list or empty>]
  reviewer: <id>
  reviewed_at: <ISO8601>
```

The log is the audit trail. It supports later "did we red-team this?"
queries during post-mortem analysis. The log is append-only; entries
are never edited or deleted.

---

## Related Skills

- `SKILL_TRUTH_STATE_CHECK_001` — supplies the project-state input;
  run BEFORE this skill so the truth state is current.
- `SKILL_DRIFT_DETECTION_001` — surfaces drift the matrix may catch
  in rows 1, 2, and 3.
- `SKILL_PROOF_MATRIX_001` — formalizes the artifact-grounded answer
  to the required question.
- `one-shot-execution-planning` (agent skill) — complements this
  preflight; that skill plans the work, this skill challenges the plan.

---

## Validation

`TEST_SKILL_SC_RED_TEAM_PREFLIGHT_001_001` verifies:

1. An order citing a known-open blocker produces verdict `BLOCKED` with
   reason citing matrix row #1.
2. An order proposing a parent tag before its child sub-tags exist
   produces verdict `BLOCKED` via condition #2.
3. An order claiming Gold based only on the presence of a scaffold
   file (no gate exercising behavior) produces verdict `BLOCKED` via
   condition #3.
4. An order with all 15 matrix rows PASS, artifact-grounded required
   answer, and no BLOCKED conditions produces verdict `APPROVED`.
5. A well-formed order with one CAVEAT on a non-critical row produces
   `APPROVED_WITH_CAVEAT` and the caveat appears in `caveats_for_order`.
6. A preflight run with truth-state input older than the draft order
   produces verdict `FAILED` with reason `stale_inputs`.

See `08_verification/skill_tests/TEST_SKILL_SC_RED_TEAM_PREFLIGHT_001_001.yaml`.

---

## Notes for the Reviewer

- The matrix is not a checklist to skim. Each row is a question to
  answer with evidence from the inputs. Silence on a row equals FAIL.

- "APPROVED" should feel rare. If you find yourself approving most
  orders, you are not being adversarial enough. Re-read the v31
  Gold surprise post-mortem.

- The required question is the single most important step. A clean
  matrix with a hand-wavy answer to the required question is still
  `BLOCKED`. The matrix catches mechanical defects; the required
  question catches conceptual defects.

- Caveats are not suggestions. If the order is not rewritten to
  include them verbatim, the second-pass preflight will catch the
  omission and downgrade to `BLOCKED`.

- This skill applies to YOU, the reviewer, too. If you find yourself
  reasoning "this order is from a trusted author, so I'll be lenient,"
  stop. The whole point of SC-MISS-001 is that trusted authors miss
  things. Run the matrix.

---

## Challenge Matrix Extensions (per SC-MISS-002 + SC-MISS-003)

The matrix has 15 rows. The following 4 rows are MANDATORY additions; their omission downgrades the review to `BLOCKED` automatically.

| # | Challenge | Failure mode | Reject phrase |
|---|---|---|---|
| 16 | Did any sub-wave silently bypass an earlier `BLOCKED`/`PARTIAL`/`MISSING_PREREQUISITE` verdict without invoking the Wave-Sequencing Contract 7-step escalation (per `SKILL_SC_AGENT_EXECUTION_ORDER_001` Wave-Sequencing Contract)? | Sub-wave override = SC-MISS-002 recurrence. | "Sub-wave Y produced workaround for sub-wave X's BLOCKED verdict without invoking the 7-step escalation. Reject." |
| 17 | Does every claim about a compiler subcommand, intrinsic, codegen path, or stdlib primitive cite an EMPIRICAL PROBE against the actual built binary (per `SKILL_SC_AGENT_EXECUTION_ORDER_001` Empirical Surface Probe Mandate)? | Build-graph greps + source scaffolds substituted for probes = SC-MISS-003 recurrence. | "Claim X cites only source-file evidence; no `scc <subcommand>` invocation captured. Reject." |
| 18 | Is "parse-clean" being conflated with "runtime-verified"? Has the reviewer confirmed that all execution claims have a corresponding `run-jit` / `emit-direct` / executable invocation in the evidence? | Parse-clean ≠ runtime-verified is the v31.2 surprise pattern. | "Implementation parses but no execution evidence. Closure rejected; revise to PARSE-ONLY status." |
| 19 | If the order's expected verdict is PASS or PASS_WITH_CAVEAT, are the load-bearing intrinsics empirically verified per Row 17? Specifically: `__load_u{8,32,64}__`, `__store_u8__`, `__syscall__`, `__strdata__` — none have codegen recognition in the seedc/scc backends as of 2026-05-17 v31.3 I4. Any forecast that assumes them must include a `tests/diagnostics/probe_*.sc` run with non-fold `path` evidence. | Assuming intrinsic codegen without probe = SC-MISS-003. | "Forecast assumes `__store_u8__` codegen; v31.3 I4 + A6 prove it BLOCKED. Reject without empirical re-verification." |

---

## SC-MISS-002 + SC-MISS-003 Regression Examples

**SC-MISS-002 (Wave-Sequencing Contract):** v31.2 sub-wave B2 authored 341 LOC SHA-256 using parse-only intrinsic workarounds AFTER A5 declared `BLOCKED_BY_MISSING_PRIMITIVE`. B2 did not invoke the 7-step escalation. v31.3 A-wave → B-wave HALT is the corrective regression — first cycle where the contract held.

**SC-MISS-003 (Empirical Surface Probe):** v31.2 final report §11 stated "scc lacks `run` subcommand" — empirical v31.3 A2 `scc help` + `streq(argv[1], "run-jit")` grep proved this false. v31.2 B2 claimed `__load_u32__` had "prior canonical usage" — v31.3 I4 census shows ZERO codegen recognition; "usage" was parse-only.

A reviewer who does not apply Rows 16-19 to every order will reproduce these misses.
