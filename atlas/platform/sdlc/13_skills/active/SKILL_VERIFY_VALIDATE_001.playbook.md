# verify-validate

<!-- Source: migrated from ~/.claude/skills/verify-validate/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: verify-validate -->

**Summary.** Pre-commit verification and validation gate. Use this skill BEFORE every commit, after every file change, before closing any task or session, and BEFORE every git push. Triggers on: any file modification, any code change, "verify this", "validate before commit", "check for accuracy", "pre-commit check", "push to remote", "git push", or any request to commit or push code. NEVER commit or push without running this skill first. This is the quality gate that prevents broken, inaccurate, or non-compliant code from entering the repository. Continually refined after every session that surfaces new error patterns.

# Verify & Validate — Pre-Commit Quality Gate

**ABSOLUTE RULE: No file is committed without passing this gate.**

Think of this skill as the quality inspector at the end of a manufacturing line.
Every product (commit) must pass inspection before it ships. Defects found at
inspection are cheap to fix. Defects that ship are expensive to recall.

---

## PROJECT-TYPE ADAPTATION

Gates 1–2 are project-type dependent. Before running, identify the project:

| Project type | Gate 1 command | Gate 2 command |
|---|---|---|
| C / SUPER C | `make clean && make` | `make test && bash tests/test_driver.sh` |
| Python / FastAPI | `python3 -m py_compile **/*.py` | `pytest` or note "no tests yet" |
| React / Vite | `npm run build` | `npm test` or note "no tests yet" |
| Multi-repo move | syntax check ALL affected repos | status check ALL repos |

Gates 3–7 and the cross-project patterns below apply to ALL project types.

---

## GATE EXECUTION ORDER

Run ALL applicable gates in this exact order. Do not skip. Do not reorder.
A failure at any gate means: FIX FIRST, then restart from Gate 1.

---

### GATE 1 — BUILD CLEAN

**C / SUPER C:**
```bash
make clean && make
```
Pass criteria: Exit code 0, zero warnings with `-Wall -Wextra -Werror -pedantic`.

**Python / FastAPI:**
```bash
python3 -m py_compile backend/*.py backend/routes/*.py
```
Pass criteria: Zero syntax errors. All files compile without output.

**React / Vite:**
```bash
npm run build
```
Pass criteria: Exit code 0, `dist/` produced with no errors.

**Failure action:** Fix the build error immediately. Do not proceed to Gate 2.

**Pattern from project history:** Build failures after merging content from
an isolated test file into a larger file indicate a content-driven edge case,
not a logic error. Use binary search to isolate the offending token or
declaration before attempting fixes.

---

### GATE 2 — FULL TEST SUITE GREEN

**C / SUPER C:**
```bash
make test
bash tests/test_driver.sh
bash tests/scc_smoke.sh
```

**Python / FastAPI / React:** Run project-specific test suite. If no test suite
exists yet (new scaffold), record "0/0 — no tests, gap noted" and create a
follow-up task to add tests. Never silently skip.

**Pass criteria:** All tests pass. Zero failures. Zero regressions from prior
HEAD. Quote exact counts: `N/N PASS, 0 FAIL`.

**Failure action:** A regression means the change broke existing behavior.
Revert or fix — do not commit over a regression.

**Critical lesson:** `N/N PASS` coexists with type errors in unreachable
function bodies. Green tests do NOT cover orphan code. Gate 3 catches what
Gate 2 misses.

---

### GATE 3 — ORPHAN AND STALE REFERENCE CHECK

**3A — Orphan function check (compiled projects)**

For every new function defined in this commit: verify its type signature is
correct even though it may not yet be called.

```
For each new function introduced in the diff:
  1. Is the parameter type list correct for how callers will invoke it?
  2. Is the return type correct for what callers expect?
  3. Are any argument counts off by one?
  4. Are any field names correct (not drifted from their struct definition)?

Specific patterns to check:
  - Arena index parameters: should be u32, not usize or pointer
  - Slice parameters: should be (ptr, len) pair, not a single reference
  - Bundle structs: field names must exactly match the struct definition
  - Return types: void vs non-void function distinction
```

**Session 20 lesson:** Five type errors in orphan functions were caught by
the follow-behind auditor. They would have blocked walker integration 1-3
sessions later.

**3B — Stale path reference check (ALL projects, especially after file moves)**

Whenever files move to new locations: grep all source files, error messages,
comments, config files, and manifests for the OLD path. Every match is a bug.

```bash
# Substitute old_path with what moved:
grep -rn "old_path" backend/ frontend/ *.json *.md *.yaml
```

**kjva-bible lesson (2026-05-25):** After moving `models/kjva/` → `KJVA/training/`,
a 503 error message in `routes/complete.py` still said
`"cp ... models/kjva/weights.safetensors"`. Gate 3 caught it before it confused
users. Stale paths in error messages, help text, and comments are bugs.

**3C — Framework anti-pattern check (ALL projects)**

Catch patterns that compile or parse cleanly but produce wrong behavior at runtime.
Run the block for your project type — all must return zero matches.

**MLX / TokenlessLM:**
```bash
grep -rn "mx\.log_softmax\|requires_grad\|\.backward()" backend/
```
These are PyTorch-isms. MLX does not have them — they silently corrupt training.
Also verify: `model.freeze()` not `requires_grad=False`; weights via `mx.load()`;
gradients via `nn.value_and_grad`.

**Python / skill-registry repos (ATLAS, child repos):**
```bash
# No hardcoded absolute paths — scripts must use Path(__file__).resolve().parents[N]
grep -rn '"/Users/\|"/home/' infrastructure/scripts/ --include="*.py"

# No os.path — all path work must use pathlib.Path
grep -rn "import os\.path\b\|os\.path\." infrastructure/scripts/ --include="*.py"

# parents[N] depth must match actual nesting — scripts in infrastructure/scripts/ are 2 deep
grep -rn "parents\[1\]" infrastructure/scripts/ --include="*.py"
```

**TypeScript ESM repos (apps/backend/, apps/frontend/):**
```bash
# No __dirname in ESM modules — use import.meta.dirname
# Excludes node_modules and next.config.ts (CJS context where __dirname is correct)
grep -rn "__dirname" apps/backend/ apps/frontend/ \
  --include="*.ts" --include="*.mts" \
  --exclude-dir=node_modules \
  | grep -v "next\.config\.ts"
```
`next.config.ts` runs in Node.js CJS context — `__dirname` is correct there, not a violation.

**Pass criteria:** All greps return zero matches for your project type.

**ATLAS lesson (2026-05-25):** After moving `25_automation/` two levels
deeper to `infrastructure/scripts/`, `parents[1]` in 15 scripts pointed one level
short of the repo root. The bulk `sed` substitution fixed quoted-string paths but
missed path-join syntax (`/ "dir" /`), requiring a second targeted pass. 3C catches
this class of error before it reaches the commit.

---

### GATE 4 — ID AND COLLISION CHECK

Verify that new names introduced in this commit do not collide with existing reserved
names, keywords, or IDs.

**SUPER C / SC projects:**
```bash
grep -n "TOK_[A-Z]" src/lexer.c | grep '"' | sed 's/.*"\(.*\)".*/\1/' | sort > /tmp/keywords.txt
# Then verify no new identifier matches a keyword in the table.
```
**TOK_PHASE lesson:** The identifier `phase` triggered 10 cascade parse errors
that took a full session to diagnose. Pre-flight catches it in 30 seconds.

**Skill-registry repos (ATLAS, child repos):**
```bash
# Duplicate SKILL IDs
grep "^id:" platform/sdlc/13_skills/active/SKILL_*.yaml | awk -F': ' '{print $2}' | sort | uniq -d

# Duplicate skill_number values
grep "^skill_number:" platform/sdlc/13_skills/active/SKILL_*.yaml | awk '{print $2}' | sort | uniq -d

# Duplicate router intent keys
python3 -c "
import yaml, collections
r = yaml.safe_load(open('platform/systems/37_command_protocol/trigger_router.yaml'))
targets = list(r.get('targets', {}).keys())
dupes = [k for k,v in collections.Counter(targets).items() if v > 1]
print('Duplicate intents:', dupes) if dupes else print('PASS: no duplicate intents')
"
```

**Pass criteria:** All three return zero duplicates.

**Python / TypeScript repos:**
```bash
# Duplicate exported function/class names within a module group
# (run manually or with a linter — no universal one-liner)
```
Check manually for any new symbol that shadows a built-in or a name already exported
from the same module.

---

### GATE 5 — CONVENTION AND POLICY COMPLIANCE CHECK

**5A — Project convention compliance (ALL project types)**

| Project type | Convention check | Command |
|---|---|---|
| C / SUPER C | C6 struct out-param, C7 slice-as-ptr, C8 arena-idx, BOOTSTRAP-CRITICAL annotations | Manual review of diff |
| Skill-registry repos | Every SKILL_*.yaml has required fields + matching playbook | See script below |
| Python repos | No wildcard imports, no bare `except:`, no mutable default args | `grep -rn "from .* import \*\|except:\b" --include="*.py"` |
| TypeScript repos | No `any` type in new code, no `@ts-ignore` without justification comment | `grep -rn ": any\b\|@ts-ignore" apps/ --include="*.ts"` |

**Skill schema completeness check (skill-registry repos):**
```bash
for f in platform/sdlc/13_skills/active/SKILL_*.yaml; do
  for field in id title version status domains trigger_conditions hard_constraints router_intents; do
    grep -q "^${field}:" "$f" || echo "MISSING ${field}: $f"
  done
  base="${f%.yaml}"
  [ -f "${base}.playbook.md" ] || echo "MISSING playbook: ${base}.playbook.md"
done
```
**Pass criteria:** Zero output.

**5B — Gitignore coverage for binary/weight files:**
```bash
grep "\*.safetensors" .gitignore   # catch-all for weight files
```
Both a catch-all AND any project-specific canonical path must be present.

**5C — Cross-repo manifest consistency:**
After any file move spanning repos, verify ALL manifests in both repos reference
the new path before either commit lands.
```bash
grep -rn "old_path" ml-training/manifests/
```

---

### GATE 6 — REGISTRY AND COUNT INTEGRITY CHECK

Verify the counts and registrations are internally consistent. Applies to every
project that maintains a registry or manifest.

**SUPER C — LOC ceiling:**
```bash
make loc
```
If within 500 of escalation: flag to human. If above hard ceiling: STOP.

**Skill-registry repos (ATLAS, child repos):**
```bash
YAML_COUNT=$(ls platform/sdlc/13_skills/active/SKILL_*.yaml 2>/dev/null | wc -l | tr -d ' ')
REGISTRY_TOTAL=$(grep "^total:" platform/sdlc/13_skills/skills.registry.yaml | awk '{print $2}')
REGISTRY_ENTRIES=$(grep -c "^- name:" platform/sdlc/13_skills/skills.registry.yaml)

echo "SKILL_*.yaml files : $YAML_COUNT"
echo "Registry total     : $REGISTRY_TOTAL"
echo "Registry entries   : $REGISTRY_ENTRIES"

# All three must match
[ "$YAML_COUNT" -eq "$REGISTRY_TOTAL" ] && [ "$YAML_COUNT" -eq "$REGISTRY_ENTRIES" ] \
  && echo "PASS: counts match" \
  || echo "FAIL: count mismatch — run validate_skill_router_integration.py"
```
Also run the full integration validator:
```bash
python3 infrastructure/scripts/validate_skill_router_integration.py
```
**Pass criteria:** `PASS: skill router integration (N active skills — all registered and routed)` with N matching the YAML count.

**All other repos with manifests / registries:**
Verify: file count on disk == declared count in manifest == CI gate expectation.
Flag any mismatch before commit.

---

### GATE 7 — LOCK LAYER AND CROSS-REPO STATUS CHECK

**7A — Lock layer diff (C / governance commits):**

```bash
git diff HEAD~1..HEAD -- "canonical/path/"
```

Diff must show ONLY explicitly-authorized files. Unexpected files in the lock
layer = stop, identify, possibly require governance patch (STOP-6 equivalent).

For governance commits: quote canonical names verbatim BEFORE editing. Diff
must touch exactly two files: schema + governance record.

**7B — Multi-repo clean status (cross-repo moves):**

When a commit spans multiple repos (e.g., removing files from repo A and adding
to repo B), check BOTH repos are fully clean after both commits land:

```bash
git -C /path/to/repo-A status --short   # must be empty
git -C /path/to/repo-B status --short   # must be empty
```

Any untracked non-ignored files in either repo after the move = incomplete work.

**2026-05-25 lesson:** After moving KJVA/ and corpus dirs from Tokenless Models
to kjva-bible, Gate 7 revealed that the fix to `complete.py` was unstaged.
Without this check, a stale error message would have shipped in the committed
state.

**7C — No accidentally tracked binary files:**

```bash
git ls-files | grep -E "\.(safetensors|gguf|bin|pt|pth|onnx)$"
```

Must return zero matches. Binary weight files are always gitignored.

**7D — Generated cache directories not present on disk:**

Before any commit: verify no generated cache directories are sitting on disk,
even if they are gitignored (gitignore prevents commit, but does not delete).

```bash
find . -maxdepth 3 -type d \( \
  -name ".pytest_cache" -o -name "__pycache__" -o -name ".mypy_cache" \
  -o -name ".ruff_cache" -o -name ".hypothesis" -o -name ".next" \
  -o -name "coverage" \
\) -not -path "./.git/*"
```

**Pass criteria:** No output.

**Failure action:** Delete the dir (`rm -rf .pytest_cache` etc.), ensure `.gitignore`
covers it at the level where the tool runs — not just the repo root.

**ATLAS lesson (2026-05-25):** `.pytest_cache/` was left at the repo
root after a 38K-file reorganization commit. It was in `.gitignore` so it never
committed, but the physical directory persisted and went unnoticed. The same pattern
was recurring across GENESYS and child repos. Gitignore ≠ deleted — this gate
enforces the delete.

---

### GATE 8 — CAPACITY AND BUFFER CHECK

*(C-host projects with fixed-size buffers only)*

For each capacity constant, verify `current_capacity > largest_input × 1.5`.

**TOKEN_BUFFER_CAP lesson (Session 24):** The capacity was provisioned for
Stage 5d files (~3,343 SC). codegen_x86.sc at 4,751 SC exceeded it and
blocked the first actual bootstrap attempt. A 50-line fix could have been
applied 5 sessions earlier if this gate had been run.

---

### GATE 9 — REPRODUCIBLE BUILD CHECK

*(Projects requiring deterministic output only)*

```bash
make clean && make && sha256sum build/output > /tmp/sha1.txt
make clean && make && sha256sum build/output > /tmp/sha2.txt
diff /tmp/sha1.txt /tmp/sha2.txt
```

Both runs must produce byte-identical output.

---

### GATE 10 — BOOTSTRAP-CRITICAL SEMANTIC MATCH

*(SUPER C bootstrap closure only)*

For every BOOTSTRAP-CRITICAL annotated function, verify against reference:
- Iteration order (must be identical)
- Discriminant/tag values (must match enumeration order)
- Sentinel values (must match between implementations)
- Field assignment order (matters for memory layout)
- Error code emission (must match for byte-identical output)

---

## GATE RESULTS TEMPLATE

```
VERIFY-VALIDATE RESULTS — [commit description]

Project type:          [C / Python+FastAPI / React / Multi-repo move]

Gate 1 Build:          PASS / FAIL — [details]
Gate 2 Tests:          PASS N/N / FAIL / N/A (no tests yet — gap noted)
Gate 3A Orphan check:  PASS / ISSUES FOUND: [list]  (compiled projects)
Gate 3B Stale paths:   PASS / STALE REFS: [list]
Gate 3C Anti-patterns: PASS / VIOLATIONS: [list]  (all projects — use type-matched grep)
Gate 4 ID collisions:  PASS / DUPLICATES: [list]  (all projects — skill IDs, keywords, symbols)
Gate 5A Conventions:   PASS / VIOLATIONS: [list]  (all projects — use type-matched check)
Gate 5B Gitignore:     PASS / GAPS: [list]
Gate 5C Manifests:     PASS / STALE: [list]  (cross-repo moves)
Gate 6 LOC ceiling:    PASS [X/ceiling] / ESCALATION NEEDED  (SC projects)
Gate 7A Lock layer:    PASS [N files] / UNEXPECTED: [list]  (governance)
Gate 7B Repo status:   PASS (both repos clean) / DIRTY: [list]
Gate 7C Binary check:  PASS (0 tracked) / FOUND: [list]
Gate 7D Cache dirs:    PASS (none on disk) / FOUND: [list] — delete before commit
Gate 7E Pre-push:      PASS (origin verified = correct repo) / MISMATCH: [remote -v output]
Gate 6 Registry/LOC:   PASS [yaml=registry=router] / MISMATCH: [details]
Gate 8 Capacity:       PASS / BUMPS NEEDED: [list]  (C-host projects)
Gate 9 Reproducible:   PASS / NON-DETERMINISTIC: [details]
Gate 10 BC-critical:   PASS / DIVERGENCES: [list]  (SC bootstrap)

VERDICT: [ALL PASS — proceed to commit] / [FAILURES — fix first]
```

---

## RAPID FIRE MODE

For trivial changes (1-5 line edits, comment changes, documentation):
Minimum gates: 1 (build) + 2 (tests) + 3B (stale paths) + 7D (cache dirs) + 7 (status)

Never skip Gate 2. Never skip Gate 3B after any file move. Never skip Gate 7
for multi-repo or lock-layer-adjacent changes.

---

## CROSS-REPO FILE MOVE CHECKLIST

Use this whenever files are moving from one git repo to another:

1. `git rm --cached <dirs>` in source repo (untrack, keep on disk)
2. `mv` the physical directories to destination repo
3. `git add <dirs>` in destination repo
4. **Gate 3B**: grep all source files in BOTH repos for old path — fix every match
5. **Gate 5C**: update ALL manifests in source repo to reference new path
6. **Gate 7B**: verify BOTH repos are clean after both commits
7. **Gate 7C**: verify no binary files accidentally tracked in destination

Order matters: untrack before move, move before add, grep before commit.

**2026-05-25 lesson:** rsync/cp is wrong for moves — the user correctly rejected
it. `git rm --cached` + `mv` + `git add` is the correct cross-repo move sequence.
It preserves the physical files, cleanly removes tracking from source, and adds
tracking in destination in a single atomic pair of commits.

---

## CONTINUOUS IMPROVEMENT

After every session that surfaces a new error pattern:
1. Add a new gate or extend an existing gate to catch it
2. Add the pattern to the relevant gate's "Failure action" section
3. Update the gate results template if new fields are needed
4. Increment the skill version

Current version: 1.4.0
Last updated: 2026-05-26

**Changelog:**
- v1.4.0 (2026-05-26): Added Gate 7E — Pre-push remote verification. MANDATORY
  before every git push. Run `git remote -v` and cross-check URL against canonical
  map in [[git-remote-discipline]] before pushing. Trigger also added to skill
  description for "push to remote" / "git push". Pattern sourced from SUPER C
  cross-repo contamination: `superc-v1/` had `origin` pointing to `Storbits.git`;
  `git push origin --follow-tags` contaminated Storbits with 78 SUPER C tags + 1
  branch. Recovery required deleting 79 refs from wrong remote.
- v1.3.0 (2026-05-26): Gates 3C, 4, 5A, 6 rewritten from project-specific N/A
  gates to universal gates covering all project types. Gate 3C: MLX anti-patterns
  + Python path discipline + TS ESM check. Gate 4: SC keyword collision + skill ID
  / skill_number / router intent duplicate check. Gate 5A: C conventions + skill
  schema completeness (required fields + playbook) + Python/TS linting rules.
  Gate 6: SC LOC ceiling + skill registry count integrity (yaml count == registry
  total == router coverage). No gate is ever N/A again.
- v1.2.0 (2026-05-25): Added Gate 7D — Generated cache directory check. Pattern
  sourced from ATLAS reorganization session where `.pytest_cache/`
  survived a 38K-file commit undetected because gitignore ≠ deleted. Gate 7D now
  mandatory in Rapid Fire Mode. apex-directory-discipline skill also updated with
  the same pattern.
- v1.1.0 (2026-05-25): Added project-type adaptation table; Gate 3B stale path
  check; Gate 3C MLX rule compliance; Gate 5B gitignore coverage check; Gate 5C
  cross-repo manifest consistency; Gate 7B multi-repo clean status; Gate 7C
  binary tracking check; Cross-Repo File Move Checklist; updated results
  template with new fields. Patterns sourced from kjva-bible / Tokenless Models
  session.
- v1.0.0 (Session 24): Initial from SUPER C project sessions 1-24.
  TOKEN_BUFFER_CAP pattern added.
