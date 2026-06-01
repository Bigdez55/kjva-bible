# audit-assess-analyze

<!-- Source: migrated from ~/.claude/skills/audit-assess-analyze/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: audit-assess-analyze -->

**Summary.** Maximum-depth audit, assessment, and analysis framework. Use when asked to: "deep dive", "audit", "analyze thoroughly", "leave no stone unturned", "deep think", "go through with a fine-tooth comb", "comprehensive analysis", "assess everything", "maximum depth", "full audit", "validate all findings", "research exhaustively", or any request for thorough investigation. This skill ensures nothing is missed, every source is cited, every claim is verified, and all findings are structured for action. Continually refined as new analysis patterns are discovered.

# Audit, Assess & Analyze — Maximum Depth Framework

**DIRECTIVE: Leave no stone unturned. Quote primary sources. Surface everything.**

Think of this skill as a forensic investigation combined with a structural
engineering inspection. A forensic investigator does not accept witness accounts
at face value — they verify against physical evidence. A structural engineer
does not glance at a building and declare it sound — they test every load-bearing
element. This skill applies that same rigor to any system, codebase, document,
or decision being examined.

---

## PHASE 1 — OBSERVE (Never proceed from memory)

Before forming any assessment, collect actual evidence.

### 1.1 Primary source inventory

For code: exact file paths, line numbers, actual output, actual test results,
actual LOC counts, actual git log.

For documents: exact titles, section numbers, verbatim quotes, dates, authors.

For systems: actual config values, actual resource utilization, actual error
logs, actual dependency versions.

### 1.2 Evidence collection commands

```bash
git log --oneline -20 main
git diff HEAD~1..HEAD
git status
make loc
make test 2>&1 | tail -20
find . -name "*.sc" | xargs wc -l | sort -n
grep -rn "TODO\|FIXME\|HACK\|XXX" src/
grep -rn "BOOTSTRAP-CRITICAL" scc/src/
grep -rn "CAP\|BUFFER\|MAX\|LIMIT" src/scc_entry.c
```

### 1.3 What to record

Quote actual output verbatim. Never paraphrase. If a test says `5 passed,
0 failed`, write `5 passed, 0 failed` — not "tests are green."

---

## PHASE 2 — ORIENT (Map findings vs reference)

### 2.1 Gap analysis

For every claimed property, verify against evidence:

```
Claim: "All tests pass"
Evidence: [actual test output]
Verdict: VERIFIED / PARTIAL / FALSE
```

### 2.2 Orphan code detection

Most commonly missed step. Green tests do NOT cover unreachable code.

```bash
grep -rn "^pub fn \|^fn " scc/src/ | cut -d: -f3 | awk '{print $3}' > /tmp/defined_fns.txt
grep -rn "(" scc/src/ | grep -v "^.*fn " | grep -oP '\b\w+\b(?=\()' | sort -u > /tmp/called_fns.txt
comm -23 <(sort /tmp/defined_fns.txt) <(sort /tmp/called_fns.txt)
```

For each orphan: intentional? type-correct for future callers? field refs
correct?

### 2.3 Cross-reference verification

For every BOOTSTRAP-CRITICAL annotated function: read the cited reference,
compare algorithm (not syntax), document any divergences.

### 2.4 Pattern recognition

Multiple findings in same file → structural issue.
Multiple findings of same type → unclear convention.
Findings clustered by author/time → something changed in that period.

---

## PHASE 3 — ASSESS (Classify and prioritize)

### 3.1 Severity

```
CRITICAL: Wrong output, incorrect behavior, blocks progress
MAJOR: Doesn't affect current correctness but will block future
MINOR: Reduces quality, doesn't block progress
INFORMATIONAL: Observation, no required action
```

### 3.2 Blast radius

```
LOCAL: One function/file
CROSS-SLICE: Affects next 1-3 commits
CROSS-STAGE: Affects multiple future stages
PROJECT-WIDE: Affects fundamental approach
```

### 3.3 Priority matrix

```
CRITICAL + any blast radius       → Fix immediately
MAJOR + CROSS-STAGE               → Fix before dependent work begins
MAJOR + CROSS-SLICE               → Fix this session
MAJOR + LOCAL                     → Fix within 2 sessions
MINOR + any                       → Document, fix when convenient
INFORMATIONAL + any               → Record in session report
```

---

## PHASE 4 — ANALYZE (Root cause, not symptoms)

### 4.1 Five whys protocol

For each CRITICAL/MAJOR finding, ask why 5 times to reach root cause.

Categories: process gap / knowledge gap / design gap / communication gap /
technical debt.

### 4.2 Binary search for isolated issues

Divide suspect area in half. Test each half. Failing half contains root cause.
Repeat until minimal reproducer found.

**Rule:** Never read all N error messages when N > 5. Find the ROOT that
generates the cascade. One root, many symptoms.

### 4.3 Semantic divergence analysis

For BOOTSTRAP-CRITICAL: compare semantics, not syntax.
- Order-sensitive: iteration order, registration order, lookup order
- State-dependent: counter init values, sentinel values, capacities
- Side-effects: error emission point, allocation sequence, default values

---

## PHASE 5 — DOCUMENT (Structured output for action)

### 5.1 Audit report format

```markdown
# Audit Report: [Subject] — [Date]

## Scope
What was audited, what was not, why.

## Evidence Collected
[Verbatim output from Phase 1]

## Findings

### CRITICAL
| ID | Location | Description | Root Cause | Action |

### MAJOR
| ID | Location | Description | Blast Radius | Action |

### MINOR
| ID | Location | Description | When to Fix |

### INFORMATIONAL
| ID | Observation | Relevance |

## Root Cause Summary
Pattern analysis. Are findings related? What systemic issue do they reveal?

## Action Plan
1. CRITICAL — must complete before [next step]
2. MAJOR — must complete before [dependent work]
3. MINOR — when convenient
4. Process improvement — add to skill or convention docs

## Verification of Prior Findings
Were findings from previous audit resolved? Quote evidence.
```

### 5.2 Citation standard

Every claim must be supported by primary source citation.

```
CORRECT:   "Function lower_match at scir_lower.c:1423 iterates left-to-right per the loop at lines 1423-1441."
INCORRECT: "The lowering iterates arms left-to-right."
```

If you cannot cite it, qualify it: "Believed to be X based on [Y], but not
directly verified."

---

## PHASE 6 — VALIDATE (Confirm before reporting)

### 6.1 Counter-hypothesis test

For every CRITICAL/MAJOR: could I be wrong? Alternative explanations?
Verified against actual source or summary?

### 6.2 Completeness check

```
□ Every file in changed set checked (not just main files)
□ Test files checked, not just source
□ Build system changes (Makefile, scripts) checked
□ Documentation accuracy vs implementation checked
□ Prior CRITICAL findings actually resolved
□ No regressions in previously passing tests
□ Capacity limits checked for ALL inputs, not just largest current
```

### 6.3 Projection check

What fails in NEXT commit if not fixed? In 3 commits? Which gate does this
block? Cost-of-fixing-now vs fixing-later?

**Rule:** Cost of a defect roughly doubles per commit until found. Fix
CRITICAL items now. Always.

---

## DOMAIN-SPECIFIC EXTENSIONS

### Compiler projects

- Iteration order matches reference?
- Sentinels exact match?
- Error code assignments match?
- Capacity ≥ 1.5× largest current input?
- Convention labels at all sites?

### Spec/governance documents

- All counts agree (keyword count = lexer = spec = tests)
- All names agree (opcode names in schema = code = docs)
- All versions agree
- No reference to non-existent commit SHA

### Research/deep-dive

Source hierarchy: PRIMARY (originals) > SECONDARY (analyses) > TERTIARY (summaries).
**Rule:** Never use tertiary to settle disputed fact. Always trace to primary.

---

## RECURSIVE APPLICATION

This skill applies to itself. Audit reports themselves get audited:
- Findings supported by primary source citations?
- Root causes verified against evidence?
- Action items specific and actionable?
- Prior findings verified resolved?

---

## CONTINUOUS REFINEMENT PROTOCOL

After every session that produces a new finding type:
1. Identify which gate/phase would have caught it
2. Add new gate OR strengthen existing
3. Add failure pattern to gate examples
4. Update version header

Version history:
  1.0.0 — Initial from SUPER C project sessions 1-24

---

## QUICK REFERENCE — WHEN TO USE WHICH PHASE

| Situation | Phases |
|-----------|--------|
| Pre-commit check | 1 (observe) + 2 (orient) + 3 (classify) |
| Follow-behind audit | All 6 phases |
| Debugging a failure | 1 + 2.2 (orphan) + 4 (root cause binary search) |
| Deep research | All 6 + domain extensions |
| Post-session retro | All 6 + 6.3 projection |
| Verifying a claim | 1 + 2.1 + 5.2 + 6.1 |

---

Current version: 1.0.0 — initial from SUPER C project sessions 1-24
Last updated: Session 24
Next refinement trigger: any finding type not caught by existing phases
