# sc-empirical-surface-probe

<!-- Source: migrated from ~/.claude/skills/sc-empirical-surface-probe/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: sc-empirical-surface-probe -->

**Summary.** Empirical Surface Probe Mandate for SUPER C compiler work (`superc-v1/`). Invoke BEFORE designing any compiler patch, BEFORE asserting any claim about compiler behavior, and BEFORE executing any handoff-driven plan. The mandate forces a minimal-fixture reproduction of every blocker against the live compiler before source modification — closing the gap that previously allowed handoff-stated bugs, mental-math instruction encodings, and stale file:line references to survive into committed patches. Triggers on the SC-MISS-003 anchor and on any SC compiler edit under `compiler/scc/`, `frontend/`, or codegen/SCIR/SHIRL paths. Anchored by 16+ regression-PASS cycles across the v31.4 / v31.5 series.

# SC Empirical Surface Probe Mandate — Operational Skill (v1.1)

**DIRECTIVE: Reproduce empirically. Decode opcodes. Disconfirm handoffs.
Preserve probe output. Never patch what you have not first observed.**

This skill is the empirical counterpart to `one-shot-execution-planning`
and `compiler-discipline`. Those skills govern *plan quality* and
*classification discipline*. This one governs the **act of seeing** —
the experimental work that must happen before any plan is trustworthy.

The skill is anchored as **SC-MISS-003** in the SUPER C project memory.
Every cycle in the v31.4 / v31.5 series that closed cleanly did so
because the agent ran the probes below BEFORE editing source. Every
revert in that same series happened because someone trusted a handoff
claim, a mental-math constant, or an unverified stale file:line
reference.

---

## When to invoke

Invoke this skill BEFORE:

- Designing ANY SUPER C compiler patch (frontend, sema, lower, codegen,
  linker, runtime).
- Making ANY claim about compiler behavior (especially claims sourced
  from a handoff report, an audit, or prior session memory).
- Executing ANY handoff-driven plan — even one with a "complete" or
  "ready-for-impl" stamp from a prior agent.
- Replying to a user request that contains "the bug is at file X line Y"
  unless you have personally reproduced that bug against the live tree.

Skip ONLY when:
- The task is pure documentation under `docs/` that touches no source.
- The user has explicitly authorized a paper exercise with no compiler
  modification.

---

## Mandatory Probes for SC Compiler Work

### A. Baseline (run from EXACT documented PWD)

Two baseline gates MUST be re-established green before any compiler
edit. PWD matters — wrong PWD silently produces false regressions.

1. **scc smoke baseline:**
   ```sh
   cd superc-v1/compiler/scc && bash tests/scc_smoke.sh
   ```
   Expected: `127 passed, 0 failed` (target floor; current empirical
   floor varies per cycle — record the current PASS/FAIL count in the
   probe report).

2. **gold gate baseline:**
   ```sh
   cd superc-v1 && bash scripts/gates/gold_gate.sh
   ```
   Expected: `21 passed, 0 failed`.

3. **Fail-fast rule.** If either gate is red on a clean tree, **STOP**
   immediately and surface to the user before any other work. A red
   baseline contaminates every subsequent measurement.

### B. Targeted reproduction (per blocker)

For every blocker named in a handoff, you author your own minimal
fixture and reproduce against the live compiler:

1. **Author MINIMAL fixture** in `/tmp/<blocker_probe>.sc`. Strip the
   reproducer to the smallest expression that triggers the failure.
   Multi-statement reproducers obscure the actual SCIR shape.

2. **Run with SCIR/SHIRL dump enabled and `-o` MANDATORY:**
   ```sh
   SCC_O1=1 SCC_O1_DUMP=1 compiler/scc/build/scc emit-direct \
     --target=macho-arm64 <fixture> -o /tmp/<probe>.out
   ```
   **`-o` is REQUIRED.** Without it, `scc` prints a usage hint and
   exits — you will get NO compile, NO dump, and no signal that the
   command failed silently.

3. **Read the SHIRL inst array.** Decode the opcode field for each
   instruction. Cross-reference against the opcode table in
   `compiler/scc/src/codegen_*.sc`. Refer to the
   `compiler-discipline` and `apex-verified-machine-encoding` skills
   for the canonical opcode-encoding rules — never hand-compute
   instruction words from memory.

4. **Compare to expected.** Your claim ("the bug is X", "the fix is Y")
   must reproduce empirically against the dump before you design the
   patch. If the dump does not match the handoff's stated behavior,
   the handoff is the bug (see Section E).

### C. Cross-PWD trap awareness

The SUPER C scripts assume specific working directories. Wrong PWD →
silent path errors → false 1/N regression signals.

- `tests/scc_smoke.sh` runs **from `superc-v1/compiler/scc/`**. Running
  it from `superc-v1/` produces a single false regression on test
  count — the script greps relative paths.
- `scripts/gates/*.sh` runs **from `superc-v1/`**. Running it from
  `compiler/scc/` produces `No such file or directory` on every gate.
- **Always document the PWD** in every probe report next to every
  command. A `cd <PWD> && <cmd>` chain is the canonical form.

### D. `timeout` is NOT available on macOS

macOS ships BSD coreutils; there is no GNU `timeout(1)`. Common bug:
copying a Linux script that uses `timeout 120 bash ...` — on macOS
you get `command not found` and the script exits 127 with no real
work done.

- **Canonical workaround:** the `perl-alarm` wrapper pattern used by
  `scripts/gates/lib/check_gate.sh` (see commit `da26298e` —
  v31.5.I.JIT-DEFENSIVE perl-alarm timeout wrappers).
- **Inline form:**
  ```sh
  perl -e 'alarm shift; exec @ARGV' 120 bash some_script.sh
  ```
- **Never** add a bare `timeout` to a SC gate script. If you must,
  guard it with a check for `gtimeout` (homebrew GNU coreutils) and
  fall back to `perl-alarm`.

### E. Empirical disconfirmation rule

When a handoff says **"Bug at file X line Y"**, your obligation is to
reproduce — not to fix.

- If the live tree shows no such bug at the cited line, do NOT begin
  remediation. Instead author a **Handoff Re-verification Report**
  documenting the gap between handoff claim and live state.
- Surface the report to the user before any source modification.
- This is the rule that converted v31.4.A1 (build-PASS / runtime-FAIL
  / safely-reverted) into v31.4.A1D (root-cause-fixed, foundations
  landed clean): the probe disconfirmed the original "all 5 encodings
  match ARM ARM" claim by exposing systematic mental-math errors of
  1024–208384 across all five instruction constants.

### F. Probe output preservation

Probes produce evidence. Evidence is the only durable currency in this
project — memory anchors decay, handoffs lie, but a captured dump and
its interpretation do not.

- **All probe output** goes into a named report. The current canonical
  path is `docs/reports/v31_5I_F1_root_cause_inventory.md` (or the
  equivalent cycle-specific named report — `v31_5_A_*`,
  `v31_4_A4D_*`, etc.).
- **Each probe block in the report MUST include:**
  - Exact command (with `cd <PWD>` prefix).
  - Exact RC.
  - Exact dump excerpt (paste the SHIRL inst array bytes, not a
    paraphrase).
  - Your interpretation, with a citation to the source file and line
    you cross-referenced.
- Probe reports are append-only. If an earlier probe is superseded,
  add a new section with a `Supersedes` marker — never silently
  rewrite history. (See `compiler-discipline` Section 6 for the
  honesty-queue convention.)

---

## Failure modes this skill prevents

Each failure mode below is anchored to an empirical regression in the
v31.x cycle history. The presence of a regression-PASS counter in
project memory (`SC-MISS-003 NN-th regression-PASS`) is the proof that
this skill works.

1. **Mental-math instruction encodings** — `v31.4.A1` shipped 5 ARM64
   constants computed by hand; all 5 were off by ≥1024. Fixed in
   `v31.4.A1D` after the printf probe forced empirical verification.

2. **Stale handoff file:line references** — `v31.4.A5` reported the
   bug at `lower_walker.sc:1306-1323`; the live probe showed Ident
   reference compared byte-span identity, which IS in that range, but
   the handoff misnamed the failure mode. Re-verification surfaced
   the real root cause (`v31.5.A` scc_entry.c Pass 4.7 back-link).

3. **Wrong-PWD false regression** — multiple v31.4 sessions logged
   "1/122 regression" when scc_smoke was run from `superc-v1/` instead
   of `compiler/scc/`. Documenting PWD in the probe report eliminates
   this.

4. **`timeout` missing on macOS** — `v31.5.I.G` and `v31.5.I.JIT` both
   needed perl-alarm wrappers after gate scripts silently 127'd.

5. **Build-PASS treated as runtime-PASS** — `v31.4.A1` and
   `v31.4.A4_REAL` both built clean but failed runtime. The probe
   protocol (Section B step 4) catches this by demanding execution
   against a fixture, not just successful build.

6. **Skipped `-o` on emit-direct** — at least 3 v31.4 cycles logged
   "scc produced no output" before discovering `-o` is mandatory for
   emit-direct mode; printing a usage hint is success in scc's RC
   model.

---

## §G State-Dependent Transient Behavior — FLAG, Don't Dismiss

### Mandatory rule
When a fixture briefly produces RC=X then reverts to RC=Y (or vice versa) without obvious source change, FLAG as `STATE_DEPENDENT` in the probe log. FORBIDDEN responses: "fluke", "flake", "rebuild artifact", "compiler cache".

### Required next steps
1. **Capture both RC outputs with build artifact SHA**. Record `git rev-parse HEAD` + `md5sum compiler/scc/build/scc` (or equivalent) at the moment of each observation.
2. **Bisect intervening builds**. If multiple `make` runs happened between observations, identify which build was active for each RC.
3. **Inspect ENV/file/cache state**. Page cache, JIT icache, register allocator entropy, /tmp file race, ulimit, system load.
4. **Re-attempt under controlled conditions**: clean tmpdir, no concurrent processes, single thread of execution.

### Forbidden
- Discarding the transient observation
- Asserting "must be timing" without measurement
- Re-running until the desired outcome and stopping

### Empirical anchor
v31.5.I.F1.a session — `case40_lex_min.sc` produced RC=0 ONCE during F1.a investigation, immediately post-rebuild. Subsequent 5/5 sequential runs all hung (RC=142 from perl-alarm). The session almost dismissed this as "fluke" until advisor() flagged it as state-dependent. Investigation revealed: when STACK_ALLOC size is correct AND struct fields happen to land at calloc-zero, the loop guard `l.pos < l.len` evaluates 0 < 0 → false → exits cleanly. The transient RC=0 was real and load-bearing — it proved F1.a's allocation correctness even before F1.b/c/0 closed the loop semantics.

### Project-agnostic frame
Any non-deterministic test outcome in a deterministic-by-design system is a DEFECT SIGNAL. Disconfirm by reproduction-attempt under varied conditions; never by dismissal. Often the transient reveals a hidden correctness property worth documenting.

### Recording template (append to probe report)
```text
STATE_DEPENDENT observation
  Fixture: <path>
  RC observed: [<rc1>, <rc2>, ...]
  Build SHA at each: [<sha1>, <sha2>, ...]
  Run order: [<command sequence>]
  Hypothesized cause: <hypothesis>
  Action: <continue probing | escalate | document and defer>
```

### Cross-references
- `gate-contention-isolation` — three-tier reproduction
- `one-shot-execution-planning` — §17 Pre-Flight Empirical Baseline
- `gate-harness-process-isolation` — when state comes from harness orphans

---

## Out-of-scope

This skill is for **SC compiler runtime/codegen empirical work**. It
does NOT govern:

- Pure plan documentation (use `one-shot-execution-planning`).
- Bootstrap-safety classification (use `compiler-discipline`).
- Machine-encoding oracle round-tripping (use
  `apex-verified-machine-encoding`).
- Wave/agent scheduling (use `apex-parallel-deploy`).
- GENOSCOPY scope enforcement (use `apex-directory-discipline`).

This skill assumes you have already invoked the relevant peer
discipline skills above. It supplies the *act of seeing* that those
skills demand as input.

---

## Authority and anchors

- Project memory anchor: **SC-MISS-003** (Empirical Surface Probe
  Mandate; first surfaced during v31.3 skill-sovereignty cycle).
- Regression-PASS counter: maintained in project memory entries
  `project_v31_4_*.md` and `project_v31_5_*.md`. 16+ regression-PASS
  cycles as of v31.5.I.F1.a (state-dependent transient anchor added
  in v1.1).
- Peer skills: `compiler-discipline`, `one-shot-execution-planning`,
  `apex-verified-machine-encoding`, `gate-contention-isolation`,
  `gate-harness-process-isolation`.
- Canonical probe-report exemplar:
  `docs/reports/v31_5I_F1_root_cause_inventory.md`.
- Canonical PWD-aware gate library:
  `scripts/gates/lib/check_gate.sh` (perl-alarm wrappers).

## §H — Silent-Success Smell in Error Paths (v1.2 anchor: F1.runtime episode)

Dump-only gates CANNOT see helper functions that return `1` ("handled")
on capacity-exhaust paths WITHOUT actually emitting the IR they were
supposed to emit. The caller proceeds as if the emit happened.

Canonical anchor: `lower_field_assign` at `lower_walker.sc:608-617`
returned `1` (handled) on `arenas.operands_len + 2 > arenas.operands_cap`
WITHOUT emitting STORE. Only a runtime RC probe surfaced the divergence.
Field-write tests passed at dump-level AND accidentally at runtime when
the final_ldr leak value happened to match expected.

**Mandatory grep on any emitter PR:**

```bash
grep -nE 'return 1.*pool|return 1.*exhaust|return 1.*cap|return 1.*emit_inst' compiler/scc/src/*.sc
```

Convert `return 1` (handled) to `return 0` (unhandled) so caller's
fallback emits diagnostic-visible failure. The new `gate-dump-vs-runtime`
v1.0.0 skill generalizes this rule project-agnostically.

Diversify runtime fixture expected values per probe (e.g., 2, 5, 42)
so final_ldr leaks become visible.

## Changelog

- **v1.2** (2026-05-26): Added §H "Silent-Success Smell in Error Paths"
  anchored to v31.5.I.F1.runtime episode. Dump-vs-runtime mandate +
  silent-success grep pattern are now project discipline. Cross-references
  new `gate-dump-vs-runtime` v1.0.0 skill.
- **v1.1** (2026-05-26): Added §G "State-Dependent Transient Behavior
  — FLAG, Don't Dismiss" anchored to v31.5.I.F1.a `case40_lex_min.sc`
  transient-RC=0 episode. Regression-PASS counter bumped 15+ → 16+.
- **v1.0**: Initial empirical surface probe mandate; sections A–F.
