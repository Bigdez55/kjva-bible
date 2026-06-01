# Tutorial Authoring Discipline

<!-- Source: migrated from ~/.claude/skills/tutorial-authoring-discipline/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: tutorial-authoring-discipline -->

# Tutorial Authoring Discipline

A binding skill for any agent authoring or expanding content under
`docs/tutorial/` of the SUPER C project (`superc-v1/`). The tutorial
tree is the **most critical** deliverable of the project: it is the
authoritative classroom-grade text for "the last programming language
a programmer needs."

This skill exists so the user never has to manually re-litigate line
counts, depth, citation discipline, or status-tag honesty again.

---

## NON-NEGOTIABLE CONTRACT

A chapter is **not done** until every clause below is true. An agent
MUST self-check this contract before reporting completion. If a
clause cannot be satisfied honestly within the agent's budget, the
agent MUST author **fewer chapters fully** rather than many chapters
partially.

### Clause 1 — Length floor (HEURISTIC, not the requirement)

**User clarification 2026-04-28:**
> "The 500 floor is not the requirement, as long as the curricula
> is exhaustive and thorough explained and shown."

The line floors below are **diagnostic heuristics** — a chapter
substantially under floor is *probably* under-developed, but the
real requirement is **exhaustive and thorough** treatment per
Clauses 2–10. A 350-line chapter that fully satisfies Clauses
2–10 (no padding, real citations, status tags, mandatory sections,
verified file refs, Stage-1234 arc, Mathematical Foundation,
SUPER C tie-in to named real-world systems) is **acceptable and
preferred** over a 600-line chapter that pads to hit a number.

Reference floors (a chapter at or above is unlikely to be
under-developed):

| Volume | Floor (heuristic) | Ceiling |
|---|---|---|
| Volume I (Foundations tutorial 00–09) | 300 | 800 |
| Volume II Domain Applications | 400 | 900 |
| Volume II Extended Applications | 350 | 800 |
| Data subseries | 400 | 900 |
| Parallel subseries | 350 | 900 |
| Volume III CS Foundations | 400 | 900 |
| Volume IV Scholarly | 500 | 1000 |
| Volume V Sciences | 500 | 1000 |
| Volume VI Failure Modes | 400 | 900 |
| README / index files | 150 | 600 |
| Pilot exemplar chapters | 600 | 1000 |

**Real test (apply to every chapter):**
- Are all four arc stages (Concept → Ideation → Realization →
  Applied) substantively developed? (Clause 10)
- Is the Mathematical Foundation present and useful? (Clause 9)
- Are all code examples status-tagged ✅/🟡/🔭? (Clause 4)
- Are 3+ worked examples present, with at least one ✅ when the
  topic admits one?
- Are 4–8 real Author (Year) citations present? (Clause 3)
- Are file refs to `superc-v1/` paths verified on disk? (Clause 6)
- Are the mandatory sections from Clause 5 present?
- Are the exercises and discussion questions present and graded?
- Is the SUPER C tie-in masterful, not perfunctory? (Clause 10)
- Are real, named real-world systems cited in Stage 4?

A chapter is "complete" when **every test above passes**, not when
it hits a line count. Line counts that are far below the heuristic
floor (e.g., a Volume V chapter at 200 lines) are nearly always a
sign that one or more tests above is failing. A chapter at 380
lines that passes all tests is done.

A chapter that passes all tests and is short because the topic
genuinely admits no more depth (e.g., a brief preface, a one-page
glossary entry) is **acceptable** and the agent should document
the cap honestly per Clause 8.

### Clause 2 — No padding

Padding patterns are forbidden:
- Repeating the same point under different headers
- Filler prose ("In conclusion, this chapter discussed...")
- Restating the abstract at the end
- Bulleted re-summaries of preceding paragraphs
- Verbose code comments that restate code

Depth comes from **more substance**: more worked examples, more
tradeoff tables, more cross-references, more graded exercises, more
literature citations, more design-decision walkthroughs, more
real-world case data.

### Clause 3 — Real citations only

Every Author (Year) reference must be a real publication. If the
agent is not confident a work exists, mark `[CITATION NEEDED — see
canonical X literature]` and continue. NEVER invent. Fabricated
citations are a project-poisoning failure mode.

Confirmed citation reservoirs the agent should use first:
- Knuth, TAOCP (1968–2011, multiple volumes)
- Cormen, Leiserson, Rivest, Stein (2009) Introduction to Algorithms
- Hennessy & Patterson (2017) Computer Architecture
- Tanenbaum & Bos (2014) Modern Operating Systems
- Aho, Lam, Sethi, Ullman (2006) Compilers: Principles, Techniques, Tools
- Pierce (2002) Types and Programming Languages
- Nielsen & Chuang (2010) Quantum Computation and Quantum Information
- Hardy & Wright (1979) An Introduction to the Theory of Numbers
- Mac Lane (1998) Categories for the Working Mathematician
- Boyd & Vandenberghe (2004) Convex Optimization
- Hoare (1978) "Communicating Sequential Processes"
- Lamport (1978) "Time, Clocks, and the Ordering of Events"
- Thompson (1984) "Reflections on Trusting Trust"
- Avizienis et al. (2004) "Basic Concepts and Taxonomy of Dependable and Secure Computing"
- Yang et al. (2011) "Finding and Understanding Bugs in C Compilers"

This is a starting set. Use what you actually know.

### Clause 4 — Status tags on every example

Every code block in a chapter must be tagged one of:
- ✅ **WORKS TODAY** — runs under current scc (refer to
  `compiler/scc/tests/sc_demos/`); only const-evaluable integer
  subset works today (let, arithmetic, fn calls, params, lazy
  `cond(c,t,e)`, recursion, comparison ops, full u32 + 64-bit
  returns via slice 5z)
- 🟡 **SPEC-LOCKED** — language design + canonical lock doc exists;
  codegen pending. Cite the lock doc.
- 🔭 **DESIGN HORIZON** — outlined in the spec roadmap; design-stage
  only. Be honest.

A chapter MUST have at least one ✅ WORKS TODAY example where the
topic admits one. If the topic genuinely doesn't admit one (e.g.
quantum measurement on physical hardware), say so explicitly.

### Clause 5 — Mandatory sections

Every chapter MUST contain:
1. **Title + tier breadcrumb** (e.g. "Volume IV — Scholarly · PHY03")
2. **Abstract** (3–5 sentences, scholar-grade)
3. **Literature framing** with real citations
4. **Connection to SUPER C** with concrete file references
   (`compiler/scc/...`, `std/.../*.sc.md`, etc.)
5. **Worked artifacts** — code/tables/diagrams, status-tagged
6. **SLP triad** (Volumes IV/V/VI) — Scholar / Learner / Practitioner
   reflections, 3 substantive paragraphs each (compress to 2 only
   under explicit budget pressure)
7. **Discussion questions** — 4 graded by depth (Volumes IV/V/VI),
   3 graded for Volumes I–III
8. **Exercises** — 3 graded difficulty (beginner / intermediate /
   advanced); 5 for data subseries chapters
9. **Cross-references** — to dictionary, thesaurus, glossary,
   sibling chapters, and applicable lock docs
10. **References** — proper Author (Year), Title, Venue/Publisher

### Clause 6 — No fabricated file refs

Every cited file path must exist in `superc-v1/`. Verify with Read
or Glob before referencing. If a file is canonical-spec-only (not
on disk), tag the reference as `🟡 SPEC-LOCKED · canon-only`.

### Clause 7 — Cross-volume crosswalk

Every chapter must include explicit cross-references to related
chapters in other volumes. If material would duplicate a sibling
chapter, link to it instead of repeating.

### Clause 8 — Honesty over completeness

If you cannot meet a clause within budget, **say so explicitly in
your report** and finish fewer chapters fully. The user's standing
directive: "DO NOT CUT CORNERS OR SHORTEN TEXT." A short chapter
that meets the contract is acceptable; a long chapter that pads to
hit a line count is a contract violation.

**User clarification 2026-04-28:**
> "No need to push unnecessarily if it is not a real improvement."

This is a binding companion to Clause 1's "exhaustive + thorough"
test. If a chapter already passes the 10 real tests in Clause 1,
**do not edit it** just to add words. Editing for the sake of
editing is a contract violation equal to padding. The agent's
report must distinguish:

- **Touched (real improvement):** chapter genuinely advanced —
  added a missing stage, fixed a bad citation, replaced a 🟡 with
  a verified ✅, added a missing Mathematical Foundation, replaced
  a perfunctory cross-link with a substantive one.
- **Audited and left alone (no real improvement available):**
  chapter already passes the 10 tests; no edit was made; reason
  documented (e.g. "PSY03 already has Stage-1234 arc, Mathematical
  Foundation, 6 real citations, 3 ✅ examples, full SLP triad —
  no improvement available within budget").
- **Deferred (real improvement available but not in budget):**
  chapter has a known gap; agent ran out of budget before
  addressing it.

The middle category — "audited and left alone" — is a legitimate
deliverable. Agents must report it explicitly so the project knows
which chapters are actually done.

### Clause 9 — Mathematical Foundation (mandatory in every chapter)

**Mathematical rationale (user directive 2026-04-28):**
> "Math is the building block of the sciences. Space travel is a
> theory, until you can mathematically figure out how to get there.
> An engine or electric motor is an idea until you can
> mathematically figure out how to build it."

Every tutorial chapter — across **all volumes**, including Volume I
foundational tutorial, Volume II Applications (domain + extended +
data + parallel), Volume III CS Foundations, Volume IV Scholarly,
Volume V Sciences, Volume VI Failure Modes, the README files, and
the front-door `00_preface.md` — MUST include a section titled
**"Mathematical Foundation"** that exposes the mathematics that
makes the chapter's subject computable, simulable, or buildable in
SUPER C.

#### Section structure (MANDATORY)

Heading: `## Mathematical Foundation`

Inside, in order:

1. **Core formalism** — the equations, axioms, theorems, or
   structures that govern the chapter's topic. State them in proper
   mathematical notation (LaTeX-style inline acceptable in markdown:
   `$f(x) = ...$` or display blocks).
2. **Why it matters here** — 2–3 sentences mapping the math to the
   chapter's subject (e.g., "Without Maxwell's equations there is
   no signal propagation; without them this codec has nothing to
   encode").
3. **Computational form** — how the math becomes code: integer
   discretization, floating-point pitfalls, recursive formulation,
   matrix layout, or — for ✅ WORKS TODAY — a recursive numeric
   kernel that runs under current scc and demonstrates a real
   sub-result of the math.
4. **Cross-link to MATH/PHY/foundations** — every Mathematical
   Foundation section MUST link to at least one chapter in:
   - `docs/tutorial/scholarly/sciences/MATH*.md`
   - `docs/tutorial/foundations/M*.md` or `T*.md`
   - `docs/tutorial/scholarly/PHY*.md` (for physics-adjacent topics)
   The link must resolve (Clause 6).
5. **Real citation** — at least one Author (Year) reference for the
   math invoked, drawn from the citation reservoir in Clause 3 or
   from a verifiable canonical work.

#### Examples (skill-internal guidance, not exhaustive)

| Chapter topic | Example mathematical foundation |
|---|---|
| Game development | Fixed-timestep integration: `x(t+Δt) = x(t) + v(t)Δt + ½a(t)Δt²` (Verlet 1967); link to `MATH06_calculus_real_analysis.md` and `PHY01_classical_mechanics_simulations.md` |
| Backend servers | Queueing theory: M/M/1 utilization `ρ = λ/μ`, Little's law `L = λW` (Little 1961); link to `MATH11_probability_measure_theory.md` |
| Compilers | Context-free grammars + Pratt precedence; link to `T02_theory_of_computation.md` and `MATH04_discrete_mathematics.md` |
| Cryptography | Modular arithmetic, RSA: `c = m^e mod n` (Rivest-Shamir-Adleman 1978); link to `MATH02_number_theory.md` |
| Concurrency | Happens-before partial order (Lamport 1978); link to `MATH04_discrete_mathematics.md` |
| Quantum computing | Hilbert space `H = ℂ^7`, unitary evolution `U†U = I`; link to `MATH08_abstract_algebra.md` and `PHY04_quantum_mechanics_foundations.md` |
| AI/ML | Gradient descent: `θ_{t+1} = θ_t − η∇L(θ_t)`; link to `MATH13_optimization_theory.md` |
| Networking | Shannon channel capacity `C = B log₂(1+S/N)` (Shannon 1948); link to `MATH16_mathematical_logic_and_proof_assistants.md` and `T08_information_theory.md` |
| Storage engines | LSM amortized cost analysis; link to `MATH03_combinatorics.md` and `A01_asymptotics_and_analysis.md` |
| Front-door tutorials (Vol I) | Even `01_hello_universe` deserves a footnote: integers as `ℤ`, the i32 type as `ℤ ∩ [-2^31, 2^31)`; link to `MATH01_foundations_set_theory_logic.md` |

For chapters where the math is genuinely minimal (e.g., classroom
curriculum, instructor guide, capstone briefs), the section may
be brief but MUST exist and MUST link to the relevant MATH/T/M
chapter. NEVER omit the section.

#### Enforcement

- Every deepening pass MUST add or expand this section in every
  chapter touched. A chapter without `## Mathematical Foundation`
  is a Clause 9 violation regardless of line count.
- Audits (per `audit-assess-analyze` skill + this skill's loop)
  MUST count Clause-9 compliance per chapter and report it.
- For chapters that resist mathematical exposition (rare), document
  the cap honestly per Clause 8 — but include the section heading
  with a 1–2 sentence honest note, not absence.

### Clause 10 — SUPER C Is the Spine (binding for ALL chapters)

**User directive 2026-04-28:**
> "This is not a math book. Everything is as it relates to SUPER C.
> Do not forget that; that should be at the forefront of all you are
> doing right now. The tie-in should be masterfully crafted and
> structured through the stages of concepts and ideation to
> practical, applied applications that we know and use today."

The tutorial is a **SUPER C textbook**. Math, physics, biology,
psychology, sociology, history, every discipline — they appear in
this tutorial only as **scaffolding for understanding SUPER C**.
Topics that cannot be tied back to SUPER C language design,
compiler internals, stdlib API, sovereignty/linear types, fibers/
realms/channels, quantum d=7, sc tooling, or applied programming
patterns must either be **tied in or removed**. There is no
"general interest" content allowed.

#### The four-stage spine (MANDATORY in every chapter)

Every chapter MUST follow this dramatic arc explicitly. The
sections may carry domain-specific names but must hit all four
stages in this order:

1. **Concept** — What is this idea? (Math, theorem, principle,
   physical law, biological process, etc.) Stated cleanly without
   yet invoking SUPER C.
2. **Ideation** — Why does this idea matter for *programming*, for
   *language design*, for *what a compiler/runtime/stdlib must do*?
   This is the bridge from pure idea to its computational shadow.
3. **SUPER C realization** — How does SUPER C express, encode, or
   enforce this idea? Specific features cited:
   - **Language**: linear types, sovereignty, lazy `cond`, fibers,
     realms, channels, `mint`, domain gates, quantum types.
   - **Compiler**: lex → parse → sema → SCIR-Low → codegen pipeline,
     `sciv-lint`, bootstrap closure, JIT.
   - **Stdlib**: cite the exact `std/<tier>/<module>.sc.md` design
     doc.
   - **Tooling**: `scc walk`, `scc emit-direct`, `scc run-jit`,
     `scc-fmt`, `scc-doc`, `scc-pack`, `scc-bench`, `scc-test`.
4. **Applied** — Where do we see this in the wild today? Tie to
   things programmers actually use: web servers, browsers, payment
   systems, video codecs, ML pipelines, OS kernels, blockchain,
   game engines, embedded firmware, quantum hardware. Every chapter
   ends in a concrete, named real-world artifact (with citation if
   applicable) that the SUPER C realization reaches.

A chapter that delivers stages 1, 3, 4 but skips stage 2 is **not
masterfully crafted** — the bridge is what makes the textbook
cohere. A chapter that skips stage 4 is academic vapor; the user
explicitly forbids that. A chapter that skips stage 3 is off-topic;
remove or rewrite.

#### Practical templates (skill-internal guidance)

| Volume | Stage 1 → 2 → 3 → 4 example for one chapter |
|---|---|
| Vol V MATH02 (Number theory) | Modular arithmetic + RSA → primes power asymmetric crypto → SC's `mint` blocks + `Counted<T>` + `gcd ✅` in `tests/sc_demos/13_gcd.sc` → TLS handshakes, Bitcoin signatures, sovereign signing per `release/SIGNING.md` |
| Vol IV PHY01 (Classical mechanics) | Newton's `F=ma` + Verlet integration → fixed-timestep deterministic sim → SC fiber-per-entity + `cond` ✅ tick logic → game engines (Unity/Unreal physics), MuJoCo robotics, KSP orbital mechanics |
| Vol II app/16 (Concurrency) | Happens-before + linearizability → race-prevention via type system → SC linear types + channel/realm primitives → Kafka log ordering, Postgres MVCC, Erlang OTP |
| Vol III S03 (Compilers) | CFG + Pratt precedence → parse-tree → AST mapping → SC's actual `frontend/src/parser.sc` + `OPERATOR_PRECEDENCE_LOCK.md` → all compilers built on this lineage (gcc, rustc, scc itself) |
| Vol VI DBG10 (Self-host) | Trusting Trust + bootstrap closure → byte-identity proof → SC's `make test-bootstrap` G6 gate ✅ → defensive verification of *every* compiler the world uses |

Note how every example collapses the math/theory/principle into
**a concrete SUPER C file or feature** before reaching applied.
That collapse is what "masterfully crafted tie-in" means.

#### Enforcement

- Audits MUST verify all four stages are present and labeled.
- A chapter where stage 3 (SUPER C realization) does not cite a
  concrete file path or feature in `superc-v1/` is a Clause 10
  violation.
- A chapter whose stage 4 (Applied) names only invented or
  hypothetical products is a Clause 10 violation. Use real, named
  systems that exist today.
- Chapters in Volume V Sciences and Volume IV Scholarly are NOT
  exempt — they have the heaviest math/discipline content but the
  TIGHTEST SUPER C tie-in requirement, because that's where readers
  are most at risk of forgetting they are reading a SUPER C book.

---

## CONTINUOUS REFINEMENT LOOP

This skill is self-improving. Every agent that authors or expands
tutorial content MUST:

1. **Read** this skill before starting.
2. **Audit** any chapters they touch against Clauses 1–8.
3. **Expand** any under-floor chapter they encounter (deepen, not
   pad). If they cannot expand it within budget, surface it in
   their report with a one-line "needs expansion: X lines, reason Y."
4. **Improve** this skill if they identify a missing clause or a
   pattern that should be banned. Edit `~/.claude/skills/
   tutorial-authoring-discipline/SKILL.md` directly. Add a
   `## Skill revisions` entry at the bottom with date + change +
   reason. Never delete prior revisions.
5. **Surface** any chapter that violates Clauses 3 or 6 (fabricated
   citations or file refs) immediately as a CRITICAL finding.

---

## OODA APPLICATION

When invoked alongside `apex-parallel-deploy` / `verify-validate` /
`audit-assess-analyze` / `apex-directory-discipline`:

- **Observe**: list every chapter in the relevant volume, line count
  per chapter, citation density per chapter.
- **Orient**: classify each as ABOVE-FLOOR / UNDER-FLOOR / VIOLATION
  per Clause 1.
- **Decide**: pick the highest-leverage UNDER-FLOOR cluster within
  budget. Prefer deepening 5 chapters fully over touching 30
  shallowly.
- **Act**: deepen via the patterns in Clause 2's "depth comes from"
  list. Re-audit after.

---

## PARALLEL DEPLOYMENT

When dispatching multiple agents to author tutorial content:

1. Assign each agent a **specific, named chapter set** (not a tier).
2. Give each agent the **explicit length floor** for their volume.
3. Mandate they **re-read this skill** at start of session.
4. Require their report to include **per-chapter line count**.
5. Auditor must verify Clauses 1, 3, 4, 6 on every committed chapter.

---

## SKILL REVISIONS

- 2026-04-28 (v1.0): Initial authoring after user directive
  "DO NOT CUT ANY CORNERS OR SHORTEN TEXT. ... CREATE A SKILL THAT
  CONTINUOUSLY IMPROVES AND REFINED." Codified Clauses 1–8, OODA
  application, parallel-deployment protocol, self-improvement loop.
- 2026-04-28 (v1.1): Added Clause 9 — Mathematical Foundation
  mandatory section in every chapter, after user directive "math
  is the building block of the sciences." Added MSC2020 alignment
  guidance for Volume V.
- 2026-04-28 (v1.2): Added Clause 10 — SUPER C Is the Spine. Four-
  stage arc (Concept → Ideation → SUPER C realization → Applied)
  binding for ALL chapters, after user directive "this is not a
  math book — everything is as it relates to SUPER C." Stage 4 must
  name real production systems.
- 2026-04-28 (v1.3): Clause 1 length floor downgraded from HARD to
  HEURISTIC after user clarification "the 500 floor is not the
  requirement, as long as the curricula is exhaustive and thorough
  explained and shown." Added 10-test "real test" enumeration as
  the actual completeness gate.
- 2026-04-28 (v1.4): Clause 8 extended with Touched / Audited-and-
  left-alone / Deferred classification after user directive "no
  need to push unnecessarily if it is not a real improvement."
  Editing for the sake of editing now equals padding as a contract
  violation.
- 2026-05-04 (v1.5): Added Clauses C-15 through C-21 — executable
  floor, anti-passive-voice, proximity-isolation, phantom-stdlib
  lint, status-drift PR check, displacement clauses, quarterly
  integrity report. Codified the **lift-only, no-demote** status-tag
  transition rule (per user directive 2026-05-03). Codified the
  **displacement thesis**: SC has no weaknesses by design — Volume
  IX comparison chapters articulate decisive superiority with
  empirical evidence, not humility framing. Locked the artifact
  scope: all `.claude/` artifacts live at the repo-root `.claude/`
  (consolidated 2026-05-13), never `~/.claude/` and never nested
  in subdirectories such as `superc-v1/.claude/`.

---

## CLAUSE C-15 — Executable Floor

Every snippet bearing the ✅ tag MUST have a corresponding test
program at `tests/curriculum/<volume>/<chapter>/<id>.sc` that
compiles in CI. CI failure on that test program **auto-demotes
the snippet to 🟡** until the test passes again. No ✅ may exist
without an executable witness on disk.

## CLAUSE C-16 — Anti-Passive-Voice in Capability Claims

The phrases "will dispatch", "would invoke", "shall route", and
their grammatical kin are **forbidden** in capability claims.
Future-tense, conditional, and modal hedges hide whether a
capability exists today. Replace with a bracketed status tag:

- `[🔭 design]` — designed, not implemented
- `[🟡 spec]`   — specified, partially implemented
- `[✅ live]`   — implemented, executable witness present

Plain present tense ("dispatches", "invokes", "routes") is reserved
for ✅ live capabilities only.

## CLAUSE C-17 — Proximity Isolation

A ✅ block that shares an identifier (function name, type name,
module path) with a 🟡 block in the same chapter MUST either:

1. Declare an explicit dependency note pointing to the 🟡 block, or
2. Downgrade to 🟡 itself.

Status-tag contagion via shared identity is the default. Silent
adjacency that implies the 🟡 piece "just works" is a violation.

## CLAUSE C-18 — Phantom-Stdlib Lint

Any `.method()` call invoked on a value whose type comes from a
🟡-tagged stdlib module MUST be flagged. Twelve known instances
exist as of v1.5; the lint runs CI-side and grows as the stdlib
matures. A phantom call is a 🟡-or-worse claim wearing a ✅ mask
and is treated as a contract violation per Clause 6.

## CLAUSE C-19 — Status-Drift PR Check

Every promotion of a snippet from 🟡 to ✅ in a pull request MUST
link the test program (Clause C-15 path) in the PR body. Promotions
without a linked, passing test program are blocked at review.
Drift in the other direction (✅ silently downgraded) is also
blocked — but only the lift direction is allowed in steady state
per the **lift-only, no-demote** transition rule (see below).

## CLAUSE C-20 — Displacement Clauses in Volume IX

Every comparison chapter in Volume IX (SC vs. C, SC vs. Rust,
SC vs. Python, SC vs. Zig, SC vs. assembly, etc.) MUST articulate
where SUPER C's design is **decisively superior** to the
comparator, backed by empirical evidence (benchmark numbers,
binary sizes, line counts, defect classes eliminated).

This is **displacement framing, not humility framing**. Phrases
like "of course, C still wins on X" or "SC trades away Y" are
forbidden unless followed by an explicit superiority clause that
overturns the framing. SC has no weaknesses by design (see the
displacement thesis section below); comparison chapters must
reflect that posture honestly and with evidence.

## CLAUSE C-21 — Quarterly Integrity Report

An automated audit runs every quarter and produces an integrity
score across all volumes (ratio of ✅ snippets with passing
witnesses to total ✅ claims, plus phantom-stdlib counts, plus
passive-voice counts). A sustained drop greater than **0.05**
between quarters triggers a **retrofit wave**: a dedicated agent
sweep that re-validates flagged content before any new authoring
proceeds.

---

## STATUS-TAG TRANSITION RULE — LIFT ONLY, NO DEMOTE

Per user directive 2026-05-03: in steady-state authoring, the
only permitted status-tag transition is **upward** — 🔭 → 🟡 → ✅.
Demotion is reserved for the automated mechanisms in Clauses
C-15 (CI failure) and C-18 (phantom-stdlib lint). Authors and
auditors do not manually demote; they fix forward. This preserves
the curriculum's monotone progress invariant and prevents
demotion-as-procrastination.

## DISPLACEMENT THESIS — SC HAS NO WEAKNESSES BY DESIGN

SUPER C is not a compromise language. It is the substrate of
GEN.OS, designed from sovereignty-first principles to be
measurably superior on every axis that matters: performance,
binary size, simplicity, safety, originality, and substrate
control. The tutorial's comparison chapters (Volume IX) and
every Stage 4 "Applied" section MUST reflect this posture.
Where a comparator appears stronger on a narrow metric, the
chapter MUST identify the SC design choice that makes that
metric irrelevant or that wins on a deeper metric. Humility
framing about SC trade-offs is a Clause 6 violation.

## ARTIFACT SCOPE LOCK

All `.claude/` artifacts for this project — skills, plans,
agent memory, settings — live at the **repo-root `.claude/`**
(consolidated 2026-05-13; nested `.claude/` subfolders are
warded by `.gitignore`). They do **NOT** live at `~/.claude/`,
and they do **NOT** live at `superc-v1/.claude/` or any other
nested location. Authors editing this skill, adding sibling
skills, or wiring hooks must target the repo-root path.
Cross-contamination with the user-global `~/.claude/` tree
is forbidden without explicit per-request permission.
