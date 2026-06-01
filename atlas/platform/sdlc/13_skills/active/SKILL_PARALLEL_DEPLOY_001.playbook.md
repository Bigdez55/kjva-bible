# apex-parallel-deploy

<!-- Source: migrated from ~/.claude/skills/apex-parallel-deploy/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: apex-parallel-deploy -->

**Summary.** Parallel multi-agent deployment strategy for large-scale compiler or systems projects. Use this skill whenever the user wants to maximize coding agent throughput on a complex multi-phase project, coordinate parallel coding tracks with follow-behind auditors, or structure autonomous agent work with human-in-the-loop gates. Triggers on: "deploy agents", "parallel agents", "maximize output", "multiple coding agents", "run agents simultaneously", "cover more ground", "autonomous coding session", or any request to run large sections of a project without stopping. Also triggers when a user says "I'm walking away for a few hours" + "keep coding" or similar.

# APEX Parallel Deployment Skill

A battle-tested framework for deploying multiple coding agents in parallel on
large-scale projects. Validated across 14+ sessions on a compiler project
(SUPER C) producing 6,500+ SC LOC with 519/519 tests green.

---

## THE VALIDATED MODEL

The correct parallel deployment is **not** maximum fan-out. It is:

```
MAIN THREAD (critical path)
    + N BACKGROUND AGENTS (genuinely independent tasks only)
    + FOLLOW-BEHIND AUDITOR (per coding track)
```

### What "genuinely independent" means

A task is independent if it meets ALL three criteria:
1. **Different files** — zero overlap with main thread's active files
2. **No interface dependency** — does not need the main thread's output to start
3. **No governance risk** — does not require STOP-6 or lock-layer edits that need review

If a task fails any criterion: defer it, do not force it parallel.

### The failure mode (avoid this)

Speculative fan-out — assigning agents to tasks with hidden dependencies —
produces merge conflicts, red builds, and net negative progress. The session
history shows: 8-agent aspirational directives consistently underperform
2-agent focused directives.

---

## HOW TO DEPLOY

### Step 1: OBSERVE the project state

Before deploying any agents, collect actual baseline state:

```bash
make clean && make
bash tests/test_driver.sh     # get exact passing count
make loc                      # get exact LOC counts
git log --oneline -5 main     # get HEAD SHA
```

Quote actual results. Do not proceed from memory.

### Step 2: Identify the critical path

The critical path is the single sequence of dependent work that determines
minimum time to completion. Only the main thread runs on the critical path.

For a compiler project, the typical critical path is:
```
sema port → lowering port → codegen port → bootstrap attempt → closure
```

### Step 3: Identify genuinely independent tasks

Enumerate everything that is NOT on the critical path and check independence:

| Task | Different files? | No interface dep? | No STOP-6? | Deploy? |
|------|-----------------|-------------------|------------|---------|
| SHA-256 in SC | ✓ | ✓ | ✓ | YES |
| Test fixtures | ✓ | ✓ | ✓ | YES |
| Version string | ✓ partial | ✓ | ✓ | YES |
| Codegen port | ✓ | ✗ (needs lowering interface) | ✓ | DEFER |
| Schema edits | ✗ | ✗ | ✗ | STOP-6 first |

### Step 4: Deploy

One background agent per independent task. Each agent gets:
1. Explicit file scope (what files it owns)
2. Explicit non-goals (what files NOT to touch)
3. Green gate requirement (all existing tests must pass after each commit)
4. BOOTSTRAP-CRITICAL annotation requirement if the output feeds closure

### Step 5: Follow-behind auditor

Assign one auditor per coding track. The auditor:
- Reads each commit immediately after it lands
- Produces an audit file before the coding agent's next commit
- Checks: bootstrap-critical semantic match, convention compliance, interface correctness
- Flags CRITICAL issues immediately (coding agent fixes before proceeding)

---

## DIRECTIVE TEMPLATES

### Autonomous session directive (human walks away)

```
SCOPE: [project/] fully authorized. No scope warnings apply.

PRE-AUTHORIZED GATES: [list all gates that are pre-approved]

ABSOLUTE EXCEPTION — STOP-CRITICAL-2:
Gates may only be marked PASS when criteria actually hold.
Do not self-certify a gate the manifest records as not-yet-passing.

MAIN THREAD: [current critical path task]
  - Execute sub-slices in order: [list]
  - Compile incrementally. [N]/[N] tests green after every commit.
  - BOOTSTRAP-CRITICAL annotations on all closure-relevant functions.

BACKGROUND AGENTS (start simultaneously, all genuinely independent):
  Agent 1 — [agent-name]: [task]
    Files owned: [list]
    Files NOT to touch: [list]
    Deliverable: [specific output]

  Agent 2 — [agent-name]: [task]
    [same structure]

FOLLOW-BEHIND AUDITOR — [auditor-name]:
  After each main thread commit: produce audits/[track]/audit_[sha].md
  Cover: bootstrap-critical verification, convention compliance, interface correctness
  Flag CRITICAL findings before next sub-slice begins.

APEX LOCK — mandatory last commit of every session:
  Update APEX_PROJECT_REPORT.md sections: [list]
  Commit: "docs(apex): lock project report after session [N]
  [summary of all tracks]. HEAD: [SHA]."

STOP-CRITICAL CONDITIONS:
  STOP-CRITICAL-1: Build red + cannot fix in 3 attempts → wait for human
  STOP-CRITICAL-2: Gate claimed PASS when not passing → ABSOLUTE, no override
  STOP-CRITICAL-3: LOC exceeds [threshold] → wait for human
  STOP-CRITICAL-4: Repository corruption → stop immediately

Proceed. All tracks. No idle agents.
```

### Per-session standing directive

```
OODA DISCIPLINE: Observe (quote actual output) → Orient → Decide → Act.
Never proceed from memory. Quote make test output before writing code.

MAIN THREAD: [next sub-slice]
BACKGROUND: [list of independent tasks with agent assignments]
APEX LOCK: Last commit, every session, always.
```

---

## GATES AND STOPS

### Hard stops (only these pause execution)

| Stop | Condition | Response |
|------|-----------|----------|
| STOP-CRITICAL-1 | Build red, 3 attempts failed | Wait for human |
| STOP-CRITICAL-2 | Gate self-certified when criteria not met | ABSOLUTE — wait |
| STOP-CRITICAL-3 | LOC exceeds ceiling | Wait for human |
| STOP-CRITICAL-4 | Repository corruption | Stop immediately |

### Pre-authorized gates

When a human pre-authorizes gates, the agent still must verify criteria are met.
Pre-authorization means "you don't need to ask" not "you don't need to verify."
STOP-CRITICAL-2 overrides all pre-authorizations.

### STOP-6 protocol (lock layer edits)

Every canonical schema or governance edit requires:
1. Quote exact canonical names verbatim from source document
2. Verify name matches schema exactly before editing
3. Commit must touch exactly two files: schema + RMEC record
4. Verify: `git diff HEAD~1..HEAD -- "canonical/path/"` shows only those two files
5. If clean: commit and continue (pre-authorized)
6. If not clean: stop and surface before proceeding

---

## BOOTSTRAP CLOSURE PROTOCOL

For self-hosting compilers: the G5/G6 gates require byte-identical output.

### Verification sequence

```bash
# Step 1: Compile scc with seedc → scc1
./build/seedc scc/src/*.sc -o /tmp/scc1.o && cc -o /tmp/scc1 /tmp/scc1.o
SHA1=$(sha256sum /tmp/scc1 | cut -d' ' -f1)

# Step 2: Compile scc with scc1 → scc2
/tmp/scc1 build scc/ -o /tmp/scc2
SHA2=$(sha256sum /tmp/scc2 | cut -d' ' -f1)

# Step 3: Compare
[ "$SHA1" = "$SHA2" ] && echo "PASS: Bootstrap closure holds" || echo "FAIL: Divergence"
```

### BOOTSTRAP-CRITICAL annotations

Every function whose output feeds the bootstrap closure must carry:

```
// BOOTSTRAP-CRITICAL: [what semantic property must match]
// Reference: [source_file]:[line_start]-[line_end]
// Iteration order: [describe if order-sensitive]
// Verified: [evidence]
```

Missing annotations = audit finding = fix before next sub-slice.

---

## APEX PROJECT LOCK

Every session ends with an APEX project report update commit.

### What to update

- Current sub-slice progress per track
- LOC counts (all tracks, separately)
- Test suite totals
- Sessions remaining estimate (honest)
- New defects surfaced (S[N].D[N] format)
- New conventions added or retired

### Commit format

```
docs(apex): lock project report after session [N]

Track [name]: [sub-slice] complete. Track [name]: [sub-slice] complete.
scc/ at [X] LOC. [N]/[N] tests. Sessions remaining: ~[range].
HEAD: [SHA].
```

This creates a point-in-time snapshot readable by the human on return.

---

## CADENCE AND ESTIMATION

### Validated cadence (from 14 sessions)

- 1 sub-slice per session on critical path: reliable baseline
- 2 sub-slices per session: achievable when sub-slices are under 600 SC each
- Best session: 1,562 SC (main thread 1,063 SC + background 499 SC)

### LOC estimation corrections

Compiler features that touch multiple subsystems consistently run 1.5x estimate.
Apply a 1.5x multiplier to any estimate touching more than 2 files.

### Sessions remaining formula

```
sessions_remaining = (remaining_critical_path_LOC / avg_LOC_per_session)
                   + governance_sessions (STOP-6 events)
                   + closure_iterations (unknown until first attempt)
```

Update after every session. Quote the range, not a point estimate.

---

## WHAT THE PARALLEL MODEL ACHIEVES

Based on validated results across 18 sessions:

| Model | Critical path | Background | Total per session |
|-------|--------------|------------|-------------------|
| Single agent | ~700 SC | 0 | ~700 SC |
| Main + 1 background | ~1,063 SC | ~499 SC | ~1,562 SC (2.2x) |
| Main + 5 background | ~464 SC | ~1,369 lines | ~1,833 lines (2.6x) |
| Aspirational 8-agent (coupled) | Red builds, merge conflicts | — | Net negative |

**The inflection point (Session 18):** 5 background agents on genuinely independent
tasks produced the best session in project history AND unblocked Track Beta
(4,550 SC of future codegen work). The interface-analysis background task
(BETA_INTERFACE_SPEC.md) had ~13x ROI.

### The Beta Unblock Pattern

The highest-leverage background task is often the one that unblocks a future track.
Always assign one background agent to interface analysis when a future coding track
is waiting on interface stability. Reading + analysis work is cheap and the unblock
is worth more than any coding the agent could do instead.

---

## FOLLOW-BEHIND AUDIT FORMAT

```markdown
# Audit: [Track] [commit SHA]

## Bootstrap-Critical Verification
For each BOOTSTRAP-CRITICAL function:
- SC function: [name]
- Reference: [source_file]:[line range]
- Semantic match: VERIFIED / DIVERGENCE: [description]

## Convention Compliance
- C6 (struct-return out-param): PASS / VIOLATIONS: [list]
- C7 (slice-as-ptr): PASS / VIOLATIONS: [list]
- C8 (arena-idx): PASS / VIOLATIONS: [list]
- BOOTSTRAP-CRITICAL annotations: PRESENT / MISSING: [list]

## Interface Correctness
- Next sub-slice can call these cleanly: YES / ISSUES: [list]
- Missing helpers next slice will need: [list]

## Action Required
- CRITICAL (fix before next sub-slice): [list]
- RECOMMENDED: [list]
- INFORMATIONAL: [list]
```

---

## RECOMMENDED PRE-FLIGHT CHECKS (per session 23 lesson)

Before authoring new SC source, pre-flight identifier names against the
SCS-0 keyword table:

```bash
grep -E '"\w+"' compiler/seedc/src/lexer.c | grep TOK_
```

Reserved keywords used as struct field names or function names trigger
silent parse-error cascades that look like type errors (E0501/E0504)
but are tokenization issues. Session 23 lost a session to this when
field name `phase` collided with TOK_PHASE (a quantum-group keyword).

Common SCS-0 reserved names that are easy to use accidentally:
- `phase`, `gate`, `measure`, `qudit`, `qreg`, `realm`, `swap`, `fourier`
- `match`, `loop`, `where`, `move`, `mut`, `ref`, `Self`, `static`, `priv`
- All operator keywords: `as`, `in`, `is`, `not`

Identifiers that *contain* a keyword as a substring (e.g.
`digest_match`, `cur_phase`) are SAFE — the lexer matches whole-word
identifiers, not substrings.

---

## QUICK REFERENCE: AGENT ROLES

| Agent type | Owns | Does NOT touch |
|------------|------|----------------|
| Main thread | Critical path files | Other tracks' files |
| Background coding | Independent new files | Any file main thread is writing |
| Follow-behind | Audit files only | Any compiler source |
| STOP-6 governance | Schema + RMEC only | All other files |

---

## IMPROVEMENT LOOP

After each session, the APEX lock commit records actual vs estimated LOC.
Over sessions, this builds a calibration history:

```
Session 9:  plan 3,600 SC, actual 2,940 SC — 18% under
Session 10: plan 700 SC,   actual 632 SC   — 10% under
Session 11: plan 450 SC,   actual 403 SC   — 10% under
Session 12: plan 150 SC,   actual 317 SC   — 111% over (LowerCtx expanded scope)
Session 13: plan 700+200,  actual 1,062 SC — on track (multi-sub-slice session)
```

Use this history to recalibrate future estimates. The model improves
continuously as more data points accumulate.

See `references/session-history.md` for the complete calibration record.
