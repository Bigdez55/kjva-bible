# Playbook: SKILL_SC_DEPENDENCY_SOVEREIGNTY_001 — SUPER C Dependency Sovereignty

## Skill ID
SKILL_SC_DEPENDENCY_SOVEREIGNTY_001

## Version
1.0.0

## Layer
governance

## Domains
sovereignty, compiler, dependency-management

---

## Purpose

Determine whether SUPER C is actually sovereign — meaning the language, its
compiler, its standard library, its build chain, and its developer-facing
tooling are all expressible and executable in SUPER C source — or whether
non-SUPER-C languages (C, Python, shell, Make, third-party binaries) still
sit in the active path and quietly block the sovereignty claim.

This skill produces an honest, evidence-backed sovereignty scorecard. It is
NOT a code change. It is a measurement and classification ritual that any
agent must perform before stamping a release as "sovereign," "self-hosted,"
"native," or "all-SC."

The skill exists because SUPER C repeatedly claimed sovereignty milestones
that were technically true at a narrow file-set scope (e.g., `scc` bootstraps
itself, the Stage-0 ELF is real bytes) while still depending on Python build
glue, C bridge shims, shell gate runners, or seedc artifacts in the active
build graph. Sovereignty claims that survive this skill's audit are
defensible; claims that fail it must be either re-scoped or remediated
before the seal is taken.

---

## When to Use

Run this skill BEFORE any of the following:

- Tagging a release with `sovereign`, `native`, `all-sc`, `self-hosted`,
  `bootstrap-closed`, `no-shims`, or `xkabi-only` in the version label or
  release notes.
- Closing a Tier 1 / Tier 2 / Tier 3 milestone whose acceptance criteria
  reference SUPER C completeness, dependency retirement, or substrate
  status (e.g., "GEN.OS substrate language ready," "Phase 7 complete").
- Sealing a STOP-block that claims to retire a non-SC component (seedc,
  scld.py, any `*.py` tool, any `*.c` bridge).
- Drafting an executive summary, board readout, or external-facing claim
  that uses the words "sovereign," "no dependencies," or "pure SC."
- After any change to the build chain, gate runner, CI workflow, or
  developer tooling under `superc-v1/scripts/`, `superc-v1/tools/`, or
  `superc-v1/.github/`.
- On the cadence defined by Tier 4 maintenance (at least every 30 days,
  or after any external contributor lands a tooling change).
- Whenever a prior session's release notes use the phrase "honestly
  disclosed" about a known non-SC component — that disclosure is a debt
  ledger entry, and this skill is the periodic audit of that ledger.

Run this skill OPTIONALLY for:

- Onboarding a new contributor who needs to know which files are real
  load-bearing SC code vs. which are scaffolding, fixtures, or
  external-host concessions.
- Drafting a deferred-defect entry (DEF-*) that references a non-SC
  component — the classifications in this skill are the canonical
  vocabulary.

Do NOT skip this skill on the grounds that "we already know the answer."
Memory drifts. Build chains accrete. The skill is cheap to run and the
failure mode it prevents is expensive to repair.

---

## Required Audit Categories

Every file flagged by the audit MUST be classified into exactly one of the
eleven categories below. The classification determines whether the file
counts against the sovereignty score, and how it must be remediated (if at
all) before the next sovereignty seal.

### 1. ACTIVE_BLOCKER

**Definition:** A non-SC file that is invoked by the current build, test,
or runtime path AND has no SC replacement in tree AND blocks a claimed
sovereignty milestone.

**Examples:**
- `scld.py` (777 LOC Python linker) invoked by every `.sco -> executable`
  step while the SC port `std/build/scld.sc` does not yet exist.
- A `.c` parser bridge called by the SC compiler driver with no SC-side
  fallback.

**Remediation:** Block the sovereignty seal. Open a P0 port slice. Either
implement the SC replacement before sealing or downgrade the seal scope.

**Counts against score:** YES (heaviest weight).

---

### 2. ACTIVE_DEPENDENCY

**Definition:** A non-SC file that is invoked by the current build or
runtime path but is acceptably scoped as "external host concession" (host
shell, host filesystem, host clock) OR is a sanctioned bootstrap rung
whose retirement is on a roadmap with a tracked deferred-defect ID.

**Examples:**
- `bash` invoked by `superc-v1/scripts/gates/near_term_success.sh`. Bash
  is the host shell; SC does not yet ship its own shell.
- A `clang` cross-compile invocation used to verify Stage-0 ELF
  reproducibility on aarch64. External toolchain used for verification,
  not for the SC build itself.

**Remediation:** Document in the deferred-defect ledger with an explicit
DEF-* ID and a target sovereignty floor. Allowed to remain in active path
until that floor.

**Counts against score:** YES (medium weight). PLATINUM cannot be reached
until this set is empty.

---

### 3. TRANSITIONAL_DEPENDENCY

**Definition:** A non-SC file that is being actively migrated — both the
non-SC original AND the SC replacement exist in tree, both are wired into
the build, and a deprecation date or trigger is recorded.

**Examples:**
- `seedc/scir_lower.c` paired with `std/build/scir_lower.sc` during the
  cutover window. Build prefers SC when `SC_SELFHOST=1`, falls back to C
  otherwise.

**Remediation:** Set a hard deprecation date in the release notes. Once
the trigger fires, the non-SC original moves to BOOTSTRAP_ARCHIVE.

**Counts against score:** YES (light weight). Acceptable for SILVER and
GOLD scoring; blocks PLATINUM.

---

### 4. ARCHIVE_ONLY

**Definition:** A non-SC file retained for historical reference, audit
trail, or reproducibility of a prior tag. Not invoked by any current
build, test, gate, runtime, or developer tooling path.

**Examples:**
- `seedc/parser.c` after the cutover trigger fires and `SC_SELFHOST=1`
  is the only supported build mode.
- A frozen Python prototype that informed the SC port and is retained
  for the SCIR design rationale.

**Remediation:** Move under `archive/` or `legacy/` with a README that
states the retirement tag. Add to `.gitattributes` as `linguist-vendored`
to keep it out of language-statistics dashboards.

**Counts against score:** NO.

---

### 5. BOOTSTRAP_ARCHIVE

**Definition:** A non-SC file that was the original bootstrap rung,
retired in favor of an SC self-host, but kept reproducible so that any
future audit can reconstruct the chain from a trusted-by-inspection
starting point.

**Examples:**
- The C `seedc` source tree after `scc` self-hosts. Required to exist for
  any "trusted ladder" verification but never executed in the regular
  build.
- An early shell driver replaced by `tools/superc_lsp.sc`.

**Remediation:** Pin to a Git tag. Document the reconstruction recipe in
`docs/bootstrap/`. Never modify after the retirement tag is set; if a
change is needed, open a new bootstrap chain.

**Counts against score:** NO. Required for trust-by-inspection sovereignty
audits, not a violation of sovereignty.

---

### 6. TEST_FIXTURE

**Definition:** A non-SC file present in the repo solely to serve as input
or expected-output for an SC test. The file's content is what is being
exercised; the file's language is irrelevant.

**Examples:**
- A `.json` golden file under `tests/golden/`.
- A `.c` source under `tests/interop/` used to verify SC's XKABI calling
  convention matches a known-good C-side implementation.

**Remediation:** Keep under `tests/`. Never invoke from production build
graph. Tag with `# fixture` comment header so audit grep can exclude.

**Counts against score:** NO.

---

### 7. NEGATIVE_FIXTURE

**Definition:** A non-SC file present specifically to assert that SC
rejects, ignores, or correctly diagnoses it. The file exists to prove a
boundary, not to be processed successfully.

**Examples:**
- A malformed `.sc` source under `tests/diagnostics/` that the parser
  must reject with diagnostic code E_PARSE_FAIL_42.
- A non-SC file extension (`.py`, `.rs`) dropped into a build-input
  directory to assert the build refuses non-SC inputs.

**Remediation:** Document the assertion it proves. Keep adjacent to the
test that consumes it.

**Counts against score:** NO.

---

### 8. GENERATED_OUTPUT

**Definition:** A non-SC file produced by an SC tool or build step. The
file's existence does not represent a sovereignty violation; the
generator does.

**Examples:**
- `*.sco` object files emitted by `scc`.
- `*.elf` Stage-0 executables emitted by the SC linker.
- `*.wat` WebAssembly text dumps emitted by `--target wasm`.
- A `compile_commands.json` synthesized by an SC-side build helper.

**Remediation:** Listed in `.gitignore` unless they are a checked-in
artifact (e.g., reproducibility baselines). The generator's language is
what is audited, not the output.

**Counts against score:** NO. Audit the generator instead.

---

### 9. EXTERNAL_HOST_REALITY

**Definition:** A file or invocation that exists outside SC's scope of
authority because it belongs to the host platform that SC has explicitly
chosen NOT to replace.

**Examples:**
- macOS `Mach-O` headers consulted when running on Darwin.
- A Linux `/proc/cpuinfo` read for runtime CPU dispatch.
- A POSIX `fork()` call routed through XKABI to the host kernel.

**Remediation:** Document the host-reality boundary in
`docs/sovereignty/HOST_BOUNDARY.md`. Reaffirm during each sovereignty
review that the boundary has not silently expanded.

**Counts against score:** NO, provided the boundary is documented and
unchanged since the prior audit.

---

### 10. FALSE_POSITIVE

**Definition:** A file flagged by the audit grep but on inspection found
to be SC-equivalent (e.g., an `.sc` file with an embedded Python-syntax
docstring fixture; a `.md` file containing a code-fenced Python example
that is never executed).

**Examples:**
- `docs/tutorial/01_intro.md` containing a fenced `python` example for
  pedagogical comparison.
- A `.sc` test whose string literal contains the substring `import os`.

**Remediation:** Annotate with `# audit:false_positive` comment near the
trigger, OR add the file to the audit's allow-list under
`development_skills/13_skills/active/sovereignty_audit_allowlist.txt`.

**Counts against score:** NO.

---

### 11. NEEDS_REVIEW

**Definition:** The classifier could not determine the correct bucket
from automated inspection alone. Requires a human or higher-context
agent to disposition.

**Examples:**
- A `.sh` file under `superc-v1/scripts/` whose call graph is unclear.
- A vendored binary blob whose provenance is undocumented.
- An imported third-party `.toml` whose semantics depend on a tool the
  audit has not enumerated.

**Remediation:** Open a review ticket. Default-conservative until
classified: treat as ACTIVE_DEPENDENCY for scoring purposes (i.e., the
file counts against the sovereignty score until proven otherwise).

**Counts against score:** YES, conservatively, until reclassified.

---

## Required Checks

All commands assume working directory is the repo root
`/Users/desmondearly/Library/CloudStorage/OneDrive-Personal/desmond-super-c/`.
Output of every check is written to the audit evidence packet under
`development_skills/08_verification/sovereignty/<ISO-date>/`.

### Check 1 — File-language inventory

```bash
find superc-v1 -type f \
  \( -name "*.py" -o -name "*.c" -o -name "*.h" -o -name "*.sh" \
     -o -name "*.rs" -o -name "*.go" -o -name "*.ts" -o -name "*.js" \
     -o -name "Makefile" -o -name "*.mk" -o -name "*.cmake" \) \
  -not -path "*/archive/*" -not -path "*/legacy/*" \
  -not -path "*/node_modules/*" -not -path "*/.git/*" \
  | sort > evidence/inventory_nonsc_active.txt
```

Result: every non-SC file outside archive paths. Each line of output must
appear in the per-file classification table.

### Check 2 — Live Python tooling

```bash
find superc-v1 -name "*.py" -not -path "*/archive/*" -not -path "*/legacy/*" \
  | xargs -I{} wc -l {} | sort -rn > evidence/python_loc.txt
```

```bash
grep -rln "^#!/usr/bin/env python\|^#!/usr/bin/python" superc-v1 \
  -not -path "*/archive/*" > evidence/python_executables.txt
```

Any non-empty file here either resolves to ARCHIVE_ONLY (with a paired
SC implementation that is wired into the build) or remains an
ACTIVE_BLOCKER / ACTIVE_DEPENDENCY.

### Check 3 — Python heredocs hidden in shell

```bash
grep -rn "python3 <<.*EOF\|python <<.*EOF\|python3 -c \|python -c " \
  superc-v1/scripts/ superc-v1/tools/ superc-v1/.github/ \
  2>/dev/null > evidence/python_heredocs.txt
```

This is the SC-MISS-001 anti-pattern. Shell scripts that quietly invoke a
Python interpreter via heredoc or `-c` flag look like shell from a casual
read but ARE Python tooling and MUST be classified as such.

### Check 4 — seedc retirement check

```bash
grep -rn "seedc" superc-v1/scripts/gates/ superc-v1/.github/ \
  superc-v1/Makefile* superc-v1/scripts/build/ \
  2>/dev/null > evidence/seedc_buildchain_refs.txt
```

```bash
find superc-v1/seedc -type f 2>/dev/null | head -200 > evidence/seedc_tree.txt
```

If `seedc_buildchain_refs.txt` is non-empty, `seedc/` is NOT yet
ARCHIVE_ONLY regardless of any release-note claim. It is at best
TRANSITIONAL_DEPENDENCY.

### Check 5 — C debt

```bash
find superc-v1 -name "*.c" -o -name "*.h" \
  -not -path "*/archive/*" -not -path "*/legacy/*" \
  -not -path "*/tests/fixtures/*" -not -path "*/tests/interop/*" \
  | xargs -I{} wc -l {} 2>/dev/null | sort -rn > evidence/c_loc.txt
```

Tally total active C LOC. Compare to the prior audit's number. Any growth
must be explained in the scorecard's "C debt delta" line.

### Check 6 — Shell gate inventory

```bash
find superc-v1/scripts/gates superc-v1/.github/workflows \
  -type f \( -name "*.sh" -o -name "*.yaml" -o -name "*.yml" \) \
  2>/dev/null > evidence/gate_runners.txt
```

For each gate runner, classify whether the runner's logic is shell-only
(ACTIVE_DEPENDENCY, host shell) or invokes Python, Make, or another
non-SC tool (chain through to that tool's classification).

### Check 7 — scc command surface

```bash
grep -rn "scc \|scc$\| scc " superc-v1/scripts/ superc-v1/.github/ \
  2>/dev/null | grep -v "^Binary" > evidence/scc_invocations.txt
```

For each invocation, record the wrapper. If `scc` is invoked through a
Python or shell wrapper that adds non-trivial logic, that wrapper itself
needs classification.

### Check 8 — Build-chain audit

```bash
find superc-v1 -name "Makefile" -o -name "*.mk" -o -name "Cargo.toml" \
  -o -name "build.sc" -o -name "build.sh" \
  -not -path "*/archive/*" 2>/dev/null > evidence/build_drivers.txt
```

Read each. Trace the dependency graph: every tool invoked, every file
read, every interpreter spawned. Any node in that graph that is not an
`.sc` source or an SC-generated artifact must appear in a classification
row.

### Check 9 — Cross-check the inventory

After classification, verify:

```bash
wc -l evidence/inventory_nonsc_active.txt evidence/classifications.csv
```

The classification CSV must have one row per inventory line (plus header).
A discrepancy means files were dropped or duplicated during classification
and the audit must be re-run.

---

## Sovereignty Levels

The scorecard awards one of four levels based on the classification
distribution. Each level has hard requirements; missing any one
requirement drops the score one tier regardless of other strengths.

### BRONZE — Sovereignty Aspired

- SC compiler self-hosts (scc builds scc).
- Standard library has at least one module entirely in SC.
- At least one end-to-end pipeline (source -> executable) is demonstrable.
- ACTIVE_BLOCKER count may be > 0 but each is documented with a port plan.
- NEEDS_REVIEW count may be > 0.

This is the entry-level claim. It says "SUPER C is real, but you should
not yet call it sovereign without qualification."

### SILVER — Sovereignty Claimed

All BRONZE requirements, plus:

- ACTIVE_BLOCKER count = 0. Every active non-SC dependency is either
  TRANSITIONAL_DEPENDENCY (with deprecation date) or ACTIVE_DEPENDENCY
  (with documented host-reality justification).
- NEEDS_REVIEW count = 0.
- C debt has not grown since the previous audit.
- Python heredoc check (Check 3) returns zero hits in `scripts/gates/`
  and `.github/workflows/`.

Releases tagged at SILVER may claim "self-hosted" but may not yet claim
"all-SC" or "no-shims."

### GOLD — Sovereignty Demonstrated

All SILVER requirements, plus the six Gold requirements (see next
section). Gold is the level at which the public claim "SUPER C is
sovereign" becomes defensible.

### PLATINUM — Sovereignty Closed

All GOLD requirements, plus:

- ACTIVE_DEPENDENCY count = 0. The repo has no non-SC code in the
  active path at all, including no host-shell scripts and no external
  toolchain invocations.
- TRANSITIONAL_DEPENDENCY count = 0. Every cutover has fired.
- The only non-SC files in tree are TEST_FIXTURE, NEGATIVE_FIXTURE,
  GENERATED_OUTPUT, ARCHIVE_ONLY, BOOTSTRAP_ARCHIVE,
  EXTERNAL_HOST_REALITY, or FALSE_POSITIVE.
- Bootstrap reconstruction recipe in `docs/bootstrap/` has been
  exercised end-to-end since the last sovereignty audit.

PLATINUM is the terminus. The claim "SUPER C is closed-sovereign" is
defensible only at PLATINUM and only with this skill's evidence packet
attached.

---

## Gold Requirements

GOLD requires all six items below. None may be waived.

1. **seedc is ARCHIVE_ONLY or BOOTSTRAP_ARCHIVE.** `seedc/` directory
   contains no file that is read or invoked by any active build, gate,
   or developer tool. The retirement is pinned to a tag, and Check 4
   returns zero hits in build-chain paths.

2. **Python tooling is ported or archived.** No `*.py` file under
   `superc-v1/` is classified ACTIVE_BLOCKER or ACTIVE_DEPENDENCY.
   Every Python tool either has an SC replacement wired in as primary,
   or is ARCHIVE_ONLY with the SC replacement as the sole live path.

3. **C debt is non-growing and bounded.** Total active C LOC (Check 5)
   is either zero, or is below a recorded budget that has not increased
   in the last three audits. Any growth must be reverted before GOLD.

4. **Shell heredoc count is zero.** Check 3 returns no Python heredocs
   in any shell script under `scripts/`, `gates/`, or `.github/`.

5. **scc command surface is unwrapped.** Check 7 shows that `scc` is
   invoked directly (or through a documented SC-side launcher), not
   through Python or shell wrappers that add non-trivial logic.

6. **Build chain traces to SC sources or generated artifacts only.**
   Check 8 confirms every node in the build dependency graph is either
   an `.sc` source, an SC-generated artifact, a sanctioned host-reality
   call, or a BOOTSTRAP_ARCHIVE node used only for trust-by-inspection.

Each Gold requirement maps directly to a previously-encountered
sovereignty regression. Failing any one means the regression class has
recurred and the seal must be withheld.

---

## Hard Stop

If ANY of the following is true at audit time, STOP. Do not produce a
sovereignty seal. Do not tag the release. Escalate to the user.

- ACTIVE_BLOCKER count is non-zero AND the release notes claim
  "sovereign," "self-hosted," "all-SC," or "no-shims."
- A file classified ARCHIVE_ONLY in the prior audit appears in any
  evidence file (`gate_runners.txt`, `python_executables.txt`,
  `seedc_buildchain_refs.txt`) of the current audit. This means a
  retirement was silently undone.
- Check 3 (Python heredocs) returns hits in `scripts/gates/` or
  `.github/workflows/` AND the prior audit reported zero. This is the
  SC-MISS-001 regression signature.
- The classification CSV has fewer rows than the inventory file
  (some files were quietly dropped from classification).
- The scorecard claims GOLD or PLATINUM but the evidence packet is
  missing any of the nine check outputs.
- A NEEDS_REVIEW entry has been carried for more than three consecutive
  audits without resolution. Three is the cap; a four-times-deferred
  review is an unresolved sovereignty question and must block the seal.

The hard stop is not an inconvenience. It is the point of the skill.

---

## Failure Mode This Skill Prevents

SC-MISS-001 was the surprise discovery that prompted this skill's
creation. A prior sovereignty audit had been declared green: seedc was
labeled archive, the SC self-host was real, and a release was about to
be tagged "no-shims." A late-running spot-check found:

- Several gate runners under `superc-v1/scripts/gates/` invoked
  `python3 <<EOF ... EOF` heredocs. The shell-language file extension
  hid that Python was load-bearing in the gate path. The audit had
  searched for `*.py` files and missed the embedded interpreter.
- `seedc/` was officially "archive" in the release notes, but
  `near_term_success.sh` still chained through a build target that
  required the C-side seedc parser to be present. The retirement claim
  was technically true at the file-tree level and false at the
  build-graph level.
- One module marked "implemented" in the truth-state ledger had a
  scaffolded SC implementation that compiled, while the actual logic
  lived in a co-named Python helper that the CI invoked via shell. The
  word "implemented" had drifted from "the SC code does the work" to
  "an SC file exists with the right name."
- A blocker reported in three consecutive sessions as "transitional"
  had no port plan, no deprecation date, and no SC counterpart in tree.
  It had been classified as transitional by inertia, not by evidence.

The four failure-mode entries in this skill's YAML correspond directly
to those four discoveries:

1. **active blockers misclassified as transitional** — the inertia case
   above. Remedy: TRANSITIONAL_DEPENDENCY requires a paired live SC
   replacement AND a deprecation trigger; absence of either reclassifies
   to ACTIVE_BLOCKER.

2. **scaffolded marked implemented** — the co-named-helper case.
   Remedy: GOLD requirement 6 demands the build graph trace to SC
   sources for the work, not just to SC files for the appearance.

3. **Python heredocs hidden** — the heredoc case. Remedy: Check 3 is
   mandatory at every audit; non-zero results in `scripts/gates/` or
   `.github/` are a hard stop.

4. **seedc declared archive while build deps remain** — the retirement-
   undone case. Remedy: Check 4 cross-references the file-tree archive
   claim against the build-chain reality; Gold requirement 1 makes the
   two-sided check non-waivable.

The skill prevents SC-MISS-001 from recurring by forcing the audit to
operate on evidence (grep outputs, build-graph traces, classification
counts) rather than on remembered claims from prior sessions. Every
non-SC file in the active path must earn its classification with a
citation; "we already decided" is not a citation.

---

## Validation

See `08_verification/skill_tests/TEST_SKILL_SC_DEPENDENCY_SOVEREIGNTY_001_001.yaml`.

The test asserts:

- Running all nine checks against a known-mixed fixture repo produces
  a classification CSV with one row per inventory entry and zero
  unclassified files.
- A fixture containing a Python heredoc inside a `scripts/gates/*.sh`
  file triggers the Check 3 hard stop.
- A fixture containing a `seedc/` reference inside a gate runner
  triggers the Check 4 hard stop even when `seedc/` itself is labeled
  archive in the release notes.
- A scorecard that claims GOLD without an evidence packet containing
  all nine check outputs is rejected by the validator.
- The eleven category names in this playbook match the eleven category
  names enumerated in the scorecard schema; drift between the two is
  detected and reported.

---

## Check 7b — Empirical Compiler Surface Probe (per SC-MISS-003)

Before any sovereignty audit asserts what `scc` does or does not support, run:

```bash
./compiler/scc/build/scc help > /tmp/scc_help_actual.txt
grep -c 'streq(argv\[1\]' compiler/scc/src/scc_entry.c > /tmp/scc_dispatch_count.txt
./compiler/scc/build/scc run-jit <minimal_main.sc>
```

Cross-check:
- Number of dispatch arms in scc_entry.c vs subcommands in `scc help`.
- Empirical exit code/output for each claimed-working subcommand.
- Any "MISSING" claim in a prior report against an actual `streq` grep.

**Hard stop:** if a prior dependency report claims subcommand X is MISSING but `grep streq(argv\[1\], "X")` returns a hit, the prior report is STALE and the audit must be re-derived.

**Originating evidence:** v31.3 A2 + I2 caught v31.2 final report §11 claiming "scc lacks `run` subcommand" — `run-jit` was dispatched at scc_entry.c:6094. Build-graph greps would have caught this; the skill DID NOT mandate them. Now it does.

---

## Check 7c — Empirical Intrinsic Codegen Probe (per SC-MISS-003)

Before any sovereignty audit asserts an intrinsic `__<name>__` "has prior canonical usage" or "is wired":

```bash
# Verify codegen recognition (NOT just parser recognition)
grep -rn "<intrinsic_name>" compiler/seedc/src/codegen_*.c compiler/scc/src/codegen_*

# If zero hits, intrinsic has NO codegen support regardless of parser acceptance.
# Run probe test in tests/diagnostics/probe_<intrinsic>.sc to confirm via run-jit.
```

**Hard stop:** if codegen grep returns zero hits AND the audit claims the intrinsic is "battle-tested" or "wired", the claim is REJECTED. Parser acceptance ≠ codegen support.

**Originating evidence:** v31.3 I4 census: 0/6 SC user intrinsics (`__syscall__`, `__load_u32__`, `__strdata__`, `__store_u8__`, `__load_u8__`, `__load_u64__`) have codegen recognition. v31.2's distinction between "load_u32 working" and "store_u8 unverified" was wrong — both are parse-only.
