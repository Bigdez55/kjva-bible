# Conformance Audit — Residual Resolution Report (2026-06-02)

**Scope.** Close the residual ledger from the adversarial conformance audit that asked
"is the model *completely put together as described*" against the three locked
source-of-truth docs: `UNIFIED_MASTER_TECH_PACK.md`, `ADR-0001`, `ADR-0002`. The audit
honestly verdict'd **"NO — model proper is done; the cognitive wrapper was partial"** and
produced a residual ledger including two security findings the prior pass had over-claimed
past. This report records what was fixed, **classified honestly** so nothing reads as more
"live" than it is.

Source-of-truth order applied throughout: **running code > test evidence > manifests > docs.**
ADR-0001 / ADR-0002 are immutable and were **not** edited.

---

## Test evidence (verbatim)

```
tests/ ............................................. 89 passed   (was 80; +9 new guards)
tests/test_pt_xmind_parity.py ...................... 1 passed    (correctness core)
ai/xmind  make clean && make ....................... ✓ libxmind-core.a/.dylib + xmind-cli
```

New guards added this pass: `test_l5_l7_failclosed.py` (5), `test_writeback_no_raw_session.py` (2),
and the **streaming covenant** guard in `test_governance_block.py` (+2:
`test_covenant_block_withholds_from_streaming` + clean control).

---

## A. Behavior-affecting fixes (these change runtime behavior)

| # | Finding (severity) | Site | Fix | Proof |
|---|---|---|---|---|
| A1 | **Streaming covenant bypass** (CRITICAL) | `api.py` `chat_stream` | Extracted shared `_enforce_covenant()` (fail-closed) and called it in the streaming path, which previously skipped the covenant gate entirely. Gate runs BEFORE context-fetch + the token generator, so a block raises before any inference. | `test_governance_block.py::test_covenant_block_withholds_from_streaming` (blocked→422, neither `chat` nor `stream` reached) + clean control. **This guard was added because the pre-existing covenant test only covered the non-streaming `chat` path — my actual fix was unguarded until now.** |
| A2 | **Raw `session_id` → SoulManager/Journal/Archive** (HIGH) | `heptagon/writeback.py` ×4 | All four emit sites now pass `_hashsid()` (SHA-256/16 hex, `sid:` prefix). No raw id leaves the process. | `test_writeback_no_raw_session.py` (to_dict + wire-capture) |
| A3 | **L7 hard gate fail-OPEN on exception** (HIGH) | `agent.py` L7 block | On enforcement exception the response is now **withheld** (fail-closed), not passed through unchecked. | code + `test_l5_l7_failclosed.py` |
| A4 | **L5→L7 coupling fail-OPEN** (HIGH, advisor-found) | `agent.py` L5/L7 | A *crashed* `verify()` left `verdict=None`, which the L7 ctx read as `passed=True / safety_failed=False / total_errors=0` — a crashed verifier silently handed the hard gate a clean bill. Now an L5 crash propagates `safety_failed=True / not-passed` into L7. | `test_l5_l7_failclosed.py::test_crashed_L5_verifier_fails_closed_into_L7` |
| A5 | **`DeterminantProbabilityRecord.deterministic_inputs` empty** (MEDIUM) | `agent.py` `_emit_records` | Now populated with real replay snapshots: policy/model config hashes (cached once at init), route-policy hash, budget-state hash, and the **real recalled-atom memory-index snapshot**. The replay property now has content. | `test_l5_l7_failclosed.py::test_determinant_inputs_are_populated` |
| A6 | **Determinant record silently never emitting** (MEDIUM, surfaced during fix) | `agent.py` `_emit_records` | The deferred `from heptagon.determinant_record import …` was failing under the package collision (B1) and being swallowed by `try/except`. Now proven to emit on the production resolution path. | `test_l5_l7_failclosed.py` (subprocess, src-first) |
| A7 | provenance surfaces memory usage + materialization count | `api.py` | `memory_used` + `materialization_count` added so the recall record is **consumed/observable**, not write-only. | code |

---

## B. Audit-trail records (emit + observable, but do NOT change generation)

The ADR §8/§11 materialization plane is explicitly an **audit trail**. These records are
emitted and surfaced in the API `provenance` (so they are consumed, not dead), but they do
not alter the bytes the model produces. Labeled as such to avoid over-claiming "the
architecture is now live."

- **Response `MaterializationRecord`** — emitted every turn; `materialization_id` + `status`
  returned in `provenance`.
- **Recall `MaterializationRecord`** — emitted **only when memory actually fed the turn**
  (a genuine Memory→Materialization transition, not a per-turn fabrication); counted in
  `provenance.materialization_count`.
- **NOT fabricated:** the §8.3 `weight` / `model-artifact` / `adapter` materializations are
  load-time / adapter-apply-time transitions — they are deliberately **not** emitted per
  chat turn. Emitting all ~12 record types every turn would recreate the exact "well-formed
  dead code / records that feed nothing" problem the original audit flagged.

---

## C. Deliberate deferrals (documented, with reasons — not silent gaps)

- **C1 — Recall is NOT injected into the byte-LM prompt.** The cue-triggered recall packet
  is computed and **consumed** as the deterministic `memory_index_snapshot_hash` (A5) and
  exposed in provenance, but it is **not** prepended to the generation prompt. Reason:
  prompt-injecting recalled free-text into a byte-level model **already proven to confabulate**
  (the PSA 105:1 verse hallucination the user corrected) would reintroduce exactly that
  failure mode. Exact-fact accuracy is served by the **retrieval-grounding path** (LM
  bypassed, `generation_invoked=False`). Documented in `agent.py:_memory_recall` docstring.
  *The scripture-accuracy lesson outranks the conformance checkbox.*
- **C2 — L5 verification remains advisory.** L5 is a quality check, not a safety gate; on a
  benign (non-crash) low-quality verdict it logs and continues. The **safety** posture is
  enforced by the covenant gate (input) + L7 (output), both fail-closed. A *crash* in L5 is
  NOT treated as advisory — it escalates to L7 (A4).
- **C3 — Adapter signature / scope / parent-hash gates** (`training/peft/v2` runtime apply)
  require extending `ai/xmind/include/lora.h` with the genome metadata fields. This is a
  genuine C-ABI change, deferred and recorded here rather than stubbed or false-certified.

---

## D. New findings surfaced *during* the fix (honesty additions)

- **D1 — `heptagon` package-name collision (test-harness artifact).** The repo has TWO
  `heptagon` packages: agent-side `ai/tokenless-agent/src/heptagon/` (owns `state_machine`,
  `verification`, `enforcement`, `determinant_record`) and a ROOT governance `heptagon/`
  (lacks them). Under `python3 -m pytest`, repo-root sits on `sys.path[0]`, so a bare
  `import heptagon` resolves to ROOT and **the agent silently degrades its cognitive modules
  to `None`** (verifier/enforcer/determinant unavailable). The prior 80 in-process tests
  never asserted on the live heptagon loop, so this was invisible. **Production runs the
  server from `src/`, where agent-side wins** (proven by standalone repro). The new
  `test_l5_l7_failclosed.py` runs in a **clean `src`-first subprocess** — the production
  resolution order — so the live cognitive loop now has exactly one real guard. *Recommended
  follow-up (not done, to avoid breaking the collision-aware `test_seven_layer_records.py`):
  a `tests/conftest.py` strategy or package rename so the in-process suite also exercises
  agent-side heptagon.*
- **D2 — SoulManager "five-tier" doc vs "4 buckets" code.** `UNIFIED_MASTER_TECH_PACK.md`
  calls SoulManager "the five-layer memory hierarchy" (register→session→episodic→semantic→
  archival — a **volatility ordering**), while `soul_manager/soul_manager.py` implements **4
  storage buckets** (`persistent, episodic, context, meta` — a **namespace taxonomy**). These
  are *different taxonomies*, overlapping only on "episodic" — not a simple count mismatch.
  Per source-of-truth, the **code (4 buckets) is what is built**. The 5-layer volatility model
  is a conceptual description realized across the broader `memory/` subsystem, not 5
  SoulManager buckets. **Recommendation (NOT applied unilaterally):** clarify the tech pack to
  distinguish "the conceptual 5-layer volatility hierarchy" from "SoulManager's 4 storage
  buckets." Left for owner approval rather than editing a spec doc to match code (per the
  ADR-0003 overstep lesson).

---

## D3 — Repository state blocker → RESOLVED (substrate removed, work committed + pushed)

> **Update (same day):** surfaced to the owner, who confirmed the legacy `models/` tree was
> no longer needed. Read-only audit found zero dependencies on it (superseded by `models v7/`
> + KJVA). Resolution executed: restored `models/` to clean HEAD (undid the half-applied
> strip), committed the conformance work (`1db4042`), then removed the legacy tree as a
> separate commit (`32b1c99`) with the substrate docs repointed to `models v7/`. The unique
> 72M weight + a full source tarball were preserved at `../tokenless-legacy-models-preserved/`;
> the 190 tracked files remain in git history. Pushed to `origin/main`. The original
> point-in-time finding is retained below for the record.



The git root is `Tokenless models/` (one level above `models v7/`) and tracks both the
project and the policy-protected `models/` substrate template. The working tree is in an
abnormal state: the index holds **29 unmerged (3-way conflict, stages 1/2/3) entries — ALL
in `models/`**, with **no merge in progress** (`On branch main`, no `MERGE_HEAD`) — consistent
with an aborted merge or a OneDrive `.git` sync artifact. A pile of `models/` deletions is
also already **staged**.

Honest provenance (per the no-over-claim rule): the tree was clean at the session's start and
is messy now, so **something in THIS session produced it.** The origin context was lost to
compaction; the staged `models/` deletions are consistent with the earlier substrate-identity
cleanup + a pull/merge or cloud-sync event. It is **not** part of the conformance fixes in
this report. Two `models v7/` files (`training/scripts/wire_base.sh`, `xstore/README.md`) are
also staged from earlier — so "`models v7/` is entirely clean new work" is not precise either.

**Action taken: NONE.** The substrate is policy-protected (`models/` = substrate template only;
`Bible_Tokenless_POC/` = DO NOT MODIFY) and resolving 3-way conflicts there unilaterally — or
sweeping them into a commit — is exactly the overstep pattern corrected earlier (ADR-0003).
The index was **left byte-for-byte as-is** (no `reset`, no `merge --abort`, no `checkout` of
conflicted paths, no `git add -A`). A plain `git commit` here would commit the staged substrate
deletions and **exclude** the (unstaged/untracked) conformance work — so it was not run. The
commit is a separate, user-directed action; the conformance **fixes** are complete and durable
on disk regardless.

---

## E. Honest conformance verdict

- **Model proper (correctness core):** ✅ built as described. Deployed XMIND-C inference ==
  trainer (RoPE rotate-half + Q4_0 scale fixed; llama path removed; logit-level parity gate
  green). This is the load-bearing "the model is built correctly" claim and it holds.
- **Cognitive wrapper (ADR §13):** ✅ the safety path (covenant + L7 + L5→L7 coupling) is
  now fail-closed and **guarded by a production-resolution test**; deterministic-replay and
  materialization audit trails emit with real content and are surfaced in provenance.
  Remaining items are the **documented deferrals (C1–C3)** and **follow-ups (D1–D2)** above —
  not silent gaps.

No gate was marked PASS that does not hold. Deferrals are labeled as deferrals; audit-trail
records are labeled as audit-trail; only the items in §A change runtime behavior.
