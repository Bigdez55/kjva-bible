# Compiler Discipline

<!-- Source: migrated from ~/.claude/skills/compiler-discipline/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: compiler-discipline -->

# compiler-discipline

Empirical discipline for evolving the SUPER C v1 self-hosted compiler (seedc → scc) without breaking bootstrap. Codifies lessons from Stage I (slices 1–5z) and the STOP-6 codegen audits.

Scope: `superc-v1/` tree only. Authority: project memory `project_superc_v1_authorized_scope.md` + audits under `audits/`.

Trigger: invoke before ANY change to `frontend/src/*.sc`, `compiler/scc/src/*.sc`, `compiler/scc/src/*.c`, SCIR opcode tables, or codegen byte-emission paths.

---

## 1. Convention 9: enum-tail-append

**Rule.** Every new variant added to `TokenKind`, `AstKind`, or SCIR opcode enums MUST be appended AFTER the last existing variant. No mid-enum insertion. Ever.

**Why.** Discriminants are positional integers. Parsers, sema walkers, and codegen dispatch tables across the seedc/scc bootstrap chain use hardcoded `k == N` checks (and switch arms keyed on literal integers). Inserting a variant mid-enum shifts every subsequent discriminant by +1, silently miscompiling every downstream consumer.

**Citation.** Slice 1 reclassification — commit `0a06e6f`. The naive insertion of a new TokenKind variant in the middle of the enum block flipped 6 downstream `k == N` checks in `parser.sc` and produced a green-but-wrong scc that emitted reordered opcodes. Lesson: append-only.

**Enforcement.** During code review, diff the enum block. If any line above the new variant moved, REJECT and re-author at tail.

---

## 2. Bootstrap-safety class taxonomy

Classify every change BEFORE editing. Pick the strictest matching class.

### SAFE
- Token-only additions AT END of enum.
- AST-additive variants AT END, with no sema/lower consumer yet.
- New helper functions not yet called from existing demo paths.
- **Verification:** `make test-bootstrap` post-build. Single green run sufficient.

### CAUTIOUS
- New sema walker for a new AST kind that EXECUTES on existing demo paths.
- Lowering additions touching shared IR builders.
- New parser productions reachable from existing source.
- **Verification:** Pre-change G6 sha snapshot. Post-change G6 sha snapshot. Squash-merge only after BOTH sha sets are green and DDC re-passes.

### HIGH-RISK
- Codegen byte-output changes (any opcode emission, any RA tweak).
- Emit-fork retire / unify operations.
- Register allocator changes.
- Calling-convention adjustments (>32-bit return paths, spill changes).
- **Verification:** STOP-6 protocol — G6 sha + DDC v2 + dual-build (seedc-built scc vs scc-built scc) + per-demo byte-identity diff + smoke suite + `ret64` regression. ALL green or revert.

### BOOTSTRAP-CRITICAL
- Any change to parser/sema where existing scc source paths execute under the new code.
- Any new keyword OR identifier promotion.
- **Verification:** Identifier-collision pre-check (Section 3) MANDATORY. Then HIGH-RISK protocol applies on top.

---

## 3. Identifier-collision pre-check protocol

Before adding any new keyword to the lexer, run:

```sh
grep -rwE "\b<keyword>\b" frontend/src/*.sc compiler/scc/src/*.{sc,c}
```

**Decision rule:**
- **Zero matches** → SAFE to promote to keyword. Proceed.
- **Any matches** → HIGH-RISK. The keyword collides with an existing identifier in scc source. **Rename the colliding identifiers in scc source FIRST**, in a separate squash-merged change, with full G6 + DDC pass. Only after the source is collision-free may the keyword be added.

Never add a keyword and rename in the same commit. The rename must land and stabilize first.

---

## 4. Discriminant audit protocol

Before merging any new TokenKind/AstKind variant, verify discriminants `0..N` for prior variants are unchanged.

```sh
grep -n "k == [0-9]" frontend/src/parser.sc | wc -l
```

The count MUST be identical pre- and post-change. If it differs, a `k == N` check was added/removed/shifted — halt and audit. Additions of new `k == N` checks for the new variant are allowed ONLY at tail discriminant; they must reference the highest integer present.

Cross-check: same grep against `compiler/scc/src/*.sc` for sema/lower dispatch.

---

## 5. The 6 seedc bug catalog reference

Authoritative list: `audits/codegen_silent_drop_finding.md`.

Every new compiler change MUST be cross-checked against the 4 active workarounds:
- **Bug 2** — silent drop on certain expression forms; workaround active in lowering.
- **Bug 3** — calling-convention return-slot edge case.
- **Bug 4** — discriminant compare miscompile under specific seedc opt path.
- **Bug 6** — emit-fork divergence on nested control flow.

Bugs 1 and 5 are closed. Do not regress workarounds. If a change appears to make a workaround unnecessary, do NOT remove it in the same change — file a follow-up slice with explicit DDC v2 + STOP-6 evidence.

---

## 6. v1.0.1 out-of-scope items + status mapping

The four deferred items from the v1.0.1 charter:

| # | Item | Status | Stage |
|---|------|--------|-------|
| 1 | Native if/else/while in scc | PARTIAL — slice 2 in flight | Stage I |
| 2 | Strings, arrays, structs | DEFERRED | Stage III |
| 3 | >32-bit return values | DONE — slice 5z landed | Stage I (closed) |
| 4 | scc emit-fork unification | DEFERRED | Stage II |

Any work touching these areas must reference this table and the corresponding slice/stage. Do not silently expand scope.

---

## 7. Stage gate map (G1–G18)

Preconditions are strict; a gate cannot open until ALL upstream gates are green and all artifacts are squash-merged.

- **Stage I (Stage I closes at G14):** G1 lexer parity → G2 parser parity → G3 AST schema lock → G4 sema parity → G5 lower parity → G6 codegen byte-identity baseline → G7 DDC v1 → G8 dual-build → G9 ret64 regression → G10 emit-fork audit → G11 slice 1 reclassification (`0a06e6f`) → G12 slice 2 native control flow → G13 slice 5z >32-bit returns → G14 Stage I close (per `audits/STAGE_I_PROGRESS_2026-05-04.md`).
- **Stage II (closes at G15):** G15 = scc emit-fork unification. **G15 closes Stage II, not Stage I.** This is the most common misread; the audit STAGE_I_PROGRESS_2026-05-04.md is explicit.
- **Stage III:** G16 strings → G17 arrays → G18 structs.

No gate may be skipped. No gate may close on a yellow CI.

---

## 8. SUPER C v1 / scc Compiler Empirical Patterns

Codified from v31.4 / v31.5 ARM64 backend cycles. These are mechanical patterns — get them wrong and you waste diagnostic cycles or ship broken state. See also: `apex-verified-machine-encoding` for the byte-level encoding discipline that pairs with these flow patterns.

### 9.1 `emit-direct` invocation requires `-o <out>`

**Rule.** Running `compiler/scc/build/scc emit-direct --target=macho-arm64 <file>` without `-o` returns the usage hint, NOT the compile. The full canonical form is:

```sh
compiler/scc/build/scc emit-direct [--fold-main] [--emit-debug] [--target=macho-arm64] <file> -o <out>
```

**Why.** scc treats missing `-o` as "user did not actually request emission" and prints usage. A green-looking session that produced no artifact is a wasted diagnostic cycle. Always pass `-o` explicitly, even when scripting against `/tmp`.

### 9.2 `SCC_O1=1 SCC_O1_DUMP=1` is the canonical SHIRL probe

**Rule.** To inspect SHIRL inst arrays before/after any lowering/codegen fix:

```sh
SCC_O1=1 SCC_O1_DUMP=1 compiler/scc/build/scc emit-direct --target=macho-arm64 probe.sc -o /tmp/probe.out
```

This is the empirical primary source for what the IR actually looks like. Never reason about SHIRL shape from source-reading alone — dump it.

**Opcode decoding cheat-sheet** (current as of v31.5.A):

| op | name | key fields |
|----|------|------------|
| 30 | `SHIRL_LOAD_32` | `op_base` indexes operand_pool |
| 34 | `SHIRL_STORE_32` | |
| 36 | `SHIRL_STACK_ALLOC` | `const_lo` = byte size |
| 46/47/48 | block markers / branch / jump | |
| 50 | `SHIRL_RET` | |
| 51 | `SHIRL_PARAM` | |

**Diagnostic heuristic.** A function with NO `op=50` in its dump almost certainly has a missing-RET emit bug. This is the first thing to check when a function silently returns garbage.

For byte-level emit-constant verification (the layer below SHIRL), defer to `apex-verified-machine-encoding`.

### 9.3 Wave-Sequencing Contract — preserve invariants

**Rule.** Two empirical gates MUST hold byte-identical pre-and-post every compiler-source patch:

- `scc_smoke` — **127/0** PASS, run from `compiler/scc/`.
- `gold_gate` — **21/0** PASS, run from `superc-v1/`.

If a patch breaks either gate, the Wave-Sequencing Contract requires **safe-revert** of the patch and a fresh re-design. Do NOT ship broken state forward "to fix in the next commit."

**Why.** This is the discipline that prevented every v31.4 cycle from shipping breakage. v31.4.A1, v31.4.A4, and v31.4.A4_REAL were all safe-reverted under this contract; the working baselines (v31.4.A1D, v31.4.A3) landed only when both gates held. Carrying broken state forward in a self-hosted compiler chain corrupts every downstream diagnostic.

### 9.4 seedc 8-param hard cap at helper-extraction layer

**Rule.** Any newly extracted helper in seedc-lowered SC code that takes **more than 8 params silently aborts** at the codegen layer. There is no compile-time error; the function never runs.

**Mitigation.** Bundle related fields into a param struct, then pass the struct. Example: `emit_arith_fully_pooled` in v31.4.A4D-FIX hits exactly 8 params after consolidation.

**Citation.** Cross-references project memory entries `feedback_seedc_caps_known.md` (8-param hard abort at codegen_aarch64.c:1257-1258) and the v31.4.A4D-FIX implementation.

### 9.5 DEF-v21-SLICE5F-001 — `arenas.operands_len` inline-capture miscompile

**Rule.** seedc miscompiles the pattern:

```text
let bin_op_base = arenas.operands_len   // captured INLINE inside kind_binary path
// ... later operand_pool pushes ...
inst.op_base = bin_op_base              // ALWAYS reads 0, not the captured value
```

The "capture before mutation" idiom does not work under seedc's current lowering of `kind_binary`. The captured value is folded to 0.

**Mitigation.** Use a **fully-pooled helper** that receives the base index as an explicit param BEFORE any operand_pool mutation. Reference implementation: `lower_walker.sc::emit_arith_fully_pooled` (landed in v31.4.A4D-FIX at +199/-48 LOC).

**Symptom this catches.** 3+operand arithmetic chains (e.g. `1+2+3`) returning wrong values because every chained ADD shares `operands_base=0` and overwrites earlier insts' lazy-unpacked `.operand0`/`.operand1`.

### 8.6 Helper Extraction Mandate Under Register Pressure (sharpened)

**Quantified empirical anchor**: Inline addition of ≥3 locals to a register-pressured SC function has produced up to **450× runtime slowdown** (DEF-v21-SLICE5F-001 family).

#### Concrete case study — v31.5.I.F1.a first attempt

Author added 5 inline locals into lower_walker.sc's StmtLet handler:
```sc
let struct_size_mask: u32     = 1073741824 as u32;
let struct_size_mask_lo: u32  = 1073741823 as u32;
let mut alloc_bytes: u32 = 4 as u32;
let mut is_struct_alloc: u32 = 0 as u32;
if (st.a & struct_size_mask) != (0 as u32) {
    alloc_bytes = st.a & struct_size_mask_lo;
    is_struct_alloc = 1 as u32;
}
```

Result: sha256_kat runtime jumped from 0.4s to 3+ minutes (>450× slowdown). seedc miscompiled an inline `arenas.operands_len` capture in the SAME function to always-0, clobbering operand_pool entries on every STORE_32 emit, causing infinite loop in SHA-256 round chaining.

#### MANDATORY mitigation pattern

1. **Audit register pressure BEFORE adding ANY local** to a function with ≥6 live locals.
2. **Extract logic into a fully-pooled helper** modeled on `emit_arith_fully_pooled` (lower_walker.sc:383-405). Helper template:
   - 8-param maximum (seedc cap)
   - All field reads to locals UP FRONT before any mutating call
   - operand_pool reservation inside helper
   - Single emit_inst call
   - Inst field assignments after emit
3. **Verify with timed gate run** post-change. Compare sha256_kat (or equivalent compute-heavy runtime test) wall time pre/post. If slowdown > 2x, helper extraction is insufficient — investigate deeper.

#### Fix that worked

`lower_decode_struct_alloc(lctx, st_a) -> u32` helper (compiler/scc/src/lower_walker.sc:418) — 2 params, fresh register budget, returns alloc_bytes. Caller now has only ONE new local (`struct_bytes`). sha256_kat returned to 0.34s parity.

#### Project-agnostic frame
On any register-pressured target (ARM64, RV32, embedded), any addition of locals to a hot function MUST be preceded by a register-pressure audit and may require helper extraction. The cost of a wrong call here is exponential, not linear.

#### Cross-references
- `apex-verified-machine-encoding` — calling-convention discipline
- `sc-field-lowering-discipline` — where this pattern most commonly bites in SC
- `sc-empirical-surface-probe` — timed gate run methodology

---

## 9. Skill revision log

- **v1.0** — 2026-05-04, post-slice-1a. Initial codification of Stage I empirical discipline. Authored from STAGE_I_PROGRESS_2026-05-04.md, codegen_silent_drop_finding.md, and the slice 1 reclassification post-mortem.
- **v1.1** — 2026-05-26, post-v31.5.A. Added Section 8 (SUPER C v1 / scc Compiler Empirical Patterns) codifying 5 lessons from the v31.4 → v31.5.A ARM64-backend cycle: `emit-direct -o` requirement, `SCC_O1_DUMP` canonical probe + SHIRL opcode key, Wave-Sequencing Contract gate values (scc_smoke 127/0, gold_gate 21/0), seedc 8-param hard cap mitigation, and DEF-v21-SLICE5F-001 `arenas.operands_len` miscompile + fully-pooled-helper mitigation. Cross-linked to `apex-verified-machine-encoding` for the byte-level layer.
- **v1.2** — 2026-05-26, post-v31.5.I.F1.a. Added §8.6 (Helper Extraction Mandate Under Register Pressure, sharpened) with quantified empirical anchor: inline addition of ≥3 locals to a register-pressured SC function produced **450× runtime slowdown** in the v31.5.I.F1.a first attempt (sha256_kat 0.4s → 3+ minutes). Concrete case study (StmtLet struct_size_mask 5-local diff) + MANDATORY 3-step mitigation (register-pressure audit → fully-pooled helper extraction → timed gate verification with 2x slowdown halt rule) + working fix (`lower_decode_struct_alloc` 2-param helper at lower_walker.sc:418, restored 0.34s parity). Project-agnostic frame for any register-pressured target (ARM64/RV32/embedded). Cross-linked to `apex-verified-machine-encoding`, `sc-field-lowering-discipline`, `sc-empirical-surface-probe`.

- **v1.3** — 2026-05-26, post-v31.5.I.F1.runtime. Added §9 (Postfix Disambiguation Guard) anchored to the v31.5.I.F1.runtime parser k==37 (LBrace) arm episode. When adding a new postfix arm to an expression parser, the guard must make the new arm **provably disjoint** from existing non-postfix paths — not just statistically unlikely. Two-part discipline:
  (1) Restrict by LHS shape (Ident-only for StructLit; numeric-only for index suffix; etc.).
  (2) Add forward-token lookahead to confirm the body shape matches the new feature, not the legacy fallthrough. For StructLit: `{` must be followed by either `}` (empty struct) or `Ident ':' first-field-value` — anything else falls through to the existing Block-as-expression path.
  Without (2), `if a > b { return X }` regresses (b is Ident, `{` follows, but `return` ≠ Ident, so lookahead correctly rejects). Empirical anchor: scc_smoke 127 → 126 transient regression on Case 40 caught + fixed by the two-token lookahead BEFORE Phase 1 was committed.
  Companion lesson: **trust empirical token-kind constants over documentation comments.** parser.sc:2275 comment claimed Colon=44; actual empirical Colon=43, ColonColon=44. The new postfix arm used 46 for Colon by mistake (literally an even worse FatArrow value), so the lookahead silently rejected ALL valid struct literals → Phases 1+2+3 were silent no-ops until the AST kind histogram probe surfaced it. Add `--print-tokens` or token-kind histogram probe to compiler-tooling for future grammar work.
