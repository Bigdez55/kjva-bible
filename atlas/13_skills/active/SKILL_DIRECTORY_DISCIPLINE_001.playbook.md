# apex-directory-discipline

<!-- Source: migrated from ~/.claude/skills/apex-directory-discipline/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: apex-directory-discipline -->

**Summary.** Governs all file and directory operations within the GENOSCOPY / Project Apex codebase. Use this skill BEFORE creating any file, directory, or document in any GENOSCOPY session. The core rule is: FIND before CREATE. GENOSCOPY is one unified codebase being progressively rewritten in SUPER C. Every component already has a canonical home directory. New code, new specs, new amendments, and new documents all live INSIDE existing directories — never in new parallel structures. Trigger this skill whenever an agent is about to: create a new directory, add a new spec file, place an amendment, create a document, or add any artifact to the project. If in doubt, consult this skill first.

# Apex Directory Discipline

## The One Rule

> **FIND before CREATE.**
>
> Before writing a single file, answer: *does a directory for this already exist?*
> If yes — work inside it. If no — ask the Chief Architect before creating anything.

GENOSCOPY is a single codebase being progressively rewritten in SUPER C.
The directory tree is the canonical project structure. It does not change
because a new feature is being added. The feature finds its home in the
existing tree. The tree is not restructured for the feature.

---

## The Violation Pattern (What NOT to Do)

These are the exact mistakes this skill exists to prevent:

| Wrong action | Why it's wrong | Correct action |
|---|---|---|
| Create `GENOSCOPY/emulation/` | XEMU already lives in `devices/desktop/vm/xemu/` | Work in the existing XEMU directory |
| Create `GENOSCOPY/xisc-apex/` | XISC already lives in `GENOSCOPY/xisc/` | Work inside `xisc/` |
| Create `GENOSCOPY/rmec/amendments/` | RMEC amendments are a single doc at root | Append to `RMEC_AMENDMENTS_*.md` at root |
| Create `GENOSCOPY/docs/` parallel structure | Docs have an existing location | Find the existing docs home |
| Create any `*-apex/` parallel directory | "Apex rewrite" means work IN the existing dir | Rewrite files in place |
| Create `GENOSCOPY/superc-v2/` | The compiler lives where it lives | Extend the existing compiler directory |
| Leave `.pytest_cache/` on disk | Generated — never belongs in any repo | Delete it; ensure `.gitignore` covers it |
| Leave `__pycache__/` committed | Generated — never belongs in any repo | `git rm -r --cached __pycache__/`; gitignore |
| Leave `node_modules/` committed | Dependency cache — always reconstructable | Add to `.gitignore`; never `git add` it |
| Leave `.mypy_cache/`, `.ruff_cache/`, `.hypothesis/` | Linter/test caches — generated artifacts | Delete and gitignore |

---

## The GENOSCOPY Canonical Directory Map

Before creating any file, look up the correct home here.

```
GENOSCOPY/
│
├── xisc/                          ← XISC Cross Instruction Set Computing
│   ├── spec/                      ← All XISC spec files (11 existing + new ones here)
│   ├── include/                   ← C headers (being superseded by SC, same location)
│   ├── runtime/
│   │   ├── xkabi_native/          ← Native layer (C11 → SUPER C rewrite lives HERE)
│   │   ├── personality_linux/     ← Linux ABI translation (SC rewrite lives HERE)
│   │   └── translator_service/    ← Python orchestrator (SC rewrite lives HERE)
│   ├── conformance/               ← Conformance suite (SC rewrite lives HERE)
│   └── benchmarks/
│
├── devices/
│   └── desktop/
│       └── vm/
│           └── xemu/              ← XEMU emulation framework (ALL xemu code lives HERE)
│               └── src/           ← Source files (SC rewrite lives HERE)
│
├── superc/ (or compiler root)     ← SUPER C compiler source
│   ├── compiler/
│   │   └── scc/                   ← scc self-host source
│   └── seedc/                     ← seed compiler (C)
│
├── docs/                          ← Project documentation (all docs go HERE)
│
├── RMEC_AMENDMENTS_*.md           ← Single amendments file at ROOT (not in subdirectory)
├── XEMU_SPEC_v*.md                ← XEMU spec at ROOT or in docs/ (not in new emulation/)
└── [other root-level docs]
```

**If a directory is not on this map:** ask the Chief Architect before creating it.
Do not infer a new home. Do not create a parallel structure.

The full canonical map with file-level detail lives at
`references/canonical-directory-map.md`.

---

## The Decision Protocol (Run Before Every File Operation)

```
STEP 1: What am I about to create?
        Name it precisely. e.g. "XISC-Apex object model spec"

STEP 2: Search the canonical map above.
        Where does this class of artifact live?
        e.g. "XISC specs live in xisc/spec/"

STEP 3: Does that directory already exist?
        YES → Place the file there. Do not create a new directory.
        NO  → STOP. Ask the Chief Architect. Do not create the directory.

STEP 4: Does a file with a similar name already exist there?
        YES → Is this an update to that file? If so, edit it in place.
              Is this a new version? Append version number, same directory.
        NO  → Create the file in the existing directory.

STEP 5: Am I naming this with an "-apex" suffix or creating a "*-apex/" dir?
        If YES → STOP. "Apex rewrite" means the existing directory IS the target.
                 The file goes inside the existing directory, not in a new one.
```

---

## Rewrite Discipline (SUPER C Progressive Rewrite)

The GENOSCOPY project is being progressively rewritten in SUPER C. This means:

1. **The C/Python original stays in place** until the SUPER C replacement passes its gate
2. **The SUPER C replacement file lives in the SAME directory** as the original
   - `xisc/runtime/xkabi_native/` gets `.sc` files alongside `.c` files
   - `devices/desktop/vm/xemu/src/` gets `.sc` files alongside `.c` files
3. **The directory does NOT get renamed** — `xkabi_native/` stays `xkabi_native/`
4. **No parallel `*-sc/` or `*-apex/` directories** are created alongside originals
5. **The C file is deleted** when the SC replacement passes its gate — not before

---

## Amendment and Governance Document Discipline

| Document type | Canonical location | Rule |
|---|---|---|
| RMEC Amendments | `GENOSCOPY/RMEC_AMENDMENTS_*.md` (root, single file) | Append to existing file. Never create `rmec/amendments/` |
| XEMU Spec | `GENOSCOPY/docs/XEMU_SPEC_v*.md` or root | Version number in filename. Never create `emulation/` |
| XISC Apex Spec | `GENOSCOPY/xisc/spec/XISC_APEX_SPEC_*.md` | Alongside the 11 existing spec files |
| SUPER C Lexicon updates | In the existing lexicon vol files | Append or version. Never create `superc-v2/` |
| Stage gate reports | Alongside existing gate report files | Same directory as prior gates |

---

## Continuously Refining This Skill

Every time a new violation pattern is discovered, add it to the **Violation Pattern** table
and update the **Canonical Directory Map** if a new directory was legitimately created.

**Refinement triggers:**
- A new directory was created that shouldn't have been → add to violation table
- A new legitimate directory was created by Chief Architect directive → add to the map
- A file was placed in the wrong location → document the correct location
- A naming convention mistake was made → add a naming rule

---

## Quick Reference Card

```
Q: Where does XEMU code go?
A: devices/desktop/vm/xemu/

Q: Where does XISC SUPER C rewrite go?
A: xisc/ (same directory as the C original)

Q: Where does a new RMEC Amendment go?
A: Append to RMEC_AMENDMENTS_*.md at GENOSCOPY root

Q: Where does a new spec file go?
A: Alongside existing spec files in the relevant spec/ subdirectory

Q: Should I create a new top-level directory?
A: NO. Ask the Chief Architect first. The answer is almost always no.

Q: What is "apex rewrite"?
A: It means rewriting existing C/Python into SUPER C IN THE SAME DIRECTORY.
   It never means creating a new directory with "-apex" in the name.
```

---

## Generated Cache Gate (Cross-Repo Rule)

This gate applies to **every repository**, not just GENOSCOPY. Run it whenever you
finish a session that touched Python, Node.js, or any test runner.

### The Problem Pattern

Generated cache directories accumulate silently. They are not noticed until a commit
or status check reveals thousands of untracked files. `.pytest_cache` alone has caused
cleanup debt in ATLAS, GENESYS, and child repos.

### Cache Directories That Must Never Be Committed

| Directory | Generator | Required .gitignore entry |
|---|---|---|
| `.pytest_cache/` | pytest | `.pytest_cache/` |
| `__pycache__/` | Python interpreter | `__pycache__/` |
| `*.pyc`, `*.pyo` | Python compiler | `*.pyc` / `*.pyo` |
| `.mypy_cache/` | mypy | `.mypy_cache/` |
| `.ruff_cache/` | ruff | `.ruff_cache/` |
| `.hypothesis/` | Hypothesis testing | `.hypothesis/` |
| `node_modules/` | npm/yarn/pnpm | `node_modules/` |
| `dist/` | build tools | `dist/` |
| `.next/` | Next.js | `.next/` |
| `coverage/` | test coverage | `coverage/` |
| `.cache/` | various | `.cache/` |

### Mandatory End-of-Session Check

Before closing any session that ran Python tests or npm commands:

```bash
# Check for cache dirs at repo root and one level deep
find . -maxdepth 2 -type d \( \
  -name ".pytest_cache" -o -name "__pycache__" -o -name ".mypy_cache" \
  -o -name ".ruff_cache" -o -name ".hypothesis" -o -name "node_modules" \
  -o -name ".next" -o -name "coverage" \
\) -not -path "./.git/*" | head -20

# Delete any that appear (they are all regenerable):
# rm -rf .pytest_cache __pycache__ .mypy_cache .ruff_cache .hypothesis
```

### Fixing a Repo That Has Already Committed Cache Dirs

```bash
# Remove from git tracking without deleting from disk (if needed):
git rm -r --cached .pytest_cache __pycache__ .mypy_cache 2>/dev/null

# Then ensure .gitignore covers them and commit:
echo ".pytest_cache/" >> .gitignore
echo "__pycache__/" >> .gitignore
git add .gitignore
git commit -m "chore: gitignore generated cache dirs"
```

### Root Cause Discipline

If a cache dir keeps reappearing despite being gitignored: the developer is running
tools from inside a directory that doesn't have a `.gitignore` covering it. Fix the
`.gitignore` at the level where the tool runs — not just at the repo root.

---

## Change Log

| Date | Version | What changed | Why |
|---|---|---|---|
| 2026-04-27 | v1.0 | Created | Corrective action after agent created `emulation/`, `xisc-apex/`, `rmec/amendments/` instead of working in existing `devices/desktop/vm/xemu/`, `xisc/`, and root-level RMEC file |
| 2026-05-25 | v1.1 | Added Generated Cache Gate section + cache violation rows to violation table | `.pytest_cache` left on disk in ATLAS root and recurring in other repos (GENESYS, child repos). Cross-repo rule now explicit. |
