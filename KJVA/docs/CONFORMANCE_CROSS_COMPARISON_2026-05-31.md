The advisor confirmed my approach and gave me the critical arbitration rules. Let me write the report directly as my final response, applying the NA-vs-gap discrimination and the two-layer headline framing.

# Cross-Subsystem Conformance Audit — models v7 vs UNIFIED_MASTER_TECH_PACK.md

**Auditor synthesis of 12 independent subsystem audits.** Source-of-truth ranking: running code > test evidence > manifests/registries > prose docs.

---

## 1. Headline Verdict

**models v7 is correctly set up at the substrate and training tiers, but its top-of-stack integration layer and its entire v2 workstream are unbuilt — so it is NOT yet wired as the full spec describes.** Three distinct tiers must be separated. (a) **Operational substrate — CONFORMANT and demonstrably running:** the freestanding XMIND C engine builds clean (26 TUs, zero warnings), the F32 `model.gguf` (18,980,352 params, vocab 259, byte_offset 3) loads through `libxmind-core.dylib`, and `validate_apex.py` reaches `ai_powered=True` against it (17/17 when invoked correctly). The byte-level tokenizer (token=byte+3) matches verified provenance exactly. (b) **Training workspace — CONFORMANT and separate:** all 23 `training/scripts/` files exist and are valid; the numpy-only export chain (`safetensors_to_gguf.py`) provably produced the shipped GGUF; the Omni-PEFT **v1** baseline passes 34/34 operator tests under the mlx-equipped training venv. (c) **Integration + v2 layers — INCOMPLETE/BROKEN:** the Python FastAPI agent never bridges to XMIND (returns hardcoded f-string templates), the §12 cognitive algorithm is largely absent, covenant/gate enforcement is structurally unreachable on the served path, and the entire Omni-PEFT++ v2 "Add" workstream (8 modules), the `sensory/` subsystem, three memory modules, and the XMIND `adapter_*` C files do not exist. The substrate works; the application and v2 scaffolding around it do not.

---

## 2. Backend Truth

**The mlx misconception is corrected here as verified fact, not assumption.** There are two distinct backends, each correct for its tier:

- **Operational runtime backend = XMIND (freestanding C11/clang) + GGUF loader + numpy/scalar-NEON F32/Q4_0 matmul.** `requirements.txt` carries only `fastapi/uvicorn/pydantic/httpx/cryptography/PyYAML` — **no mlx, torch, or jax**. `pyproject.toml` `[tool.setuptools.packages.find]` includes `_xmind*/heptagon*/governance*/soul_manager*` and **excludes `ai*/tests*/training*`**. The absence of mlx from the runtime is **by design** ("we used something else" = XMIND/GGUF). `torch 2.10.0` happens to be present in the host interpreter but is never imported by runtime code — INFO only.
- **Training workspace backend = MLX (`import mlx.core as mx`).** Used **only** inside `training/` (PEFT operators, train/eval/serve scripts). This is the separate optional workspace; mlx here is correct. Operator tests run green under `../../models/training/.venv/bin/python`.
- **Application/governance/heptagon layers = pure Python** (FastAPI + asyncio IPC + stdlib + `cryptography`). No ML backend; mlx-absence is irrelevant to these slices.

**Therefore:** runtime mlx-absence is never a defect. mlx is only in scope as a defect for the `training/` test-skip hygiene (see M-rows).

---

## 3. Conformance Matrix

Counts tallied from each slice's `items[].verdict`. NA_BY_DESIGN has no column in the required 4-way split and is footnoted to keep row math exact.

| Subsystem | CONFIRMED | PARTIAL | ABSENT | DEFECT | (NA) |
|---|---:|---:|---:|---:|---:|
| 1. Training pipeline & scripts | 21 | 0 | 0 | 1 | 1 |
| 2. Omni-PEFT **v1** operators & registry | 5 | 2 | 1 | 1 | 2 |
| 3. Omni-PEFT **v2** / §11.1 "Add" gap | 0 | 2 | 9 | 0 | 1 |
| 4. XMIND C inference engine | 6 | 1 | 1 | 0 | 0 |
| 5. Heptagon L1–L7 layers | 12 | 7 | 0 | 3 | 0 |
| 6. Cognitive pipeline, agent & memory | 5 | 1 | 6 | 7 | 0 |
| 7. SoulManager & memory tiers / encryption | 5 | 3 | 0 | 1 | 2 |
| 8. Governance / Covenant / decision gates | 5 | 2 | 1 | 6 | 0 |
| 9. Sensory evidence modules (§11.1 Add) | 0 | 0 | 7 | 0 | 1* |
| 10. Tests, acceptance & backend reconciliation | 6 | 5 | 0 | 3 | 1 |
| 11. Companion / UI provenance | 4 | 4 | 3 | 0 | 0 |
| 12. Identity-neutrality, taxonomy, ADRs | 7 | 1 | 0 | 4 | 0 |
| **Totals** | **76** | **28** | **35** | **26** | **9** |

\*Slice 9's single INFO row is a scope-defer note, not a true backend-NA. **Arbitration applied (see §5):** Slice 2 locally labeled the 8 v2 modules NA_BY_DESIGN *for the v1 contract*; at whole-build level Slice 3 correctly scores them ABSENT/CRITICAL/MAJOR. This report treats them as **gaps**, not NA.

---

## 4. CRITICAL & MAJOR Findings

Filtered on severity ∈ {CRITICAL, MAJOR}. **Mapping rule:** ABSENT→G (gap); DEFECT→M (mishap); PARTIAL→G if incomplete-build, M if built-but-diverges. CRITICAL marked ‼.

| ID | Subsystem | Requirement | Verdict | Evidence | Action |
|---|---|---|---|---|---|
| ‼ M1 | Governance (8) | CovenantEnforcer gates every request before XMIND dispatch | DEFECT | `api.py:288` calls non-existent `_covenant_enforcer.evaluate()` + `EnforcementAction.HARD_STOP` + `.reason` (enum has only ALLOW/BLOCK/WARN; method is `enforce()`); all 3 raise AttributeError, swallowed by bare `except Exception` (:296), falls through to inference. BLOCK branch unreachable — ABSOLUTE requests are NOT blocked. | Replace with `enforce()`; gate on `action==BLOCK`; use `summary()`; narrow the bare except so it fails loud. Fix is in the **caller** `api.py` (NOT the DO_NOT_MODIFY `covenant_enforcer.py`). |
| ‼ M2 | Governance (8) | §25.6 claims this exact api.py bug was "found and corrected" | DEFECT | `api.py:288-296` **still** contains `.evaluate()`, `HARD_STOP`, and the swallowing except. Running code contradicts the prose fix-claim. Spec-integrity / false-claim finding (code > docs). | Apply the fix §25.6 claims landed; treat §25.6's "corrected" assertion as false until M1 is fixed. |
| ‼ M3 | Cognitive pipeline (6) | §4.3 Routing to XMIND — agent produces model-backed inference | DEFECT | `agent._process()` (agent.py:77-150) is a hardcoded if/elif of f-string templates; `a.chat('s1','who are you')` returned a canned 197-char string, not inference. `_xmind_glue.py` (only XMIND bridge in tokenless-agent) is an uncalled generic template (imported by nothing). Served `/v1/chat` returns templated text — GGUF artifact never bridged in the Python path. | Wire a real XMIND/GGUF bridge into `TokenlessAgent.chat()` (adapt `_xmind_glue` `deliberate_*`), replacing the template branches. |
| ‼ M4 | Cognitive pipeline (6) | §12 CognitivePipeline algorithm (evidence→gate→memory→reflex→route→adapters→XMIND→review→writeback) | ABSENT | grep: no `build_evidence_envelope`, no `DecisionGateChain` in path, no `SoulManager.retrieve`, no Heptagon⇄SoulManager reflex, no `OmniPEFT.route_adapters`, no recursive REVIEWING, no `record_lineage/evaluate_writeback`. Actual pipeline is flat IPC shard-fetch→`agent.chat`→fire-and-forget telemetry. §11.2 items 9-13 confirm never built. | Implement §12 or mark §12 future. Minimum: wire DecisionGateChain (exists, unwired) + a SoulManager retrieve/commit reflex. |
| ‼ G5 | Omni-PEFT v2 (3) | §11.1 ADD `adapter_ir.py` (canonical AdapterIR/AdapterIROp, 16 op_kinds, compiler emission) | ABSENT | No `adapter_ir.py` in either peft tree; zero imports. §8.4 fully specifies it; §20.2 exit requires LoRA/DoRA/IA3/AdaLoRA/XLORA/GRALORA/ALORA/TRAINABLE_TOKENS→AdapterIR. Central dependency for genome_v2 + XMIND runtime. | Implement IR schema + 8+ emitters + validator + hash. Scope large (~400-700 LOC). |
| ‼ G6 | Tests/acceptance (10) | Canonical §22 acceptance file collected by default runner | DEFECT | `pytest tests/ --collect-only` finds only the 7 smoke tests; `validate_apex.py` doesn't match `test_*.py`, and there is **no** `[tool.pytest.ini_options]`, conftest, or pytest.ini. Bare `pytest` → "39 failed, 7 passed" (recurses into training mlx tests); §22 sweep silently never runs. CI green while skipping the entire acceptance contract. | Rename `validate_apex.py`→`test_validate_apex.py` (or add `python_files` override) + `testpaths=['tests']`. Classified DEFECT→treated as M-class wiring; listed here for blast-radius. |
| ‼ G7 | Cognitive pipeline (6) | §12 post-inference lineage + writeback recorded by pipeline | ABSENT | `cognitive_pipeline.execute()` ends with fire-and-forget telemetry; no `record_lineage`, no `evaluate_writeback`, no `SoulManager.commit`. heptagon `lineage.py`/`writeback.py` exist but not imported by pipeline. | Invoke lineage.record + writeback.evaluate + SoulManager.commit at pipeline end per §12. |
| ‼ G8 | Companion (11) | §11.2 step 19 GEN Companion provenance display | ABSENT | grep across all `*.ts/*.tsx`: zero of `heptagon_active/shard_count/route_reason_code/l7_severity/writeback/memory_used/deliberation_depth/turn_id`. `action-trace.ts` renders an action lifecycle, not the §8.7/§9.19 pipeline-stage provenance panel. §10.2 provenance object dropped UI-side. | Implement a provenance panel rendering the §8.7 allowed surface from the §10.2 `response.provenance` object. |
| M9 | Heptagon (5) | Spec path `ai/genesys-ai/src/heptagon/` resolves to code | DEFECT | `find ai/genesys-ai` → exit 1 (does not exist). Real code at `ai/tokenless-agent/src/heptagon/`. Every §3/§4.3/§20.x/Appendix B path citation is stale. | Update spec §3/§4.3/§20.x/Appendix B to cite `ai/tokenless-agent/src/heptagon/` (or rename dir). |
| M10 | Heptagon (5) | L7 invariant severities match Appendix B | DEFECT | 4 divergences: `HALLUCINATION_GUARD`=CRITICAL (enforcement.py:334) vs spec VIOLATION "Redact match" — CRITICAL triggers `hard_stop`, so a fabricated DOI/ISBN hard-stops instead of redacting (behavioral defect). Also BUDGET_COMPLIANCE/AUTHORITY_BOUNDS/COVENANT_COMPLIANCE mismatched. | Set HALLUCINATION_GUARD→VIOLATION+redact; align the other 3 or amend Appendix B. |
| M11 | Cognitive pipeline (6) | L4 state machine drives the chat turn | DEFECT | FSM is event-driven; `agent.py` calls `transition('LISTENING'/'ROUTING'/'REVIEWING'/'IDLE')` passing **state** names as **events** → every call raises ValueError, swallowed by bare except. FSM never leaves IDLE; GENERATING never emitted. | Pass valid event names; remove bare excepts. |
| M12 | Cognitive pipeline (6) | L5 evaluation + L6 calibration live in path | DEFECT | `CycleEvaluator` exposes only `evaluate()` but agent calls `.record()/.latest_metrics()` (AttributeError, swallowed). `ParameterCalibrator()` construction raises → `calibrator=None`; L6 block guarded out. L5/L6 dead in path. | Align agent to actual APIs / fix constructor; remove silent excepts. |
| M13 | Cognitive pipeline (6) | L7 invariant enforcement BEFORE inference | DEFECT | `enforcer.check_all` runs at agent.py:398 **after** `super().chat()` at :354 — post-inference, contradicting §4.3 "before inference"; receives only {agent_id, latency, length}, not request context. | Move pre-check before model call; feed inbound context. |
| G14 | Cognitive pipeline (6) | §11.1 memory modules `experience_atom.py` / `recall_trail.py` / `lifespan_ledger.py` | ABSENT | None exist in `memory/`; §11.2 items 11-12 list unbuilt. Sibling modules from the same §11.1 Add block (heptagon/, memory/session+episodic) DO exist → genuine omission. | Add the 3 modules per §11.1 or scope to a future milestone. |
| G15 | Cognitive pipeline (6) | §4.3 Stage-2 context retrieval via `episodic.py`+`session.py` | DEFECT | Both modules complete + import clean, but the running `_stage_fetch_context` fetches shards via Ahki IPC and **never imports them** — matrix mapping ≠ running code. | Wire EpisodicMemory/SessionMemory into Stage-2, or correct §4.3:8503. |
| G16 | Governance (8) | Tier-3 gate chain enforced in live request path | ABSENT | `create_default_gate_chain`/`gate_evaluators` referenced only by `governance/__init__.py` re-export; `cognitive_pipeline.py`/`api.py` have zero DecisionEnvelope calls. Tier-3 is dead code w.r.t. served runtime. | Wire `GateChainExecutor.evaluate(envelope)` into pipeline after the covenant gate per §5.5. |
| M17 | Governance (8) | `create_default_gate_chain()` builds a wired 7-evaluator chain | DEFECT | Running it → `TypeError: HeptagonHarness.__init__() missing 'member_id'`. `_StubHarness` (gate_evaluators.py:42) doesn't override `__init__`. Documented factory non-instantiable. | Give `_StubHarness` an `__init__` supplying member_id; add a test that calls `.evaluate(env)`. |
| M18 | Governance (8) | Unregistered BLOCKING gate must not silently approve | DEFECT | `decision_envelope.py:219` ternary collapses to `ALLOW` on both branches → a missing blocking-gate evaluator passes silently (fail-OPEN in core executor). `interceptors.py:47` builds a bare executor with no evaluators → every envelope approved. | For missing blocking-gate evaluator return DENY/STEP_UP (fail-closed); default interceptors to the real chain. |
| G19 | XMIND C (4) | §11.1 XMIND `adapter_ir.c`/`adapter_runtime.c`/`adapter_cache.c`/`adapter_telemetry.c` + 2 headers | ABSENT | grep returns nothing; no `*adapter*` file in include/src. **Bounded:** §11 is an "Add/modify files" plan; §25.6 passed 9/9 without them; base single-adapter capability already exists in `lora.c` (load/find/apply_delta, compiled+linked). | Planned forward work, not a build defect. To close §11.1 literally, add the 6 files; `adapter_runtime.c` can wrap existing `lora.c`. |
| G20 | Omni-PEFT v2 (3) | §11.1 ADD `ontology.py` / `adapter_algebra.py` / `adapter_genome_v2.py` / `tournament_v2.py` / `layer_plasticity.py` / `sensory_plasticity.py` / `determinism.py` | ABSENT | None present in either peft tree; zero references. §11.2 steps 2-8/13 unrealized. genome_v2 + algebra depend on G5 (adapter_ir). | Implement the v2 module set per §8.4-8.6/§5.2; medium-large each. Sequenced after G5. |
| G21 | Omni-PEFT v2 (3) | §11.2 step3 registry upgraded to §4.3 ontology schema | ABSENT | `omni_training_registry.json` entries carry only v1 keys; none of `adaptation_kind/operation_kind/plasticity_profile/sovereignty_profile/proof_obligations`. grep: 0 hits. | Migrate ~42 entries to §4.3 schema + validator. |
| G22 | Sensory (9) | §11.1 `sensory/evidence.py` + `router.py` + `home_security.py` + `build_evidence_envelope()` + `sensory_anchors/scope` wiring + test | ABSENT | No `sensory/` dir anywhere; repo-wide grep "sensory" = 0 non-doc hits. Sibling §11.1 modules (heptagon/, memory/) DO exist → genuine omission. (`training/peft/router.py` is unrelated PEFT router.) | Create the `sensory/` module set + envelope wiring + `test_sensory_envelope.py`. |
| G23 | SoulManager (7) | §12.1 Heptagon⇄SoulManager reflex packets (RecallContextFrame, MemoryStructureVerdict) — "mandatory" | PARTIAL | Named dataclasses appear only in `docs/_archive/`; grep of `ai/` = 0. A functional quality-gated writeback exists (writeback.py, QUALITY_FLOOR 0.30) but the bidirectional structured-reflex **contract** is unbuilt. | Implement the 2 frames + wire into writeback flow, OR downgrade §12.1 "mandatory" to deferred Part-IV. |
| M24 | SoulManager (7) | 5 named locked tiers (register/session/episodic/semantic/archival; LOCK-006) | DEFECT | `VALID_BUCKETS = {persistent, episodic, context, meta}` — only `episodic` matches a spec name. `test_01` silently redefines to "≥4 buckets". §25.1 "[x] 5 canonical tiers" is an overclaim vs code. | Realize the 5 locked names, or amend spec/§25.1 with an authorized mapping + fix test_01. |
| M25 | Identity (12) | §1: model has no name/persona/domain allegiance; README claims "identity-neutral" | DEFECT | `constitution/*.md` presents 8 named members (Ahki/Esther/Ruth/Sarah/Abigail/Ezri/Magen/Cherev) as active "Constitutional Law — Immutable" (65 occurrences); spec §0.1A demotes them to reference patterns. Contradicts README:4. | Archive/relabel constitution member tables as non-active reference per §0.1A; correct neutrality claim. |
| M26 | Identity (12) | No domain allegiance — covenant rules functional, no scripture basis | DEFECT | `covenant_enforcer.py` maps COV-001..007 to Proverbs verses; populated `scripture` field emitted in violation messages; `governance.sc` "8 Covenant Rules with Scripture bindings — ABSOLUTE". Spec covenant table (L681) has NO scripture column. Residual Biblical-domain contamination in a DO_NOT_MODIFY surface. | Strip scripture fields/citations, replace with neutral rationale (allowed under DO_NOT_MODIFY.md "Current Exception"); IDs/severities unchanged. |
| M27 | Identity (12) | Reconciliation #5: federated multi-member resolved to single-neutral-process | PARTIAL | Resolved by ADR-S49-03 **reinterpretation**, not conforming code: `_xmind/client.py` still requires `MEMBER_NAME`, loads `personas/<MEMBER_NAME>.txt`. Federated surface preserved; report's "in favor of master spec" overstates. | Mark #5 "resolved by reinterpretation; code retains federated MEMBER_NAME surface"; ship no member persona as default. |
| G28 | Heptagon (5) | PII_LEAKAGE / verifier screens + redacts outgoing responses | PARTIAL | `_check_pii` screens `ctx['log_output']` only, not `ctx['response']`; CRITICAL hard-stops rather than redacting per §4.4.3. In agent path, verifier failure only **logs**, no redaction. | Screen `response`; implement redact-full-response action instead of hard-stop. |
| G29 | Heptagon (5) | route_engine §20.3 contracts (reject-on-budget, degraded, DriftIndex, Covenant non-bypass) | PARTIAL | grep covenant/degraded/drift in route_engine = 0; contracts enforced (if at all) at caller, not the module. | Add §20.3 guards into route_engine or amend §20.3 to locate them at the pipeline caller. |

---

## 5. NA_BY_DESIGN (intentionally not applicable — NOT gaps)

Per the arbitration rule (backend-inapplicable = NA; §11.1-scheduled = gap), only these are genuinely NA:

1. **Runtime mlx/torch/jax absence** (Slices 1,2,10) — XMIND/GGUF+numpy is the operational backend; `pyproject` excludes `training*/ai*`. `torch 2.10.0` present in host but never imported by runtime code.
2. **training/ mlx-gated scripts not importing in audit env** (Slice 1) — `train_byte/train_peft/benchmark_byte/eval_*/export*/generate/model/serve_raw_model/train` fail only on `ModuleNotFoundError: mlx`; valid by inspection, run under the training venv.
3. **`training/tests/` 39 failures = environmental** (Slice 1) — every failure is mlx-absence; logic provable only with mlx installed in the optional workspace.
4. **SEC-001 (raw-message-never-persisted) and SEC-002 (session-id hashing) inside SoulManager** (Slice 7) — content contracts enforced upstream in `cognitive_pipeline.py`/`api.py` (`_hash_session = sha256[:16]`); SoulManager correctly encrypts-and-stores whatever it's handed. Out-of-module by design.
5. **ADR-S49-01 "may use Python/MLX"** (Slice 12) — a training/optional-workspace statement, consistent with the runtime reframe.

> **Explicitly NOT NA (corrected from Slice-2's local label):** the 8 Omni-PEFT v2 modules, registry ontology upgrade, `sensory/` subsystem, the 3 memory modules, the §12 algorithm, and the XMIND `adapter_*` C files are **applicable forward-work gaps** (§11.1 "Add" block, same block whose sibling modules were built). Slices 3, 8, and 9 confirm this in their own words ("genuine omission, not by-design exclusion"; "planned forward work"). They appear in §4/§6, not here.

---

## 6. Prioritized Action Plan (ordered by severity × blast-radius)

### (a) Safe immediate fixes — small diffs, high blast-radius, no new architecture
1. **Fix covenant wiring (M1/M2).** In `api.py:288` call `enforce()`, gate on `action==BLOCK`, use `summary()`, narrow the bare except. One-line-class change in the **caller** (not the DO_NOT_MODIFY enforcer). Restores fail-closed safety on the only request path; closes the false §25.6 "corrected" claim.
2. **Fix pytest collection (G6).** Rename `validate_apex.py`→`test_validate_apex.py` (or add `[tool.pytest.ini_options] python_files=['test_*.py','validate_*.py']`) + `testpaths=['tests']` + `norecursedirs=['training']`. Makes the §22 contract actually run under CI; stops "green while skipping everything."
3. **Fix state-machine/L5/L6/L7 wiring (M11/M12/M13).** Pass event names not state names; fix `ParameterCalibrator` constructor; align CycleEvaluator API; move enforcement pre-inference; **remove the bare excepts** so failures surface. Reanimates the dead L4-L7 cognitive path.
4. **Fix gate-chain fail-open + factory (M17/M18).** Give `_StubHarness.__init__` a member_id; change `decision_envelope.py:219` so missing blocking-gate→DENY/STEP_UP; default interceptors to the real chain.
5. **Severity reconciliation (M10)** + **PII response screening (G28)**: set HALLUCINATION_GUARD→VIOLATION+redact, screen `response` not just `log_output`.
6. **Identity de-contamination (M25/M26/M27)** under DO_NOT_MODIFY.md "Current Exception" (name/origin-language cleanup, behavior-neutral, + smoke-test pass): strip scripture fields, relabel constitution member tables as non-active, correct README/PROVENANCE neutrality claim and reconciliation-#5 wording.
7. **Doc-sync (Slice 1 DEFECT, Slice 9/5 path drift):** update spec prose `ml-training/`→`training/`; cite `ai/tokenless-agent/src/heptagon/`; fix README "37"→"35" PEFT count. Apply `SKILL_DOCS_ARCHITECTURE_SYNC_001`.

### (b) Small net-new — bounded modules, wire existing parts together
8. **Wire the §12 spine into `cognitive_pipeline.execute()` (M4/G7/G16):** thread DecisionGateChain (exists) + SoulManager retrieve/commit reflex + lineage.record + writeback.evaluate. Most pieces exist; this is integration glue, not new architecture.
9. **Wire Episodic/Session memory into Stage-2 (G15)** or correct §4.3 to the Ahki-IPC mechanism.
10. **Companion provenance panel (G8)** + §10.2 object consumption — bounded UI module once a backend emits provenance.
11. **Add the 3 alignment-trainer tests** (kto/orpo/ppo_rlhf) + registry-count reconciliation note (Slice 2 PARTIALs); add `training/programs/kjv_omni_program.yaml` or repoint the dangling spec reference.

### (c) Large net-new — requires explicit go (estimate scope)
12. **Agent→XMIND inference bridge (M3)** — the headline integration gap; medium (adapt `_xmind_glue`, replace template branches, end-to-end test).
13. **Omni-PEFT++ v2 workstream (G5/G20/G21)** — large: `adapter_ir.py` (~400-700 LOC, central dep) → then `adapter_algebra`/`adapter_genome_v2`/`tournament_v2` (~400-600 LOC each) + `ontology`/`layer_plasticity`/`sensory_plasticity`/`determinism` (~150-500 LOC each) + registry §4.3 migration + proofs/. Sequenced behind adapter_ir.
14. **`sensory/` subsystem (G22)** — evidence/router/home_security + envelope wiring + tests (medium).
15. **3 memory modules (G14)** — experience_atom/recall_trail/lifespan_ledger (medium).
16. **§12.1 Heptagon⇄SoulManager reflex contract (G23)** — 2 dataclass frames wired to writeback (medium), or formal deferral.
17. **XMIND `adapter_*` C files (G19)** — only if multi-adapter IR runtime is needed; single-adapter LoRA already works (`lora.c`). 
18. **Latency SLA** (Slice 10 PARTIAL): §22 P99<5000ms unmet (~13s/turn, scalar-CPU F32) — standing qualification; needs SIMD/NEON, Q4 path, or larger served model (no engine change required for F32).

---

## 7. Completeness Boundary

- **Searched / found:** all 12 declared subsystems were inventoried at file level (find/ls/grep across `training/`, `ai/xmind`, `ai/tokenless-agent`, `ai/companion`, `governance/`, `soul_manager/`, `constitution/`, `adr/`, root configs). File presence, names, and LOC were primary-source verified by the sub-audits.
- **Verified-run (executed):** XMIND `make clean && make` + `make test` (clean, smoke PASS); `safetensors_to_gguf.py` provenance manifest (matches reframe exactly); `validate_apex.py + test_substrate_smoke.py` (17 passed, 86s, `ai_powered=True` via dylib); `omni_training_program.py validate` (pass:true, 44 methods); `test_peft_operators.py` 34/34 + `test_peft_imports.py` 5/5 under the mlx venv; standalone `--help` on 8 numpy-only CLIs; live AES-256-GCM round-trip + tamper-rejection; `create_default_gate_chain()` (raised TypeError — captured); `agent.chat()` (returned canned template — captured); FSM/CycleEvaluator/Calibrator wiring probed at runtime (AttributeError/ValueError captured).
- **Not-run / inspection-only:** mlx-gated `training/` scripts (valid by `py_compile`, not imported — env lacks mlx, by design); companion `tsc/vite build` (node_modules absent — typecheck NOT executed); `training/tests/` logic (mlx-absent — failures are environmental).
- **Qualified:** (i) NA-vs-gap for the v2 workstream was **arbitrated** at whole-build level against Slice-2's local v1-scope NA label — this report scores them gaps. (ii) §22 P99 SLA is unmet but disclosed as throughput-bound, not architectural. (iii) Several acceptance assertions are weaker than spec (5-tier→≥4 buckets; top-7/≤1800 enforced by the test's own slice not the SUT; bounded-re-entry is a static table check, not a driven loop) — counted as PARTIAL, not pass. (iv) Cross-slice scope handoffs (sensory §7.1 method-form, byte+3 tensor detail, XMIND adapter_* vs peft adapter_ir) were noted by each slice and not double-audited to avoid straying.