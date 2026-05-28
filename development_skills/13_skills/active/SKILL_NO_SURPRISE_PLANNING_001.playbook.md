# Playbook: SUPER C No-Surprise Planning

## Skill ID
SKILL_SC_NO_SURPRISE_PLANNING_001

## Version
1.0.0

---

## Purpose

Prevent coding agents from discovering major blockers after implementation starts.

This skill forces explicit feasibility forecasting, blocker enumeration, dependency
graphing, and claim-boundary declaration **before** a coding agent commits to a
milestone closure, classification claim (Silver, Gold, Platinum, True-LTS), or
multi-session work plan.

The skill exists because the SUPER C project has repeatedly seen execution orders
that ask for a closure level (e.g. Gold) when prior evidence already documents the
prerequisite blockers as unresolved. The result is wasted cycles, dishonest seals,
or, worse, gate weakening to manufacture a PASS. This playbook makes that pattern
visible at planning time, not discovery time.

---

## When to Use

Run this skill at the **front of any cycle** that has one or more of these
characteristics:

1. The cycle requests a sovereignty classification (Silver, Gold, Platinum, True-LTS,
   Stage N, freeze, retirement, archive, deletion).
2. The cycle proposes touching one of the canonical compiler authority surfaces:
   `compiler/scc/`, `compiler/seedc/`, `tools/sc*-tool*`, `tools/scld/`,
   `tools/canon-export/`, `tools/sco-pack/`, `superc-mcp/`, or any active
   `scripts/gates/*.sh`.
3. The cycle proposes Tier 3+ rewrites (GEN.OS, Storbits, IPOS, GUI, cloud, pkg-mgr).
4. The cycle would land more than ~6 evidence packets or more than one parallel work
   stream (A/B/C).
5. A prior red-team report, scorecard, or final report has been written for the same
   or an adjacent milestone within the last 90 days.
6. The execution order names a "G-number" goal (G4-G20 LTS goals) without naming the
   prerequisites that must close first.
7. The cycle would unblock a previously DEFERRED defect (DEF-*) or close an open
   DELTA (DELTA-001 through DELTA-007).

**Skip this skill for:** pure documentation patches, single-file typo fixes, single
gate-script noise reduction, or cycles that explicitly carry a `BLOCKED` verdict in
the order itself.

---

## Required Inputs

| Input                          | Source                                                                      | Required |
|--------------------------------|-----------------------------------------------------------------------------|----------|
| current tag                    | `git describe --tags --abbrev=0`                                            | yes      |
| current HEAD                   | `git rev-parse HEAD`                                                        | yes      |
| gate status                    | `bash scripts/gates/near_term_success.sh` RC + tail line                    | yes      |
| known blocker reports          | `superc-v1/docs/reports/v*_*.md`, `docs/lts_gap_register.md`                | yes      |
| active dependency inventory    | A1-class report (e.g. `v31_active_dependency_inventory.md`)                 | yes      |
| gate definitions               | `scripts/gates/*.sh` source for every gate the cycle touches                | yes      |
| scorecard                      | most recent `*_sovereignty_scorecard.md`                                    | yes      |
| prior red-team reports         | most recent `v*_red_team_review.md`                                         | yes      |
| prior final reports            | most recent `v*_final_report.md`                                            | yes      |
| user directive                 | the execution order text the cycle is responding to                         | yes      |

All inputs must be cited by **file path + line range or section ID** in the
feasibility forecast. Forecasts that quote without citation are rejected.

---

## Required Outputs

The skill produces **eight** artifacts. Each must land before any code edit.

| # | Artifact               | Form                                  | Purpose                                                                  |
|---|------------------------|---------------------------------------|--------------------------------------------------------------------------|
| 1 | feasibility forecast   | markdown <= 1500 words                | Per-requirement verdict with one of the 8 feasibility classes (see §1).  |
| 2 | blocker map            | markdown table                        | Every blocker the cycle would have to clear, with file:line citation.    |
| 3 | dependency graph       | mermaid graph LR                      | Edges between blockers and the goal claim.                               |
| 4 | closure path           | markdown enumerated sequence          | Streams A/B/C-style decomposition with concrete milestones.              |
| 5 | claim boundary         | markdown <= 400 words                 | What this cycle WILL ship vs what it will NOT ship.                      |
| 6 | gate design            | markdown table or pseudo-shell        | Every gate the cycle would add or alter, with PASS criteria.             |
| 7 | red-team precheck      | markdown answering §9 below           | The mandatory anti-overclaim question, answered honestly.                |
| 8 | final authorization    | one of three verdict strings (§11)    | The single binary signal the rest of the cycle reads.                    |

All eight live under `docs/reports/v<N>_<M>_evidence/W0-*` or equivalent
cycle-evidence directory. The naming convention is `W0-` because they precede every
W1+ work item.

---

## §1 — Feasibility Classes (8 enum)

Every prerequisite, predicate, or sub-goal in the cycle must be tagged with exactly
one of these classes. The vocabulary is grounded in v30-v31 SUPER C evidence and
must not be paraphrased.

| # | Class                                | Meaning                                                                                                                            | Example                                                                                  |
|---|--------------------------------------|------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------|
| 1 | `VIABLE`                             | Prerequisite is met today; the predicate would pass on first invocation.                                                           | `near_term_success.sh` RC=0 on warm-binary.                                              |
| 2 | `VIABLE_WITH_LANDED_WORK`            | Prerequisite is met after a specific, scoped, single-session work item that lives inside the cycle's scope.                        | "Add 3 lines to `scc_entry.c:8341` to surface parse-floor exit code."                    |
| 3 | `SCAFFOLDED`                         | Implementation exists structurally but returns 0/STUB/parse-floor; predicate would pass a name check and fail a behavior check.    | `scc check` parse-floor only at `scc_entry.c:8341-8347`.                                 |
| 4 | `BLOCKED_BY_MISSING_PREREQUISITE`    | A prior cycle's work item is not yet done; closure requires that prior work to land first.                                         | `sco-validate.sc` blocked by `std::crypto::hash_one_shot` STUB.                          |
| 5 | `BLOCKED_BY_STRUCTURAL_DEPENDENCY`   | An architectural fact (Makefile, build pipeline, opcode allocation) forecloses the predicate until rewritten.                      | `compiler/scc/Makefile:142-204` invokes `$(SEEDC)` for every `.sc` object.               |
| 6 | `DOCTRINAL_ONLY`                     | Policy says the predicate holds but evidence shows the structural reality is the opposite.                                         | `BOOTSTRAP_ARCHIVE_POLICY §3` doctrinally archives seedc while Makefile still calls it.  |
| 7 | `EXPECTED_TRIGGERED`                 | A stop-rule will fire by design; the cycle's honest verdict is `BLOCKED` and that is the intended outcome.                         | W1-G stop conditions #3, #4, #5, #7, #18, #19 in v31.1.                                  |
| 8 | `DEFERRED`                           | The predicate is open work tracked under a `DEF-*` ID or G-number with an explicit later target version.                           | `DEF-v22-NATIVE-SC-SCLD-PORT-001` (P2 post-v23.0).                                       |

**Class assignment rules:**

- A predicate may not carry two classes. Pick the most specific that applies.
- `SCAFFOLDED` always outranks `VIABLE`. If the surface is name-present but
  behavior-absent, it is SCAFFOLDED, not VIABLE.
- `BLOCKED_BY_STRUCTURAL_DEPENDENCY` always outranks `DOCTRINAL_ONLY` when both
  apply. The Makefile is the truth; the policy is the aspiration.
- `EXPECTED_TRIGGERED` is **not a failure mode** of the skill — it is the skill
  working. A cycle that lands with `EXPECTED_TRIGGERED` predicates and a `BLOCKED`
  verdict is an honest seal.

---

## §2 — Required Forecast Statement Template

Every feasibility forecast must open with this exact preamble (substitute the
parenthetical values from the cycle's inputs):

```
# Feasibility Forecast — <CYCLE_ID>

| Field | Value |
|---|---|
| Cycle ID                   | <e.g. v32.0> |
| Asked-for classification   | <Silver | Gold | Platinum | True-LTS | none> |
| Current tag                | <git describe --tags --abbrev=0> |
| Current HEAD               | <git rev-parse HEAD> |
| near_term_success.sh RC    | <0 | nonzero with stderr excerpt> |
| Prior scorecard            | <path:section + score, e.g. v31_sovereignty_scorecard §1 — 32/90 SILVER> |
| Prior red-team verdict     | <APPROVED | APPROVED_WITH_CAVEAT | BLOCKED | FAILED + path:section> |
| Date                       | <ISO-8601> |

## Forecast statement

This cycle is forecast to land at classification **<X>** with verdict
**<PASS | PASS_WITH_CAVEAT | BLOCKED>**. The forecast is grounded in the eight
feasibility classes enumerated in `SKILL_SC_NO_SURPRISE_PLANNING_001 §1`. Below,
every requirement of the asked-for classification is tagged with exactly one class,
with file:line evidence.

## Per-requirement table

| # | Requirement | Source | Class | Evidence (file:line or §) | Closure path |
|---|---|---|---|---|---|
| 1 | <req text> | <ORDER §N> | <CLASS> | <path:line> | <stream A/B/C or N/A> |
| 2 | ... | ... | ... | ... | ... |

## Class counts

- VIABLE: <n>
- VIABLE_WITH_LANDED_WORK: <n>
- SCAFFOLDED: <n>
- BLOCKED_BY_MISSING_PREREQUISITE: <n>
- BLOCKED_BY_STRUCTURAL_DEPENDENCY: <n>
- DOCTRINAL_ONLY: <n>
- EXPECTED_TRIGGERED: <n>
- DEFERRED: <n>

## Forecast verdict

<PASS | PASS_WITH_CAVEAT | BLOCKED> — <one-paragraph reasoning citing the dominant
class>.

## Honest claim boundary for this cycle

This cycle WILL ship: <bulleted list>
This cycle WILL NOT ship: <bulleted list>
```

The forecast is rejected if any per-requirement row is missing the `Class` or
`Evidence` column, or if `Class counts` does not sum to the number of rows.

---

## §3 — Hard Stop Rules (10)

These are the conditions under which the skill **must** halt the cycle before any
code edit. Each rule is single-line and binary. If any rule fires `YES`, the cycle's
final authorization defaults to `BLOCKED` and no Tier 3+ work may proceed.

| # | Hard Stop Rule | Rationale |
|---|---|---|
|  1 | `near_term_success.sh` returns nonzero RC at the start of the cycle. | A red gate at intake means baseline is broken; no closure claim can be honest until it returns 0. |
|  2 | Asked-for classification has >= 1 requirement classed `BLOCKED_BY_STRUCTURAL_DEPENDENCY`. | Structural blockers cannot be discharged inside the cycle; closure is impossible until the prior structural work lands. |
|  3 | Asked-for classification has >= 1 requirement classed `BLOCKED_BY_MISSING_PREREQUISITE` whose prerequisite is not in this cycle's scope. | A cycle cannot claim closure on work it has not authored. |
|  4 | Asked-for classification has >= 1 requirement classed `SCAFFOLDED` AND the order treats `SCAFFOLDED` as `VIABLE`. | Scaffold counted as implementation is the canonical overclaim failure. |
|  5 | A predicate is classed `DOCTRINAL_ONLY` AND the order claims structural completion. | Policy is not implementation. |
|  6 | Cycle plan exceeds one session of agent work AND order describes the work as "single shot" / "this cycle". | Multi-session work mis-scoped as single-session leads to mid-cycle abandonment. |
|  7 | Closure path would require weakening, deleting, or `exit 0`-ing any existing gate. | Gate weakening is forbidden (per `feedback_done_is_all_sc` + `project_v31_comprehensive_seal`). |
|  8 | Order references a tag, scorecard, or red-team report that has not been read by the agent in this session. | Orientation is mandatory; surprise blockers usually live in unread prior evidence. |
|  9 | Cycle would touch Tier 3+ (GEN.OS, Storbits, IPOS, GUI, cloud, pkg-mgr) without an explicit Tier 3+ authorization line in the user directive. | Tier 4 freeze is the default; widening must be explicit. |
| 10 | A previously SEALED tag would be moved, force-pushed, or rewritten. | Tag immutability is the spine of the audit chain. |

**Rule application protocol:**

1. Evaluate all 10 rules before the feasibility forecast is finalized.
2. Record each rule's result (`YES` / `NO` / `N/A`) in the red-team precheck artifact.
3. For every `YES`, write a one-sentence reason citing the order line and the
   contradicting evidence.
4. If any rule is `YES`, set the final authorization to `BLOCKED` with the
   `EXPECTED_TRIGGERED` clause from §V19 alternate-outcome path (see W1-G precheck
   convention).

---

## §4 — Anti-Overclaim Rules

These rules govern how the feasibility forecast translates into the cycle's
written claims. They are not stop rules — they are the wording discipline that
prevents the v31-Gold-surprise class of error.

1. **Class-faithful wording.** Every claim sentence in any cycle artifact must
   match the dominant feasibility class of the predicate it covers. A predicate
   classed `SCAFFOLDED` may not be described as "implemented", "lands", "closes",
   or "completes" — only as "scaffolded", "parse-floor", "name-present", or
   "structural-only".
2. **Tag-claim discipline.** No new tag may be cut whose name includes the
   classification level (e.g. `*-gold`, `*-platinum`, `*-lts`) if any §1
   classification requirement is classed worse than `VIABLE_WITH_LANDED_WORK`.
3. **Score-not-verdict separation.** A scorecard row is a number, not a verdict.
   A score of 1/3 on a row means the row is `SCAFFOLDED` or worse — never
   `VIABLE`.
4. **"Closed" requires byte-changing evidence.** A closure claim must cite a
   diff, an objfile, an opcode allocation, an inventoried LOC delta, or an
   executed gate transcript — not a memory entry, not a policy file, not a
   memo. (See `project_v21_4_1_sealed` "5/5 optimizer REAL — produces real
   byte changes" pattern.)
5. **Pilot work is named, not assumed.** A Tier 1 pilot must be (a) named in
   the order, (b) approved by the user, and (c) carry the `Tier-1 Pilot:` line
   in its W1-A artifact. Pilots are never "implied" by the cycle.
6. **Cite once, repeat never.** A blocker cited in the blocker map must not
   be re-narrated in the closure-path section; cross-reference it by file:line.
   This forces the agent to read its own evidence once, not write the same
   blocker twice with subtly different phrasings.
7. **Honest verdict never weakens.** If feasibility forecast says `BLOCKED`,
   the final authorization may not be `PASS_WITH_CAVEAT`. Verdict only ever
   weakens later (from `PASS` to `PASS_WITH_CAVEAT` to `BLOCKED`) when new
   evidence surfaces — never strengthens via re-classification.

---

## §5 — Gate Design Discipline

Every gate the cycle authors or modifies must satisfy:

1. **PASS criteria are file:line predicates.** A gate script must `grep -n` or
   `wc -l` or `git rev-parse` actual repo content; predicates like "is sufficient"
   or "approximately complete" are rejected.
2. **`exit 0` is reserved for actual PASS.** Gates that report "FAIL by design"
   must `exit 1` (not `exit 0` with a stderr note), unless the explicit purpose
   is to surface a class-tagged signal — in which case the gate must carry a
   comment-block header naming the class.
3. **Every gate carries a one-line `# Class:` header.** Allowed values:
   `WARM-BINARY`, `BUILD`, `SCAFFOLD-SURFACE`, `STRUCTURAL`, `RED-TEAM-DRIVER`.
4. **Gate enhancement is reviewed as a closure-path artifact.** Any change to
   `near_term_success.sh`, `superc_active_path_silver.sh`, or
   `superc_active_path_gold.sh` must land with a W1-C-class evidence packet.
5. **Hot-path gates have a flake-mitigation note.** If a gate has historically
   shown a flake (e.g. `seedc: cannot open 'build/main.o' for write`
   write-contention), the cycle's gate design must reference the prior W1-G
   sub-finding and either fix the flake or carry an isolation rerun
   instruction.

---

## §6 — Closure Path Decomposition Discipline

The closure path artifact must:

1. Name three or fewer named streams (Stream A, Stream B, Stream C). More than
   three streams means the cycle is mis-scoped — split.
2. For each stream, name the **concrete prerequisite** that, when landed,
   transitions one or more `BLOCKED_*` predicates to `VIABLE`.
3. For each stream, give a target version (e.g. v32.0, v22.0.C2, v1.1.0). A
   stream without a target version is forbidden — it indicates the agent
   forecasts closure but has no commitment to land it.
4. For each stream, name the **owning artifact** (a `DEF-*`, a `G-N` LTS goal,
   or an A-series evidence packet ID). Streams without owning artifacts drift.
5. Cross-link to memory entries (e.g. `project_v22_0_a4c_canonical_elf`) when
   the stream extends prior sealed work.

---

## §7 — Claim Boundary Artifact

The claim boundary is the cycle's contract with the user. It is one page, two
lists:

```
## Claim boundary — <CYCLE_ID>

### This cycle WILL ship
- <one bullet per artifact, naming the file path>
- ...

### This cycle WILL NOT ship
- <one bullet per claim the order might be read as requesting but which falls
  outside the cycle's actual capacity, with the feasibility class that explains
  why>
- ...

### Asked-vs-shipped delta
The order asks for: <one-sentence summary>.
This cycle ships: <one-sentence summary>.
Delta: <one paragraph naming the gap and the closure-path stream that owns it>.
```

The claim boundary is the single artifact the user reads first at seal time. It
must never lie. If asked-vs-shipped delta is empty, say so explicitly ("The
cycle ships exactly what was asked.").

---

## §8 — Red-Team Precheck Required Format

The red-team precheck answers the §9 required question and runs the §3 hard
stop rule grid. Format:

```
## Red-Team Precheck — <CYCLE_ID>

### Required question
**Q:** <verbatim from §9 below>
**A:** <honest answer; if YES to any sub-clause, the cycle is blocked or scoped down>

### Hard stop rule grid
| # | Rule | Result | Reason (file:line) |
|---|---|---|---|
| 1 | near_term_success RC=0 | <YES/NO> | <citation> |
| ... | ... | ... | ... |
| 10 | tag immutability | <YES/NO> | <citation> |

### Honest-verdict guard
If any rule above is YES, final_authorization is set to BLOCKED.
```

---

## §9 — Required Red-Team Question

Every cycle's red-team precheck **must** include and answer this exact question
verbatim:

> **Is the cycle being asked to claim closure on a sovereignty surface
> (compilation authority, gate authority, canon authority, archive authority,
> rewrite authority) whose prior-evidence-documented blockers have not landed
> a discharging artifact (byte-changing diff, opcode allocation, replaced
> Makefile rule, ported `.sc` source, or executed gate transcript) inside
> this cycle's scope?**

If the answer is **YES**, the cycle's final authorization defaults to
`BLOCKED`, the asked-for classification is downgraded by one level (Gold ->
Silver, Platinum -> Gold, True-LTS -> Floor-LTS), and the closure-path artifact
must name the stream(s) that would discharge the blockers in a later cycle.

If the answer is **NO**, the precheck records the file:line evidence for each
asked-for requirement showing a discharging artifact is in-scope.

The question is required because **the v31 Gold surprise was a YES that went
unasked** — see §10 below.

---

## §10 — Failure Mode This Skill Prevents

> **This skill specifically prevents the v31 Gold surprise: Gold closure was
> requested even though seedc structural dependency and incomplete scc command
> surface were already known blockers from v31 A2/A3/A7 evidence.**

Context. The v31 cycle was asked to land Gold classification. Prior v31 evidence
packets had already documented:

- **A1** (`v31_active_dependency_inventory.md`): 44,372 LOC of active C blocker
  in `compiler/seedc/` + `scc_entry.c` + scc-tools satellites.
- **A2** (`v30_7_evidence/A2_scc_command_surface.md`): `scc emit` forks to
  `$(SEEDC)` at `scc_entry.c:8198`; `scc check` is parse-floor SCAFFOLDED at
  `scc_entry.c:8341-8347`; G15 self-host bootstrap retimed to v1.1.0
  (2027-02-15).
- **A3** scc command surface: 4 MISSING subcommands; 5 EXT Mach-O satellites;
  `canon_export.py` (262 LOC Python) still the active canon producer.
- **A7** (`v31_active_path_gold_gate_report.md`): verdict `GOLD_BLOCKED`,
  0 PASS / 8 FAIL / 1 PENDING.

The Gold ask landed anyway. The cycle had to discover at W1 time that 8 of 9
Gold requirements were structurally `BLOCKED`, that the closure path was three
multi-quarter streams (A2/A3/A4), and that no honest Gold seal was reachable
inside the cycle. The honest outcome — `PASS_WITH_CAVEAT` at Silver, with Gold
explicitly `BLOCKED_BY_STRUCTURAL_DEPENDENCY` — was the §V19 alternate path,
documented in `W1-G_stop_rule_precheck.md`.

**Where this skill would have changed the outcome.** Had the cycle run this
skill at intake:

1. The feasibility forecast (§2) would have tagged Gold requirements #1, #2,
   #3, #4, #5, #6, #7, #8 as `BLOCKED_BY_STRUCTURAL_DEPENDENCY` or
   `SCAFFOLDED`, citing the A1/A2/A3/A7 file:line evidence above.
2. Hard Stop Rules #2, #3, #4 (§3) would have fired YES at intake.
3. The required red-team question (§9) would have been answered YES.
4. Final authorization (§11) would have defaulted to `BLOCKED` with the
   ask downgraded to Silver before any W1 work began.
5. The cycle would have shipped its honest Silver seal as its **primary**
   deliverable, not as a §V19 alternate-path discovery.

This is the failure mode the skill exists to prevent. It is the canonical
SUPER C planning failure: **prior evidence documents the blocker; the order
ignores the prior evidence; the cycle discovers the blocker mid-flight.**

---

## §11 — Final Authorization Verdict Strings

The cycle's `final_authorization` artifact emits exactly one of three strings:

- **`PROCEED_AS_REQUESTED`** — all §3 hard stop rules are NO; all §1 classes
  are `VIABLE` or `VIABLE_WITH_LANDED_WORK`; the §9 question answers NO with
  cited discharging artifacts.
- **`PROCEED_WITH_DOWNGRADED_CLASSIFICATION`** — one or more §3 rules are
  YES, but a clean honest seal is reachable at a lower classification level;
  the cycle's claim boundary (§7) reflects the downgrade.
- **`BLOCKED_DO_NOT_PROCEED`** — multiple §3 rules are YES, structural
  blockers dominate, and no honest seal is reachable inside the cycle's
  scope. The cycle should output only the W0 evidence packet and stop.

The verdict is consumed by the rest of the agent stack as a binary
go/no-go/scope-down signal. It is not advisory.

---

## Output Locations

```
docs/reports/v<N>_<M>_evidence/W0-A_feasibility_forecast.md
docs/reports/v<N>_<M>_evidence/W0-B_blocker_map.md
docs/reports/v<N>_<M>_evidence/W0-C_dependency_graph.md
docs/reports/v<N>_<M>_evidence/W0-D_closure_path.md
docs/reports/v<N>_<M>_evidence/W0-E_claim_boundary.md
docs/reports/v<N>_<M>_evidence/W0-F_gate_design.md
docs/reports/v<N>_<M>_evidence/W0-G_red_team_precheck.md
docs/reports/v<N>_<M>_evidence/W0-H_final_authorization.md
```

The `W0-` prefix marks these as preceding all W1+ work items.

---

## Validation

See `08_verification/skill_tests/TEST_SKILL_SC_NO_SURPRISE_PLANNING_001_001.yaml`.

The test asserts:

- All 8 outputs are present under the cycle's evidence directory.
- The feasibility forecast contains the §2 preamble verbatim.
- Every per-requirement row has a class drawn from the §1 enum.
- The red-team precheck contains the §9 question verbatim.
- The final authorization is one of the three §11 strings exactly.
- If any §3 hard stop rule is YES, `final_authorization` is not
  `PROCEED_AS_REQUESTED`.
- The §10 failure-mode citation appears verbatim in the playbook reference of
  any cycle that closes with `BLOCKED_DO_NOT_PROCEED`.

---

## Originating Miss

SC-MISS-001 (v31 Gold Closure Surprise) — see
`development_skills/_miss_log/SUPER_C_MISS_LOG.md:3`.

Extended by SC-MISS-002 (Wave-Sequencing) and SC-MISS-003 (Empirical Surface Probe).

---

## Stage IV-I XKABI/XISC Dependency Taxonomy (per SC-MISS-003)

Any feature whose closure depends on the following has a multi-cycle prerequisite and CANNOT close in a single bounded slice. Surface this in §1.2 KNOWN BLOCKERS:

### XISC Opcode Stage IV-I dependencies (BLOCKED until XISC HASH_ONE_SHOT / SYS_WRITE / XKABI_PROC_EXIT etc. land)
- `std/std/io.sc::io_read`, `io_write`, `io_flush`, `io_close` (XISC SYS_READ/SYS_WRITE/SYS_FSYNC)
- `std/std/env.sc::env_args`, `env_arg_count`, `env_arg_at`, `env_cwd` (XKABI argv table / GETCWD)
- `std/std/process.sc::process_id`, `process_exit`, `process_abort` (XKABI TLS / XKABI_PROC_EXIT / XKABI_PROC_ABORT)
- `std/std/crypto.sc::hash_one_shot` (XISC HASH_ONE_SHOT for canonical impl; v31.2 inline workaround is parse-only)

### Intrinsic Codegen Stage IV (BLOCKED per v31.3 I4 — 0/6 SC user intrinsics have codegen)
- `__syscall__` — XKABI syscall dispatch (no codegen as of 2026-05-17)
- `__load_u8__` / `__load_u32__` / `__load_u64__` — byte/word loads (parse-only)
- `__store_u8__` — byte stores (parse-only; v31.3 A6 probe empirically proved const-fold-only execution)
- `__strdata__` — string data (parse-only)
- `__store_u32__`, `__store_u64__`, `__align__`, `__panic__` — not yet referenced anywhere

### Run-jit Import Resolver Stage IV (BLOCKED per v31.3 A2 + I2)
- `std::std::*` imports rejected by `apply_bounded_imports` at scc_entry.c:6144
- Only `std::core::*` permitted; any std::std::-rooted test cannot run via run-jit

### Run-jit Codegen Bridge Stage IV (BLOCKED per v31.3 I5)
- Non-trivial programs (loops, intrinsics, memory ops) fall back to const-fold path
- 8/8 sampled demos resolve `path=fold` — "57/57 passing" is const-fold theater, not JIT execution
- match-pattern programs HANG run-jit (60_match_int.sc → ~13min CPU before kill)

**Required §1.2 disclosure:** any forecast that includes one of these dependencies MUST cite the Stage IV-I prerequisite explicitly. Failure = SC-MISS-001 recurrence pattern.

---

## Improvement History

- v1.0.0 — Initial skill from SC-MISS-001 v31 Gold closure surprise.
- v1.1.0 (2026-05-17) — Added Stage IV-I XKABI/XISC Dependency Taxonomy per SC-MISS-003 v31.3 I-wave audit. The taxonomy was implicit in std/std stub bodies' "// STUB: real impl emits XISC ... in Stage IV-I" comments but had not been promoted to a forecast-time blocker. v31.2 + v31.3 both attempted feature closure without explicit Stage IV-I prerequisite acknowledgment; this section makes that acknowledgment mandatory.
