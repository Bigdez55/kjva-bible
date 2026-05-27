# Apex Systems Architect — Agent Memory

## Current Focus: Phase 2f — XK_SYS_WAIT_MANY Handler

**Status:** Design phase complete (2026-03-21)
**Deliverable:** `kernel/xenos/design/phase2f_wait_many_handler.md` (13 sections, ~750 LOC of pseudocode)

### Key Architectural Decisions

**Waitable Objects (Three Categories):**
1. **Events** — Kernel-managed signaling via capability handle (from EVENT_CREATE syscall 21)
2. **Timers** — Single-shot LAPIC deadline checks via TSC (slot indices 0-15)
3. **Vnodes** — File descriptors for I/O readiness (FD 3-63, Phase 2f stub → Phase 3 async)

**Wait Strategy:**
- Spin-yield polling loop (cooperative scheduler-friendly)
- No real wait queues in Phase 2f (deferred to Phase 3)
- Timeout via TSC comparison: `deadline_abs = pal_get_tsc() + (timeout_ns * tsc_hz / 1e9)`
- MAX_POLL_ITERS = 100,000 guard (prevent infinite loops)

**Fixed-Size Data Structures:**
- Stack-allocated wait context: 16 nodes × 16 bytes = 256 bytes
- No heap allocation (all state pre-sized)
- Results array written directly to user VA (bounds-checked)

**Capacity Constraints:**
- Max 16 objects per call (enforced via EINVAL if > 16)
- 32 event slots, 16 timer slots, 64 FDs per process
- No resource exhaustion vector (everything is bounded)

### Implementation Blueprint

**Syscall Signature (System V AMD64 ABI):**
```
RAX=61, RDI=max_items, RSI=user_handles_va, RDX=timeout_ns, RCX=user_results_va
Returns: >0 = signaled count, 0 = timeout, <0 = error
```

**Handle Array Format:**
- User provides: uint64_t handles[max_items]
- Kernel classifies each: capability (event), slot index (timer), FD (vnode)
- Results written back: struct { uint8_t signaled, object_type, int32_t error_code }

**Error Handling:**
- EINVAL: invalid max_items, timeout overflow, unknown handle
- EFAULT: unmapped user VA (handles or results buffer)
- ETIMEDOUT: timeout expired (return 0)
- EBADF: invalid FD

### Integration Points (Already Implemented)

- **event_find_by_handle()** — exists in main.c line 1214
- **g_events[32]** — exists, populated by EVENT_CREATE (syscall 21)
- **g_timers[16]** — exists, populated by TIMER_CREATE (syscall 25)
- **g_processes[].fd_table[64]** — exists, populated by VNODE_OPEN (syscall 48)
- **_fd_validate()** — exists in main.c line 1273

### Testing Strategy

**phase2f_tests.c coverage:**
- Smoke: initialization without crash
- Functional: single/multiple events signaled, timeout behavior, mixed event+timer
- Security: max_items bounds, invalid handles, EFAULT paths
- Stress: 16 objects simultaneously, 100 repeated calls
- Observability: syscall counter (g_syscall_counts[61]) incremented

**CI Pipeline:** `.github/workflows/phase2f.yml` (5-job gate)

### Phase 3 Migration Path (Future-Proof Design)

**Real Wait Queues (Phase 3):**
- Replace polling loop with red-black tree waiters per object
- Wakeup callbacks on event signal / timer expiry
- Zero CPU usage for sleeping threads (no yield loop)

**SMP TLB Shootdown (Phase 3a):**
- Send IPI to remote CPUs holding WAIT_MANY on same object
- Use xlapic_send_ipi_broadcast(..., XK_VEC_WAIT_MANY_WAKEUP)

**Async Vnode Signaling (Phase 3):**
- XVFS layer registers per-FD completion callbacks
- I/O completion → set vnode ready flag
- WAIT_MANY detects readiness without polling

**API Stability:** Zero user-space changes across Phase 2f → Phase 3 transition.

### Key Constraints (Phase 2f)

- Single-threaded cooperative scheduler (no preemption)
- No SMP (but design prepared for SMP in Phase 3a+)
- No real wait queues (spin-yield acceptable on single CPU)
- Timeout measured via TSC (no HPET fine-grain in Phase 2f)
- Vnode signaling stubbed (always returns unsignaled)

### Code Locations

- **Design doc:** `kernel/xenos/design/phase2f_wait_many_handler.md`
- **Implementation target:** `kernel/xenos/core/main.c` (new kern_wait_many before xenos_syscall_dispatch)
- **Test suite:** `kernel/xenos/tests/phase2f_tests.c` (template provided in design doc)
- **CI:** `.github/workflows/phase2f.yml` (new file)

### Estimated Sprint Effort

- **Design review:** 2h (this document)
- **kern_wait_many() core:** 4h
- **Helper functions:** 1h
- **Error handling + results:** 2h
- **Test suite:** 6h
- **CI integration:** 1h
- **Code review + bug fixes:** 3h
- **Total:** ~20h for Sprint 43

---

## Previous Work: Phase 2d (Documented in phase2d-implementation.md)

[Reference: phase2d-implementation.md for process/job table context, fiber scheduling patterns, capability model foundations]

## SUPER C v1 — Cross-Agent Coordination Lessons (2026-04-25)

**Context:** Multi-agent parallel work on `desmond-super-c/superc-v1/` repo. Several agents writing concurrently to `compiler/seedc/`. No remote, local-only main branch.

**Key patterns that worked:**
1. **New compilation unit + accessor surface = zero collision.** Trait solver (slice 4c) shipped as new files `src/sema_traits.c` + `include/scs0_sema_traits.h`. Existing `Sema` struct stays private to `sema.c`. New file consumes `sema.c` only via 2-function accessor pair appended at file end. Concurrent agents writing other parts of `sema.c` did not collide.
2. **Makefile uses `$(wildcard src/*.c)`** — new `.c` drop-ins are picked up automatically. Zero Makefile change needed.
3. **Atomic `git add ... && git commit ...` with explicit `--` pathspec** is the only reliable way to commit when other agents are running `git stash` / `git reset` between commands.

**Patterns that bit me:**
1. Concurrent agents run `git stash push -u` to isolate their WIP; this can sweep my untracked files. Recovery: `git checkout stash@{0} -- <my-paths>`. Verify `git stash list` to find your work; never `pop` wholesale (mixes WIP).
2. `git reflog -10` shows `reset: moving to HEAD~1` events from parallel agents. My staged work can vanish between `git add` and `git commit`. Mitigation: use atomic add+commit on same bash line.
3. The `Bash` tool resets cwd between calls — always use absolute paths. The Edit tool's "file modified since read" guard fires on stash rotations; re-read before retry.

**Slice 4c trait solver design notes (for follow-on Stage 5 work):**
- `type_nominal_symbol(TYPE_PATH)` returns the bare nominal Symbol regardless of type_args. Means `Reverse<T>` and `Reverse<u32>` key on the same `Reverse` Symbol in the impl_table — generic-impl machinery is reusable for S2.D14 retirement.
- Trait fn parser preserves `body` field when `{ ... }` is present, sets to NULL when followed by `;`. Default-method synthesis can use lookup-time fallback (cheap) instead of eager AST cloning (expensive).
- `preregister_functions` in `scir_lower.c` does NOT descend into `ITEM_TRAIT.items[]` (only `ITEM_IMPL.items[]` and inline `ITEM_MODULE.items[]`). Trait-only default bodies cannot be called via codegen until that's extended. Slice 4c's S2.D02 retirement is sema-level only.
- `SCIR_LOW_DUMP` reproducible-build SHA `4a7ca98637536430c40b7e2f6bd8dc3aba4116e4ae6e7cd48e2f888a19f919d1` is the canonical anchor. Any sema-only change should preserve it (slice 4c did).

**Canonical green gates (SUPER C):**
- `cd compiler/seedc && make clean && make` (must build under `-Werror`)
- `bash compiler/seedc/tests/test_driver.sh` (currently 26/26 post-slice-4d/7+4g)
- `bash compiler/scc/tests/scc_smoke.sh` (currently 21/21)
- `SEEDC=./build/seedc-... sh tests/stage3b/run_stage3b.sh` (currently 12/12 ACTIVE)
- LOC ceiling: 21,500 (per STAGE4 §8.1). Slice 4d added ~660 LOC; aggregate seedc ~19,000.

## Slice 4d ABI classifier (2026-04-25 follow-up)

`compiler/seedc/include/abi_classify.h` + `compiler/seedc/src/abi_classify.c` —
single source of truth for SysV §3.2.3 + AAPCS64 §6.4.2 classification.
9 AbiClass values + 4 predicates + abi_indirect_buffer_size. INT1 codegen
emission landed on both backends; INT2/SSE/HFA/INDIRECT abort with slice-
ref message until follow-up.

**Empirical blocker discovered at 4d.7:** scir_lower::ity_to_low maps
ITY_NOMINAL → void at the SCIR boundary (line 197). End-to-end struct-
return SC source cannot exercise aggregate-return emission today; the
classifier + codegen are correct but unreachable through the lowering
pipeline. Tests exercise the classifier directly via `tests/test_abi_classify.c`
(48-case unit harness, wired as Case 22c in test_driver.sh).

**Critical file-revert hazard (4d.6 burn):** Sibling agents' tooling
(format-on-save / linter) can silently overwrite Edit'd files between
operations. Pattern that worked: issue all related edits in a single
assistant turn (no advisor / Bash interleaving), then immediately
`make clean && make && tests && git add && git commit` chain in one
Bash call to durably persist the bytes before the next revert window.
Never trust an "Edit succeeded" without an immediate atomic commit.

**`set -e` test_driver.sh hazard:** A sibling injected a `seedc_run`
function shim (line 28). With `set -e` (line 12), any silent `cc`
compile error in a Case clause halts ALL subsequent cases including
the reproducible-build check. Mitigation: append `|| true` to cc
compile lines that may legitimately fail (e.g. on missing fixtures);
explicit `rc=0` initialization before exec keeps rc unbound errors
from propagating.

## Slice 4b NLL borrow checker (2026-04-25)

**Shipped:** Slice 4b/2 — phases 0-1 of MIR-style NLL solver.
Coordination commits: `ff3ba95` (code, swept with parallel
lower_concurrency) + `0c1e558` (docs) + `ebf08c9` (HALT).

**4b/2 components delivered (in compiler/seedc/src/borrow_check.c, 753 LOC):**
- Bump arena over caller-supplied 4 MB scratch buffer (design §11.6).
- CFG-point indexer `block_start[block_count+1]`; point (b,i) maps
  to `block_start[b]+i`.
- Iterative post-order DFS for RPO using `(stack, succ_idx)`
  arrays + visited bitset — no recursion.
- `RefEntry` collection: every `SHIRL_ADDR_OF` becomes a Region
  with Place keyed on (origin_sym=ValueId of operand, PK_WHOLE,
  flags from B1 mut-bit).
- B1 fix in scir_lower.c:493-509 — stash mut-vs-shared into
  `inst->field_index` of `SHIRL_ADDR_OF` (otherwise unused per
  scir_low.h:124).
- B3 quantum E1320-E1323 added to BorrowCkDiagCode enum.
- Per-block use[]/def[] bitsets via Aho/Sethi/Ullman §10.6 forward
  walk: operand-uses BEFORE same-block defs land in use[b].
- Backward dataflow propagator: in[b] = use[b] U (out[b] \ def[b]);
  out[b] = U in[s]. Iterates in PO (= RPO of reverse CFG); 256-iter
  cutoff guards against pathological graphs.
- Region seeding from in[b] (conservative; 4b/3 will tighten).
- CLI `--borrowck=stage0|nll|strict` in main.c, default STAGE0;
  per-fn 4 MB scratch arena allocated once, reused.

**Key structural decisions (preserve in future slices):**
- `BorrowCtx` struct private to borrow_check.c (no header export).
- All bitsets word-count must match for `bitset_union` to copy bytes
  cleanly with memcpy.
- Slice 4b/2 emits NO diagnostics — phases 2-7 incrementally fill
  in 4b/3-4b/7. This guarantees green at every commit.

**Blockers surfaced at HALT (parent must resolve before 4b/3-4b/7):**
1. seedc LOC at 21,481 / 21,500 §8.1 flag — 19 LOC margin. 4b/3
   alone needs 200-400 LOC. Either raise flag to 22,500 or contract
   sibling slices (lower_concurrency/lower_mint/qir_emit may have
   unused scaffolding).
2. 4 quantum_linear fixtures (qubit_clone, qubit_double_consume,
   qubit_leaked, use_after_measure) crash at scir_lower with
   INTERNAL "nonvoid function reaches end without return value" —
   slice-4a tail-return bug (Deferred Item #2 from STAGE4_PROGRESS).
   These cannot pass until 4a's bug is fixed.
3. 2 quantum_linear fixtures (qubit_shared_borrow, qubit_across_ffi)
   pin `pending: slice 4a` with codes E1325/E1329 outside B3's
   authorized vocabulary. At 4b/7 with `LANDED="4b"` literal, these
   stay SKIP — accept it.
4. E0320 semantics: `borrow_past_last_use.sc` requires region
   extension to `max(last_use, base_move_within_binding_scope)`.
   Standard Rust-NLL would accept; SC's design is stricter. Plan
   covered (advisor hand-trace); implement at 4b/4.

**File-revert hazard observed AGAIN at 4b/2:** A `<system-reminder>`
showed borrow_check.c reverted to 203-line skeleton mid-session
WHILE git showed 753 LOC at HEAD. The system-reminder was a stale
filesystem snapshot — git was authoritative. Do NOT re-implement on
the basis of system-reminders alone; verify with
`git show HEAD:./path/to/file | wc -l` first.

**Coordination model (reaffirmed):** Local-only main; no remote.
Parallel agents commit straight to main. Surgical staging (`git add
<specific-file>`) is mandatory — `git add -A` will sweep other
agents' unstaged work into your commit. If your edits get swept into
another agent's commit message (as 4b/2 work was into ff3ba95),
that is acceptable per anti-revert clause: "the work is durable on
main; the deliverable shipped — record the coordination artifact in
STAGE4_PROGRESS.md and proceed."

