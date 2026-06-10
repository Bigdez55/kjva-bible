> **CORRECTION (2026-06-04, after re-grounding in the locked ADRs).** The "DEAD" label below is
> the wrong frame for most items. **ADR-0002 §3 maps `soul_manager/*`, root `heptagon/*`,
> `governance/*`, `workspace.py`, `memory/session.py`+`episodic.py`, and the C `materialize/lineage/
> writeback/adapter_ir/cache` as CANONICAL components** of the Memory Continuity / Cognitive Control /
> Governance / Materialization systems (§2.1 lists them as active source zones; §4 names them in the
> closed-cognitive-cycle edges). They are not dead — they are **canonical-but-UNWIRED**: the task is to
> WIRE them per the ADR-0002 §4 edges + §11 workstreams, **keeping their real names** (ADR-0002 §0.2
> STOP rule + §14 forbid renaming the architecture; SoulManager is a real component, episodic is a real
> memory tier within it). Genuinely-removable items are narrower than the table implies (e.g. the
> training eval orphans). See [[project-adr-0002-canonical-mapping]]. Use the table below as a
> "what's-not-yet-CALLED" map, NOT a deletion list.

# Wired-vs-Defined / Dead-File Audit — models v7 (2026-06-03)

Six disjoint read-only auditor agents swept the whole tree (205 .py, 68 .c/.h, 10 ts,
9 .sc) with the discriminator **WIRED** (imported+called from a runtime entrypoint) /
**INTENTIONAL-SEAM or SUBSTRATE-SCAFFOLD** (ships wired-without-data by design, doc-cited) /
**DEAD** (defined, zero importers/callers, no documented reason) / **DOC-DATA**.
Source-of-truth: running code > tests > docs. No deletions made — classification only.

## Headline

Most of the tree is genuinely wired or a documented substrate seam. The real findings:
a handful of **proven-dead modules**, **partial neutralization residue in code** (not just
docs), **doc drift**, a **missing server entrypoint**, and **performance left on the table**
(NEON compiled but unused). Nothing here blocks correctness — the live inference + cognitive
+ governance + sensory paths are wired and tested (133 green, parity 3/3).

---

## A. Clear gaps — will FIX (unambiguous wire/fix, no disposition needed)

| # | Gap | Evidence | Fix |
|---|---|---|---|
| 1 | **No server entrypoint** — `api.py` has `app=FastAPI()` but NO `__main__`/`uvicorn.run`. Documented run command `python3 …/api.py` imports and exits, binds no port. | api.py (no uvicorn ref); WIRING.md:35, README:118, QUICKSTART:115 | Add `if __name__=="__main__": uvicorn.run(app,…)` |
| 2 | **Partial neutralization residue IN CODE** (ADR-0001 §4 locked) | `cognitive_pipeline.py:68-69,83,439` `AHKI_HOST/PORT`, `ahki=%s:%d` log, `COUNCIL_IPC_TIMEOUT_S`, `SOULMGR_HOST`; `heptagon/writeback.py` `SoulManager`×7 | Neutralize env-var + label names |
| 3 | **Doc drift** — 10 STALE-PATH (`models/`→`models v7/`), Council/Bookworm/SoulManager in WIRING/STRUCTURE/README/QUICKSTART, 5 OVERCLAIM run-commands | (agent-6 reconciliation table) | Reconcile docs to code |
| 4 | **`governance/interceptors.py:127` latent broken import** `from ..heptagon.registry` — unresolvable in runtime layout; would ImportError if its method were ever called | proven by agent-3 | Decouple (like covenant/gate_evaluators) |
| 5 | **`memory/cognitive_memory_verdict.py` never emitted** though ADR-0001 §8.4 says emit per turn | 0 importers; only `__main__` self-test | WIRE it per turn (conformance) |
| 6 | **AGENTS.md stale training route** → `ml-training/scripts/train_*.py` (wrong dir + MLX reference path; canonical is `training/pt/`) | training/README.md:8-28 | Reconcile (verify first) |

## B. Proven-DEAD code — needs disposition (no live importer/caller)

| Item | Status | Note |
|---|---|---|
| **ROOT `heptagon/` (8 .py)** | shadowed-dead | `import heptagon` resolves src-first to agent-side; ROOT `registry`/`harness` never in `sys.modules`. Only importer is top-level `__init__` (un-loadable: space in dir name). **Carries 174 named-member contamination hits** (Ahki/Esther/Council/Abigail). Decoupling this session removed the last reason the runtime needed it. |
| **`soul_manager/` (5 .py)** | dead/test-only | superseded by IPC episodic (:18610) + LifespanLedger + agent-side `heptagon.consolidation` |
| `memory/episodic.py`, `memory/session.py` | dead duplicates | superseded by in-agent `_sessions` + IPC |
| `workspace.py` | dead | superseded by `_sessions`; doc-vs-code divergence at api.py |
| `training/scripts/eval_byte.py`, `eval_final.py` | orphans | 0 refs; superseded by `benchmark_byte.py` + `pt/eval_clean_ppl.py` |

## C. Stub-seams / off-path — wire-or-keep judgment

| Item | Status | Note |
|---|---|---|
| `heptagon/{metacognition,invariant_engine,drift_detector}.py` | declared stubs, 0 importers, no activation | "stub" docstring but no env flag / fallback → functionally inert |
| C `harness.c`+`materialize.c`+`lineage.c` | compiled, off live path | `xmind_harness_execute` only called by a C test, never by `xmind_easy_generate`. Python side already runs the cognitive loop — C harness is redundant-or-unwired |
| C `adapter_ir.c`, `adapter_cache.c` | compiled, zero callers | adapter IR/cache layer inert (live path is lora.c→adapter_runtime) |
| C `neon_dot.c`, `neon_matmul.c` | compiled on arm64, **zero callers** | **Engine runs SCALAR even on Apple Silicon** — `xjit_*` stubs used. Real perf left on table. |
| C not-compiled (interp_llama, context_bridge, telemetry, writeback, xmind_http) | excluded by Makefile (IPC-heavy / multi-family seam), stubbed in shim/stubs.c | documented intentional exclusions |
| governance seams (decision_envelope, gate_evaluators, rationale_card, storage_envelope, boot_manifest) | loaded via eager `__init__`, no runtime symbol caller | substrate governance scaffold |
| `federation_adapter.py` + top-level `_xmind/` | Mode-B federation seam | WIRING.md-documented optional `USE_FEDERATION=1` path; latent sys.path-shadow TypeError hazard |
| `saas_translation/` (6 md), `skills/` (1 md) | doc-only | PROVENANCE.md flags saas_translation "historical, not repo identity" |

## D. Confirmed NOT dead (corrects STRUCTURE.md staleness)

- `net/`, `pal/`, `sec/`, `xisc/`, `xstore/` — **WIRED** C-contract header dirs (`ai/xmind/Makefile` `-I` flags, compiled into libxmind-core). Absent from STRUCTURE.md = doc staleness, not death.
- `ai/tts/` — WIRED (tts_bridge ← api.py voice-out; tts_engine.c built). `ai/companion/` — INTENTIONAL-SCAFFOLD (bridge hits real endpoints; reference UI unmounted by design).
- `training/`: `pt/` canonical (PyTorch), `scripts/` MLX reference (by README design); all 37 PEFT methods wire; omni 42/44 = 40 impl + 4 retrieval/corpus scaffolds.
