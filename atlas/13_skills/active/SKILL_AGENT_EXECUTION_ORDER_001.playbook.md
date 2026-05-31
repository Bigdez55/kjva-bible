# Playbook: SKILL_SC_AGENT_EXECUTION_ORDER_001
# SUPER C Agent Execution Order — One-File Handoff Standard

## Skill ID
SKILL_SC_AGENT_EXECUTION_ORDER_001

## Layer
governance

## Domains
handoff, agent-orchestration, communication

---

## Purpose

Produce **one complete copy-paste-ready Markdown handoff** for a coding agent
that takes a SUPER C milestone (Bronze, Silver, Gold, LTS, or interior sub-tag)
from issued to executed without surprise.

Every execution order this skill emits is:

1. A single cohesive `.md` file. Not a thread, not a sequence of messages,
   not a "see also" trail. One file the coding agent can paste into a new
   session and execute end-to-end.
2. Structured into the **15 required sections** in this playbook, in order,
   numbered.
3. Pre-loaded with the **Feasibility Forecast**, **Claim Boundary**, and
   **Red-Team Block** that the SUPER C governance stack requires before any
   implementation authorization is honest.

This skill is the standardized template that prevents SC-MISS-001 from
recurring: a Gold-class closure order issued without a feasibility forecast,
with no claim boundary on what "closure" means, and with no red-team review
of whether the milestone is reachable inside the requested session.

---

## When to Invoke

- Before dispatching ANY execution order to a coding agent.
- When converting an informal user request into a formal handoff.
- When auditing whether an issued order is honestly complete.

---

## Inputs

| Parameter            | Type      | Required | Description                                                                 |
|----------------------|-----------|----------|-----------------------------------------------------------------------------|
| milestone_spec       | yaml/path | yes      | The milestone being ordered (Bronze/Silver/Gold/LTS) with explicit exits   |
| feasibility_forecast | yaml/path | yes      | Output of `SKILL_SC_NO_SURPRISE_PLANNING_001`; classifies feasibility       |
| blocker_register     | yaml/path | yes      | Output of `SKILL_SC_DEPENDENCY_SOVEREIGNTY_001`; ACTIVE_BLOCKERs + DELTAs   |
| red_team_verdict     | yaml/path | yes      | Output of `SKILL_SC_RED_TEAM_PREFLIGHT_001`; APPROVED / WITH_CAVEAT / REJECTED |

If any input is missing, do not emit an order. Return a `BLOCKED_VERDICT`
using the template in §15 of this playbook and invoke the missing skill first.

---

## Outputs

| Artifact                              | Form                                  |
|---------------------------------------|---------------------------------------|
| one-file handoff                      | Single `.md` file, all 15 sections    |
| coding agent order                    | Embedded in §1–§12 of the handoff     |
| implementation authorization          | Embedded in §11, gated by §8/§9/§10   |
| blocked verdict template              | §15 (used when authorization withheld)|

---

## Mandatory Format

**One cohesive .md file. No split.**

The deliverable is exactly one `.md` file. It must:

- Open with a single H1 title naming the milestone (e.g. `# EXECUTION ORDER — v31 Silver Closure`).
- Carry every one of the 15 required sections below as numbered H2 headings
  (`## 1. ...` through `## 15. ...`), in order, no skipping, no renaming.
- Be **copy-paste-ready**: the coding agent should be able to paste the
  entire file into a fresh session and execute without needing to consult
  any other document for the order itself. (References to project artifacts
  are normal and expected; references that hide order content in a sibling
  message are forbidden.)
- Carry the explicit closure status of the **Feasibility Forecast** (§8),
  the **Claim Boundary** (§9), and the **Red-Team Block** (§10) before
  the **Authorization** in §11 can be `AUTHORIZED`.

Forbidden formats:

- A thread of messages where the order accumulates across turns.
- A "starter" message + a "follow-up" message that together form the order.
- A handoff file that points the agent to "see appendix A" or "see other
  document" for any of the 15 required sections. Inline the content, or
  the section is incomplete.

---

## Required Sections (15)

The order file must carry these 15 sections, in order, numbered, with the
content described.

### 1. Header / Authority / Mode / Cap

A 4–8 line block establishing:

- **Title** — `EXECUTION ORDER — <milestone>`
- **Date** — ISO 8601
- **Authority** — which governance artifact authorizes this order
  (e.g. "v31 EXECUTION ORDER §19 final synthesis", "user directive 2026-05-17")
- **Mode** — `READ-ONLY`, `READ-AND-WRITE`, `IMPLEMENTATION`, or
  `IMPLEMENTATION-WITH-COMMIT`
- **Cap** — hard limit (LOC, word count, file count, session count)
- **Tier scope** — which tier this touches (T1 pilot, T2 stdlib, T3 toolchain,
  T4 frozen ecosystem). Tier-4 writes are forbidden unless explicitly
  authorized by the user in the same order.

### 2. Starting State (HEAD + tag)

Pin the exact starting state the order assumes.

- **HEAD SHA** — full 40-char or first 8 (e.g. `847602a8`)
- **Anchor tag** — the most recent green seal (e.g. `v30.7-seedc-retirement-scc-authority`)
- **Working-tree status** — clean / dirty / known-uncommitted artifacts
- **Memory entries that frame this milestone** — list the relevant project
  memory keys (e.g. `project_post_v30_acceptance`)

If the order would be invalid against a different HEAD, say so explicitly
in this section ("This order is only valid against HEAD `847602a8`. Abort
if HEAD has moved.").

### 3. Tags Verified

List the anchor tags that must remain intact for this order to be honest.
Each tag with its SHA. If any tag has moved, the order is automatically
`BLOCKED` and §11 must downgrade.

Example:

```
- v30.7-seedc-retirement-scc-authority → 847602a8  (MUST MATCH)
- v30-ecosystem-rewrite-lts-readiness-floor → a918af74  (MUST MATCH)
- v22.0.A canonical-x86-elf → f08bc0f0  (MUST MATCH)
```

### 4. Gates to Run

Exact shell commands the coding agent will run. No abstractions, no "run
the usual gates". Concrete paths, concrete script names.

```
bash scripts/gates/near_term_success.sh
bash scripts/gates/superc_active_path_silver.sh
bash scripts/gates/non_superc_dependency_audit.sh
```

If a gate is missing, the order is BLOCKED and §11 cannot authorize.

### 5. Expected Results & Stop Rules

For each gate from §4, the expected PASS line, the expected count
(`N/N PASS, 0 FAIL`), and the **stop rule** if the gate does not match.

Stop rules are non-negotiable. Examples:

- "If `near_term_success.sh` returns non-zero, STOP. Do not proceed to
  Silver gate. Do not amend. Do not commit. Open a miss log entry."
- "If `superc_active_path_silver.sh` returns < 21/21, STOP. Report
  delta. Do not declare Silver."

### 6. Active Dependency Inventory

A current snapshot of ACTIVE_BLOCKERs and DELTAs that bear on this
milestone. Either inline a short table or reference the precise file +
line range from `non_superc_dependency_audit.sh` output.

This is not optional. If the order does not enumerate which blockers
it acknowledges, §8 (Feasibility Forecast) cannot be honest, and §11
cannot authorize.

Example minimum content:

```
ACTIVE_BLOCKERs preserved from prior milestone:
- A01 compiler/seedc/* (42 .c+.h, 32,158 LOC) — Makefile dependency
- A02 compiler/scc/src/scc_entry.c (8,725 LOC C) — host dispatch shim
- A03 tools/scld/scld.py (777 LOC Python) — DELTA-002 deferred

DELTAs honesty-queued:
- DELTA-001 scc emit forks to seedc
- DELTA-002 scld.py native-SC port deferred to post-v23.0
- DELTA-006 boot/stage0 Python duo (synth_elf_from_obj.py, synth_aarch64_elf.py)
```

### 7. Milestone Classification

State exactly which milestone class is being ordered:

- **Bronze** — minimum honest claim; documentation + audit
- **Silver** — operational predicates pass; scaffolds permitted
- **Gold** — sovereignty closure; no scaffolds; all blockers resolved
- **LTS** — multi-version stability; long-horizon

Cite the criteria document and section that defines the chosen
milestone. If the criteria are not satisfied by the current state,
the order is `BLOCKED_BY_PREREQUISITE` and §8 must show the gap.

### 8. Feasibility Forecast (REQUIRED)

This is the section SC-MISS-001 demands. The forecast must explicitly
classify the milestone against the current evidence:

- `FEASIBLE_THIS_SESSION` — all prerequisites green; one-shot closure honest
- `FEASIBLE_WITH_BOUNDED_SLICES` — closable, but only via N enumerated slices
- `BLOCKED_BY_PREREQUISITE` — cannot honestly close until listed prereqs land

Use the template below. If the forecast lands on `BLOCKED_BY_PREREQUISITE`,
§11 must NOT carry `AUTHORIZED` — it carries `WITHHELD` and references §15.

```
### Feasibility Forecast

Milestone target:   <milestone class>
Classification:     <FEASIBLE_THIS_SESSION | FEASIBLE_WITH_BOUNDED_SLICES | BLOCKED_BY_PREREQUISITE>
Evidence anchors:
  - <report path §section> — <one-line finding>
  - <report path §section> — <one-line finding>
Prerequisite gaps (if any):
  - <prereq id> — <one-line description> — owner: <slice/order> — ETA: <version target>
Estimated session count to honest closure: <1 | N | unknown>
Stop-if-discovered conditions:
  - <condition that, if found during execution, forces re-classification to BLOCKED>
```

The forecast must reference the **blocker_register** input by file path.
If the register contradicts the classification, the order is invalid.

### 9. Claim Boundary (REQUIRED)

State precisely what the order does and does not claim. The boundary
prevents an agent from declaring "v31 Gold closed" when only a doc-level
floor passed.

Template:

```
### Claim Boundary

This order, on successful completion, will support claims of the form:
  - "<verbatim claim 1>"
  - "<verbatim claim 2>"

This order will NOT support claims of the form:
  - "<forbidden overclaim 1, e.g. 'Gold sovereignty closure'>"
  - "<forbidden overclaim 2, e.g. 'seedc retired in operational path'>"

The order operates under SCAFFOLDED / SILVER / GOLD floor of:
  <one-line scope statement, e.g. "doc-floor only; operational closure deferred to Gold gate">

Any seal commit message produced under this order must carry the
verbatim claim boundary above as a quoted block.
```

The claim boundary is the structural fix for the v31 Gold misalignment:
the order's wording fixes the agent's wording.

### 10. Red-Team Block (REQUIRED)

The verdict from `SKILL_SC_RED_TEAM_PREFLIGHT_001` is inlined verbatim
here. Not a link — the verdict text. The order is BLOCKED unless this
section reads `APPROVED` or `APPROVED_WITH_CAVEAT` (with the caveats
enumerated and §9 amended to acknowledge each one).

Template:

```
### Red-Team Block

Red-team verdict:  <APPROVED | APPROVED_WITH_CAVEAT | REJECTED>
Verdict source:    <path/to/red_team_review.md §N>
Verdict date:      <ISO 8601>

Challenges raised:
  - RT-001 <one-line>  →  <status: ADDRESSED | OPEN | DEFERRED>
  - RT-002 <one-line>  →  <status>
  - RT-003 <one-line>  →  <status>

Caveats (if APPROVED_WITH_CAVEAT) — each must appear in §9 Claim Boundary:
  - <caveat 1>
  - <caveat 2>

If REJECTED: §11 carries WITHHELD and §15 BLOCKED_VERDICT is filled.
```

### 11. Tier / Pilot / Implementation Authorization

The authorization line. One of:

- `AUTHORIZED — proceed under the constraints of §1, §5, §9`
- `AUTHORIZED_WITH_CAVEAT — proceed; caveats from §10 binding`
- `WITHHELD — see §15 BLOCKED_VERDICT`

Also explicit Tier statement:

- `Tier scope: T2 stdlib only`
- `Tier scope: T1 pilot — pending separate user approval; this order does NOT auto-fire pilot`
- `Tier scope: T4 frozen ecosystem — FORBIDDEN under this order`

### 12. Output Artifacts

Enumerate the artifacts the agent must produce on successful completion:

- Report paths (`docs/reports/<milestone>_<topic>.md`)
- Evidence paths (`docs/reports/<milestone>_evidence/...`)
- Gate scripts (`scripts/gates/<milestone>_*.sh`)
- Policy files (`docs/compiler/<milestone>_<topic>_POLICY.md`)
- Memory entry draft path
- Seal commit message draft path

If the artifact does not appear here, the agent must not produce it.
If an artifact is missing at completion, the milestone is not closed.

### 13. Closure Criteria

Bullet list of what "done" looks like, in measurable terms:

- All gates in §4 returned the expected results in §5
- All artifacts in §12 exist on disk and are committed
- The Claim Boundary in §9 is preserved verbatim in the seal commit
- The Red-Team Block in §10 status is reflected in the report's verdict line
- No file outside the inputs/outputs scope was modified
- Memory entry drafted and ready for user review

### 14. Rollback / Abort Conditions

The explicit exits. The agent must abort and not seal if any apply:

- A gate from §4 fails outside its stop rule margin
- An anchor tag from §3 is found moved
- An ACTIVE_BLOCKER from §6 is found resolved by surprise (re-feasibility
  is required; the original forecast is invalidated by improvement, not
  by overclaim — log and re-issue)
- A Tier-4 lock file shows blob-SHA drift
- User issues abort directive mid-execution

On abort: produce a `<milestone>_abort_report.md` with the failed
condition, the gate output, and the unmodified working tree. Do not
attempt remediation under this order.

### 15. Sign-off / Blocked Verdict Template

If §11 authorized, §15 carries the **Sign-off Block** that the agent
fills on completion:

```
### Sign-off

Executed under: SKILL_SC_AGENT_EXECUTION_ORDER_001
Milestone:      <class + name>
Started:        <ISO 8601>
Completed:      <ISO 8601>
HEAD at start:  <SHA>
HEAD at end:    <SHA>
Tag created:    <tag name or NONE-DOC-ONLY>
Verdict:        <PASS | PASS_WITH_CAVEAT | FAIL>
Claim Boundary preserved: <YES | NO + reason>
```

If §11 withheld, §15 carries the **Blocked Verdict Template** that the
order-issuing agent fills instead:

```
### BLOCKED_VERDICT

Order: <milestone>
Status: WITHHELD
Reason:
  - <Feasibility Forecast classification = BLOCKED_BY_PREREQUISITE>
    OR
  - <Red-Team Verdict = REJECTED>
    OR
  - <Required input missing: <input name>>

Prerequisite slices to issue first (in order):
  1. <slice id> — <one-line> — target version: <vNN.M.X>
  2. <slice id> — <one-line> — target version: <vNN.M.X>

Re-issue conditions:
  - <condition 1 that, once met, this order can be re-issued>
  - <condition 2>

Recorded in: atlas/_miss_log/SUPER_C_MISS_LOG.md
Originating incident reference: <SC-MISS-NNN if applicable>
```

---

## Required Feasibility Forecast Template

(Copy of the §8 template above for ease of reuse. The order file must
inline this template populated; do not link to this playbook.)

```
### Feasibility Forecast

Milestone target:   <milestone class>
Classification:     <FEASIBLE_THIS_SESSION | FEASIBLE_WITH_BOUNDED_SLICES | BLOCKED_BY_PREREQUISITE>
Evidence anchors:
  - <report path §section> — <one-line finding>
  - <report path §section> — <one-line finding>
Prerequisite gaps (if any):
  - <prereq id> — <one-line description> — owner: <slice/order> — ETA: <version target>
Estimated session count to honest closure: <1 | N | unknown>
Stop-if-discovered conditions:
  - <condition that, if found during execution, forces re-classification to BLOCKED>
```

Rules of use:

- Classification is one of the three exact strings above. No other strings.
- Every entry in "Evidence anchors" must point to a file that exists on
  disk at the time the order is issued. If the anchor file is missing,
  the forecast is invalid.
- Every "Prerequisite gap" must reference a tracking id (slice, blocker,
  DELTA, or DEF tag).
- The "Stop-if-discovered" list is binding: discovering any such
  condition during execution forces the agent to STOP under §14.

---

## Required Claim Boundary

(Copy of the §9 template above. Inline-populate; do not link.)

```
### Claim Boundary

This order, on successful completion, will support claims of the form:
  - "<verbatim claim 1>"
  - "<verbatim claim 2>"

This order will NOT support claims of the form:
  - "<forbidden overclaim 1>"
  - "<forbidden overclaim 2>"

The order operates under SCAFFOLDED / SILVER / GOLD floor of:
  <one-line scope statement>

Any seal commit message produced under this order must carry the
verbatim claim boundary above as a quoted block.
```

Rules of use:

- "Forbidden overclaim" entries are not theoretical. They name the
  exact phrasing the order is most likely to be mistaken for
  authorizing (e.g. at v31 Silver, the forbidden claim is "Gold
  sovereignty closure").
- The seal commit message produced by the executing agent must
  quote the claim boundary block verbatim. The reviewer checks this.

---

## Required Red-Team Block

(Copy of the §10 template above. Inline-populate from the red-team
verdict input; do not link.)

```
### Red-Team Block

Red-team verdict:  <APPROVED | APPROVED_WITH_CAVEAT | REJECTED>
Verdict source:    <path/to/red_team_review.md §N>
Verdict date:      <ISO 8601>

Challenges raised:
  - RT-001 <one-line>  →  <status: ADDRESSED | OPEN | DEFERRED>
  - RT-002 <one-line>  →  <status>
  - RT-003 <one-line>  →  <status>

Caveats (if APPROVED_WITH_CAVEAT) — each must appear in §9 Claim Boundary:
  - <caveat 1>
  - <caveat 2>

If REJECTED: §11 carries WITHHELD and §15 BLOCKED_VERDICT is filled.
```

Rules of use:

- The verdict string is one of three exact values. No softening
  ("APPROVED_PROBABLY" is not legal).
- Every caveat must be reflected in the §9 Claim Boundary forbidden-claims
  list. If a caveat is not visible in §9, the order is incoherent.
- A REJECTED verdict mechanically forces §11 = WITHHELD and §15 =
  BLOCKED_VERDICT. No override path inside this skill — re-issue requires
  the red-team verdict to flip.

---

## Failure Mode This Skill Prevents

SC-MISS-001 ("v31 Gold Closure Surprise", 2026-05-17,
`atlas/_miss_log/SUPER_C_MISS_LOG.md`) is the originating
incident. Two specific failures from that miss this skill exists to prevent:

### 1. Piecemeal handoff frustration

In SC-MISS-001 the Gold order was effectively assembled across a sequence
of messages and reports, with no single cohesive Markdown file the coding
agent could paste into a fresh session. The agent had to reconstruct the
intended scope, the gates, and the closure criteria from fragments. This
created reconstruction error and user frustration — the agent and the user
spent execution time arguing about what the order actually was, instead
of about what the milestone required.

This skill prevents that by mandating: **one cohesive `.md` file, the 15
sections above, in order, numbered, with the templates inlined**. No
threaded orders. No "see other message" handoffs. The agent has one
artifact and it is complete.

### 2. v31 Gold misalignment

In SC-MISS-001 the Gold order was issued as a one-shot closure target,
when the v31 evidence already on the record (active seedc dependency,
Makefile reference to `$(SEEDC)`, 22 `.sc` files routed through seedc,
incomplete scc command surface, 777-LOC `scld.py`, 8.3K-LOC `scc_entry.c`,
3.5K-LOC scc-tools C debt) showed Gold was structurally blocked by
long-range prerequisites. The order forced the executing agent to either
fabricate closure or refuse the order — both bad outcomes.

This skill prevents that by mandating, before §11 Authorization:

- §6 Active Dependency Inventory — the blockers are named in the order itself.
- §8 Feasibility Forecast — the classification is one of three exact strings;
  `BLOCKED_BY_PREREQUISITE` is a legal outcome and mechanically forces §11
  to `WITHHELD`.
- §9 Claim Boundary — the order says out loud what it does and does not
  authorize the agent to claim.
- §10 Red-Team Block — adversarial review verdict is inlined; `REJECTED`
  mechanically forces `WITHHELD`.

If those four sections are honest, the order is honest. The agent never
again has to choose between fabrication and refusal.

---

## Related Skills

- `SKILL_SC_NO_SURPRISE_PLANNING_001` — produces the feasibility forecast
  consumed by §8.
- `SKILL_SC_DEPENDENCY_SOVEREIGNTY_001` — produces the blocker register
  consumed by §6.
- `SKILL_SC_MILESTONE_GATE_DESIGN_001` — produces the milestone criteria
  referenced by §7 and the gates listed in §4.
- `SKILL_SC_RED_TEAM_PREFLIGHT_001` — produces the verdict consumed by §10.
- `SKILL_SC_IMPROVEMENT_LOOP_001` — consumes any miss arising from a
  defective order issued under this skill (and forces a `version` bump
  here with a new `improvement_history` entry).
- `SKILL_SLICE_PLANNING_001` — used when §8 forecast is
  `FEASIBLE_WITH_BOUNDED_SLICES` to enumerate the slice list.
- `SKILL_PROOF_MATRIX_001` — supplies the evidence anchors §8 cites.

---

## Validation

`TEST_SKILL_SC_AGENT_EXECUTION_ORDER_001_001` verifies:

1. An order file with fewer than 15 sections, or any section out of order,
   is rejected by the validator.
2. An order file missing §8 Feasibility Forecast, §9 Claim Boundary, or
   §10 Red-Team Block is rejected.
3. An order whose §10 verdict is `REJECTED` but whose §11 is `AUTHORIZED`
   is rejected (mechanical-rule violation).
4. An order whose §8 classification is `BLOCKED_BY_PREREQUISITE` but
   whose §11 is `AUTHORIZED` is rejected (mechanical-rule violation).
5. An order whose §10 caveats are not reflected in §9 forbidden claims
   is rejected (incoherence).
6. A seal commit message produced under an executed order must contain
   the §9 Claim Boundary block verbatim; if not, the seal is rejected.

See `atlas/08_verification/skill_tests/TEST_SKILL_SC_AGENT_EXECUTION_ORDER_001_001.yaml`
(to be authored alongside first use).

---

## Originating Miss

SC-MISS-001 — see `atlas/_miss_log/SUPER_C_MISS_LOG.md`.

Extended by SC-MISS-002 (Wave-Sequencing Contract, 2026-05-17) and SC-MISS-003 (Empirical Surface Probe, 2026-05-17).

---

## Wave-Sequencing Contract (per SC-MISS-002)

If any agent lane reports `BLOCKED`, `PARTIAL`, or `MISSING_PREREQUISITE`, a later lane MAY NOT silently overrule that verdict.

To proceed past an earlier `BLOCKED` verdict, the integration agent MUST:

1. **Reopen** the blocker in the active register.
2. **Record** the new evidence (workaround discovery, additional probe, scope refinement).
3. **State why** the earlier verdict changed (specific assumption that was wrong, new primitive discovered, etc.).
4. **Update** the blocker register.
5. **Update** the feasibility forecast in the order's §1.
6. **Trigger** red-team review against the new evidence.
7. **Mark** the earlier report `SUPERSEDED-BY-<new evidence>` in its header — preserving the file per `feedback_no_deletion`.

A sub-wave that produces a parse-only workaround for an earlier `BLOCKED_BY_CODEGEN`/`BLOCKED_BY_RUNTIME` verdict without performing these 7 steps is itself a Wave-Sequencing Contract violation and is rejected by red-team automatically.

**Regression prompt:** "When an earlier wave reports BLOCKED_BY_*, does the next wave halt, escalate via the 7-step protocol, or proceed silently? Silent-proceed = automatic reject."

---

## Empirical Surface Probe Mandate (per SC-MISS-003)

Before any §1 feasibility forecast that depends on a compiler subcommand, intrinsic, codegen path, or stdlib primitive, the planner MUST run an EMPIRICAL PROBE against the actual built binary. The probe must:

1. Invoke the binary (e.g. `./compiler/scc/build/scc help`, `./compiler/scc/build/scc run-jit <minimal.sc>`).
2. Capture verbatim output.
3. Compare output to the assumption being made in the forecast.
4. If output contradicts the assumption, REVISE the forecast and re-enter §1.

Documentation, prior reports, source-file scaffolds, and build-graph greps are NOT substitutes for empirical probes. Build-graph presence ≠ codegen presence ≠ runtime execution.

**Example violations the probe would have caught:**
- v31.2 final report §11 claimed "scc lacks `run` subcommand" — empirical `scc help` shows `run-jit` (just unlisted in help text).
- v31.2 B2 claimed `__load_u32__`/`__load_u64__` have "prior canonical usage" — empirical I4 census shows zero codegen recognition; usage was parse-only.
- v31.1 claimed "minimal/empty .text" for emit-direct — empirical `scc emit-direct + file(1)` shows real 78-byte .text in 776-byte ELF-64.

**Regression prompt:** "What empirical probe against the actual binary supports this forecast claim? If none, you cannot make the claim."

---

## Improvement History

- **v1.0.0** — Initial from SC-MISS-001 + user's "one complete Markdown file"
  directive. Mandates one cohesive .md file, 15 numbered sections, inlined
  Feasibility Forecast / Claim Boundary / Red-Team Block templates, and
  mechanical-rule coupling between §8/§10 outcomes and §11 authorization.
- **v1.1.0** (2026-05-17) — Added Wave-Sequencing Contract (7-step escalation
  protocol per SC-MISS-002) and Empirical Surface Probe Mandate (per
  SC-MISS-003). Both surfaced during v31.2 and v31.3 cycles where parse-only
  workarounds + documentation-derived assumptions produced surprise BLOCKED
  outcomes. v31.3 A-wave → B-wave HALT is the first regression-test PASS
  for the Wave-Sequencing Contract.
