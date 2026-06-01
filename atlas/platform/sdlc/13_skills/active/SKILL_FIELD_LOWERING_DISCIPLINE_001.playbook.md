# sc-field-lowering-discipline

<!-- Source: migrated from ~/.claude/skills/sc-field-lowering-discipline/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: sc-field-lowering-discipline -->

**Summary.** Empirical discipline for SUPER C compiler sessions that touch struct definitions, struct literals, struct fields (kind_field), field READ or WRITE lowering, ref-param field access, compound assign on fields, STACK_ALLOC sizing for aggregates, or field_offset/field_index handling in codegen. Codifies the four canonical bug classes surfaced during GB-FIELD-LOWERING-001 closure: STACK_ALLOC size collapse, field READ no-offset, field WRITE dropped, and missing field offset/width stamping. Mandates SCC_O1_DUMP empirical discovery on four canonical probes BEFORE any code is edited, and enforces strict implementation order F1.a (size) → F1.b (READ) → F1.c (WRITE) with full gate hold after each step. Trigger this skill whenever a self-host compiler session must reason about aggregate lowering, kind_field consumers, or struct STORE/LOAD emission. Cross-references compiler-discipline (SHIRL opcodes), one-shot-execution-planning (Pre-Flight Empirical Baseline), and apex-verified-machine-encoding (ARM64 LDR/STR encoding).

# SC Field Lowering Discipline

**Version: v1.2** (refined 2026-05-26 from v1.1 with F1.runtime dump-≠-runtime lesson)

**DIRECTIVE: Probe empirically. Stamp once. Lower in order. Gate after each step.**

This skill is the institutional memory of `GB-FIELD-LOWERING-001` —
the moment the SUPER C self-hosted compiler had to teach itself how
to read and write a struct field. The four canonical bugs below are
not hypothetical. They are the four failure modes that empirically
surface every time a self-hosted toolchain reaches aggregate
lowering and a previous bootstrap shortcut (treat-aggregates-as-
scalars) has to be retired. Future field-lowering work — across
SUPER C and any successor language hosted by it — must invoke this
skill BEFORE touching parser, sema, lower_walker, or codegen.

---

## 1. When to invoke

Activate this skill any time an SC compiler session touches:

- Struct definitions, struct literals, struct fields (`kind_field = 6`).
- Field READ (`x.field`) or field WRITE (`x.field = ...`).
- Ref-param field access (`fn f(s: &mut S) { s.field = ... }`).
- Compound assign on field (`s.field += 1`).
- `STACK_ALLOC` sizing for aggregates.
- `field_offset` or `field_index` handling in codegen.
- Removal of any historical "treat aggregates as scalars" shortcut
  in `lower_walker.sc`, `sema_*`, or `codegen_*`.

If any of the above are in scope, STOP. Run the Discovery Procedure
(§3) BEFORE drafting design changes. The handoff's framing of the
bug surface is a hypothesis; SCC_O1_DUMP is the ground truth.

---

## 2. The Four Canonical Bug Classes

Every field-lowering pass eventually hits these four. Name them
explicitly in the One Shot Plan so the regression matrix can target
each in isolation.

### 2.1 STACK_ALLOC size collapse

**Symptom.** Allocating a struct returns 4 bytes (or whatever the
scalar default is) instead of the struct's actual byte size.
Subsequent writes to the second-or-later field overflow into
unrelated stack slots.

**Cause.** Aggregate types fall through to the scalar default in the
size-of pass. The struct type is never stamped with its computed
size, so STACK_ALLOC's const_lo is wrong.

**Mitigation.** Parser or sema (whichever owns the type registry)
must stamp struct size during definition processing. lower_walker
must read the stamped size, not the scalar fallback.

### 2.2 Field READ no-offset

**Symptom.** `s.a` and `s.b` both evaluate to the same value (the
value of `s.a`). All fields appear to "collapse" to the first.

**Cause.** `kind_field` is a stub in lower_walker that emits a LOAD
on the base slot, ignoring `.field` offset. The walker doesn't
consult the resolved field offset because no offset has been
stamped on the field AST node.

**Mitigation.** Walker must add the sema-provided field offset to
the base slot pointer before LOAD_32 (or whatever load width the
field type demands). This depends on §2.4 having stamped offset
information on the field AST node.

### 2.3 Field WRITE dropped

**Symptom.** `s.a = 7` followed by `return s.a` returns the
initial value, not 7. Field assignments appear to be silently
discarded.

**Cause.** `kind_assign` and `kind_compound_assign` have an
Ident-only guard that lowers only RHS for side-effect traversal
when LHS is not a plain Ident. Field-LHS falls through this guard.
The RHS is evaluated and discarded; no STORE is emitted.

**Mitigation.** Dispatch field-LHS to a dedicated emit helper that
performs STORE_32(slot + offset, rhs_val). For compound assign,
the helper performs LOAD → arith → STORE in sequence. This depends
on §2.2 (READ producing correct offset) for the compound case.

### 2.4 Field offset/width not stamped

**Symptom.** kind_field AST node carries the field-name byte span
but no resolved offset and no resolved width. Walker has no way to
compute the slot pointer at lower time.

**Cause.** Sema (or parser, if struct type info lives there) never
walks the struct's field declarations to compute cumulative byte
offsets and per-field widths, or it walks them but does not back-
link the resolved offset to each field-use AST node.

**Mitigation.** Decide: parser-side or sema-side stamping. Sema is
usually correct because field references need the resolved struct
type, which depends on type resolution. Parser-side stamping only
works if struct definitions are syntactically resolvable (no type
aliases, no generics) — usually they are not. **Default: sema-side
stamping, parser leaves field AST nodes with null offset/width and
sema fills them during reference resolution.**

---

## 3. Discovery Procedure (BEFORE Coding)

Before drafting any design diff, run the SCC_O1_DUMP probes in
order. Each probe isolates exactly one of the four canonical bugs.
Capture the dump for each in a single audit note that the One Shot
Plan can cite.

### 3.1 Four canonical probe fixtures

Run each with `SCC_O1=1 SCC_O1_DUMP=1 scc emit-direct <probe>.sc`
and capture the SCIR-Low dump. Compare across probes — the
differences pinpoint which bug class is active.

**p1 — SIZE only.**

```sc
struct S { a:u32, b:u32 }
fn main() -> i32 {
  let s = S{ a:1, b:2 };
  return 42;
}
```

Question: does `STACK_ALLOC` have correct `const_lo` (= struct
byte size, here 8)? If `const_lo == 4`, §2.1 STACK_ALLOC size
collapse is active.

**p2 — READ.**

```sc
struct S { a:u32, b:u32 }
fn main() -> i32 {
  let s = S{ a:1, b:2 };
  return s.b as i32;
}
```

Question: does the LOAD_32 op_base differ from p1 — i.e. does the
walker emit a LOAD at base+offset(b)? If LOAD_32 op_base equals
the slot base (offset=0), §2.2 field READ no-offset is active.
Also: is the returned value 2, or 1 (which would indicate offset
collapse)?

**p3 — WRITE (and compound-assign foundation).**

```sc
struct S { a:u32, b:u32 }
fn main() -> i32 {
  let mut s = S{ a:1, b:2 };
  s.a = 7;
  return s.a as i32;
}
```

Question: does STORE_32 appear at all in the SCIR-Low dump after
the lowering of `s.a = 7`? If no STORE is emitted, §2.3 field
WRITE dropped is active. Also: if STORE appears but offset is
wrong, that is the WRITE-side mirror of §2.2.

**p4 — ref-param field WRITE (function boundary).**

```sc
struct S { a:u32, b:u32 }
fn f(s: &mut S) { s.a = 1 }
fn main() -> i32 {
  let mut s = S{ a:5, b:6 };
  f(&mut s);
  return s.a as i32;
}
```

Question: does `fn_0` (or whichever function index `f` lowers to)
contain a STORE_32? Does the STORE address the ref-param's base
slot plus field-a offset? This probe exposes the intersection of
§2.3 (WRITE dispatch) and §2.2 (offset resolution) across a
function boundary — the hardest of the four to get right.

### 3.2 Locate producers and consumers

Before designing the fix, identify by file path and line range:

1. **kind_field producer** — typically `parser.sc`'s
   `ast_write_field` (or similar). What fields does it stamp on the
   AST node? Does it stamp offset, width, parent-type, all three, or
   none?
2. **kind_field consumer** — `lower_walker.sc`'s field-handling
   stub. What does it currently emit? Does it look up the AST node's
   offset, or does it ignore offset entirely?
3. **Sema struct registry** — where struct definitions are stored
   after sema. Is there a per-struct field table with cumulative
   offsets? If not, where would it live? If yes, does any current
   pass read it?

### 3.3 Decide stamping locus

With §3.1 and §3.2 in hand, decide explicitly: parser-side or
sema-side offset stamping. Cite the constraint that forced the
choice. Default is sema-side (see §2.4).

The decision goes in the One Shot Plan as a single sentence:
"Field offset and width will be stamped by `<file>:<function>` at
`<pass-name>` time, consumed by `lower_walker.sc:<function>`."

---

## 4. Implementation Order

**F1.a (size) → F1.b (READ) → F1.c (WRITE).**

Reason:

- WRITE depends on READ semantics for compound-assign
  (`s.a += 1` decomposes to LOAD + ADD + STORE; the LOAD half is
  pure READ).
- READ depends on SIZE for correct allocation — if STACK_ALLOC is
  the wrong size, READ at non-zero offsets will read past the slot.

Each step is a separate commit. No combined "F1 closure" commit
that lands all three at once. Wave-sequencing (§5) requires
empirical re-verification after each step; bundling defeats the
gate.

If empirical evidence (§3) shows §2.4 stamping must land
separately from §2.1/2.2/2.3 dispatch, treat it as F1.0
(prerequisite) before F1.a. Stamping without consumers is a no-op
landing; consumers without stamping is a misalign waiting to
happen. Land stamping first only if the stamped data is read by
nothing yet — i.e. the change is provably inert.

### 4.1 Sub-cycle execution order with empirical anchors (v31.5.I)

The v31.5.I.F1 series is the canonical reference execution of this
order. Each sub-cycle below is anchored to its sealing commit and
its empirical-gate witness so future sessions can compare drift.

| Sub-cycle | Status | Empirical anchor |
|---|---|---|
| F1.a (STACK_ALLOC size) | SEALED 92fa2862 | struct_stack_alloc_size_gate 6/0 |
| F1.b stamps (Pass 4.21) | SEALED 8d5f1995 | zero-behavior-change; all prior invariants held |
| F1.b (field READ) | SEALED 55ac0004 | field_read_offset_width_gate 8/0 |
| F1.c (field WRITE) | SEALED e161b77a | field_write_lhs_gate 8/0 |
| F1.0 (struct literal init) | OPEN | runtime regression discovered; blocks end-to-end RC verification |
| F1.d (void RET) | OPEN — premise contested | empirical probe required first |

Two open rows above are the live frontier as of v31.1.5.I close.
F1.0 is the struct-literal initializer path (separate from F1.a's
StackAlloc sizing); F1.d is a void-return-statement question whose
premise is contested and must be re-probed before any design diff.
Treat both as gate-blockers for any "F1 closure" claim.

---

## 5. Wave-Sequencing

After each F1.x:

- `scc_smoke` must hold at 127/0 (or whatever the current baseline
  is at session start).
- `gold_gate` must hold at 21/0.
- The probe from §3.1 that corresponds to the just-landed step
  must transition from FAIL to PASS, and previously-passing probes
  must not regress.

If any gate fails, **safe-revert** per `compiler-discipline §
Bootstrap-safety class taxonomy`. Do not "fix forward" through a
broken intermediate. Field lowering is BOOTSTRAP-CRITICAL — every
self-hosted source file that uses a struct will execute the new
lowering path on the next scc rebuild.

A broken intermediate that escapes the gate will silently miscompile
scc itself on the next bootstrap. The miscompile may not surface
until a later cycle, by which point the diff that caused it is
buried under unrelated work. Safe-revert is cheap; bisecting a
silent self-host miscompile is not.

---

## 6. STORE Width Promotion Guard for Aggregates

### Mandatory rule

ANY auto-promotion of STORE width (e.g., STORE_32 → STORE_64)
MUST be gated by an aggregate-type check. Initialization values
originating from bare-Ident-fallback (e.g., the dropped struct
literal `Cursor` parsed as bare Ident) are 32-bit. Emitting
STR X (64-bit ARM64) reads upper-half register garbage from
whatever was last in the source register, corrupting the
struct's interior bytes.

### Symptom of violation

- Struct allocation byte size is correct (F1.a)
- Field reads correctly use field_index (F1.b)
- BUT runtime infinite-loop or wrong field values because the
  struct's tail bytes contain garbage from register state at
  the time of the spurious STORE_64

### Required check pattern

```sc
let mut st_op: u32 = shirl_store_32(zero);
if alloc_bytes == (8 as u32) {
    if struct_bytes == (0 as u32) {   // ONLY promote for ptr-primitive
        st_op = zero + 35 as u32;      // STORE_64
    }
}
```

### Empirical anchor

v31.5.I.F1.a — initial implementation promoted STORE to
STORE_64 for any 8-byte StackAlloc, including 8-byte structs.
The 8-byte struct's init_val (from bare-Ident "Cursor"
lower_expr fallback) was a 32-bit ValueId. STR X read the
upper 32 bits of W1 (register garbage) and stored to the
struct's tail bytes. case40 loop guard `l.pos < l.len` saw
non-zero garbage l.len → infinite loop. Fix: gate STORE_64
promotion on `struct_bytes == 0`.

### Project-agnostic frame

On any compiler where store-width is inferred from destination
size rather than source value, aggregate-typed destinations
require explicit source-width verification. The destination's
allocation size is a necessary but not sufficient signal —
without inspecting the source value's effective width, the
upper bits of an aggregate's spill are register-state-dependent
and indistinguishable from intentional initialization.

### SHIRL opcode quick-reference (width × direction)

| Width | LOAD | STORE |
|---|---|---|
| 1 byte | 52 | 32 |
| 2 byte | 53 | 33 |
| 4 byte | 30 | 34 |
| 8 byte | 31 | 35 |

Use this table when authoring promotion guards or width-cast
helpers. The STORE_64 promotion in the rule above corresponds
to opcode 35; the default STORE_32 is opcode 34. Promotion
into row 35 without an aggregate-type check is the v31.5.I.F1.a
failure mode.

---

## 7. Cross-Reference

- **compiler-discipline** — SHIRL opcode reference (LOAD_32,
  STORE_32, STACK_ALLOC), Bootstrap-safety class taxonomy, STOP-6
  protocol. Field lowering changes are typically HIGH-RISK or
  BOOTSTRAP-CRITICAL.
- **one-shot-execution-planning** — Pre-Flight Empirical Baseline.
  The Discovery Procedure (§3) is the field-lowering-specific
  realization of the Pre-Flight Empirical Baseline mandate.
- **apex-verified-machine-encoding** — ARM64 LDR/STR encoding. The
  load and store machine-code constants emitted by codegen for
  field READ and WRITE must be oracle-verified per that skill's
  one rule. Do not hand-compute a `ldr w0, [x0, #imm12]` constant.

---

## 8. Anti-Patterns

These are concrete failure modes observed during real sessions.
Each one will silently corrupt the bootstrap if not caught.

- **Skipping SCC_O1_DUMP before designing.** The handoff's four-bug
  framing is a hypothesis. SCC_O1_DUMP is the ground truth. Without
  the dump, you are designing against a story, not the actual IR.
- **Trusting the handoff's 4-bug framing without empirical re-
  verification.** The exact subset of bugs active in the current
  tree may be one, two, three, or all four — and which probes
  trigger which classes may have shifted since the handoff was
  written. Re-probe every session.
- **Adding STORE for field WRITE without first verifying READ
  produces correct offset.** Compound-assign (`s.a += 1`) silently
  reuses READ's offset logic. If READ has a bug, WRITE inherits it
  in the compound case, and the test for plain WRITE will pass
  while compound WRITE silently miscompiles.
- **Inlining helper logic that pushes past seedc's register-
  pressure threshold.** Field-emit helpers near the 8-param cap
  must follow the fully-pooled-helper pattern (see
  `emit_arith_fully_pooled` in `lower_walker.sc`). Inlining past
  the cap silently drops parameters and produces ELF that builds
  clean but SIGSEGVs at runtime.
- **Landing F1.a, F1.b, F1.c as a single combined commit.** The
  wave-sequencing gate is per-step. A combined commit cannot
  isolate which step broke the gate, and safe-revert becomes
  all-or-nothing.
- **Treating "build PASS" as "field lowering works".** Build PASS
  means the compiler compiled. Runtime PASS on probes p1–p4 means
  field lowering works. Empirically these are different things —
  see project memory `project_v31_4_A1_build_pass_runtime_fail.md`.

## §7 — Dump ≠ Runtime (v1.2 anchor: F1.runtime episode)

The F1.b (`field_read_offset_width_gate`) and F1.c
(`field_write_lhs_gate`) gates passed 8/0 each with SHIRL_LOAD_N /
SHIRL_STORE_N + correct `field_idx` values stamped — yet **struct-
bearing programs still returned RC=0 from bridge JIT** instead of the
explicit `return 42`. The dump-only gates couldn't see this. Only
empirical runtime RC verification could.

**Rule:** No `field_*` feature is sealed until BOTH gates green:
- structural (SHIRL dump shows correct op + field_idx), AND
- runtime RC (scc run-jit returns the expected value via path=bridge).

The F1.runtime episode also surfaced a second class of dump-invisible
bug: **silent-success guards in error paths.** `lower_field_assign`
returned `1` (handled) on operand-pool exhaustion WITHOUT emitting any
STORE — silent success masking a missing write. The dump gate couldn't
see the missing STORE because the function reported "handled" upstream.
Only a runtime RC probe surfaced the divergence.

**Anti-pattern to grep on any emitter PR:**
```
grep -nE 'return 1.*pool|return 1.*exhaust|return 1.*cap' compiler/scc/src/*.sc
```
Every hit needs review — convert to `return 0` (unhandled) so caller
falls through to diagnostic-visible path rather than masking the
elision.

Cross-reference: the NEW `gate-dump-vs-runtime` skill v1.0.0 generalizes
this rule project-agnostically.
