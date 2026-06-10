# Full Gap Ledger — every-file deep audit (2026-06-04)

Exhaustive per-file pass of all **298 code files** across every folder of `models v7`, by 6 deep-audit
agents, checked against the LITERAL ADR-0001/0002 text (spec-literal discipline). Each gap is
`severity · status · file · what · fix`. **Status: CLOSED / PARTIAL / OPEN.** This is the honest
accounting — not everything is closed yet; the larger architectural items are OPEN with a concrete
next step, not glossed.

## CRITICAL

| status | file | gap | resolution |
|---|---|---|---|
| **CLOSED** | `ai/xmind/shim/stubs.c` | xsec "SHA-256" was an FNV-1a fold behind a SHA-named/security API → r1_per tamper gate, §8.3 weight hash, continuity attestation rode a non-crypto hash | Real FIPS 180-4 SHA-256 (self-contained). Verified: FIPS `abc` vector + GGUF==`shasum`. (commit 6a51bf6) |
| **OPEN** | `training/peft/router.py`, `model.py` | §9.2 adapter-activation trust chain (sign→base-hash→scope→conflict→DPR) is written in `v2/adapter_genome_v2.py` but **called by nothing** on the live PEFT activation path | Wire `AdapterGenomeV2.verify()` + base-hash + scope + numeric conflict-threshold + emit a DeterminantProbabilityRecord into `route_for`/`HierarchicalRouter.route` before activating each candidate |
| **OPEN** | `training/peft/alignment/sft.py` + `scripts/train_peft.py:120-121` | `distill_logit`/`distill_sequence` both alias `SFTTrainer` (plain cross-entropy) — logit/sequence distillation is **not implemented**; these IDs silently run vanilla SFT | Implement a `DistillationTrainer` (KL(student‖teacher) at temperature T; teacher-forced sequence loss) and repoint the 2 registry entries — OR make them raise so they can't silently mislabel |

## HIGH

| status | file:line | gap | resolution |
|---|---|---|---|
| **CLOSED** | `agent.py:678` | `_emit_memory_verdict` checked `pkt.shards` (nonexistent) → `used_memory` always False → `route_type` always "direct" | use `retrieved_experience_ids`; verified flips to `memory_mediated` (6a51bf6) |
| **CLOSED** | `training/peft/registry.py:107` | `promote()` skipped the §9.2-rule-7 rollback-pointer check | require `genome.rollback_previous` (6a51bf6) |
| **OPEN** | `ai/xmind/src/adapter_runtime.c:62-111` | §9.2 base-hash/authority-scope/conflict are PROXIED not VERIFIED (TODOs at :67/:81/:94) — a validly-shaped adapter for the WRONG base would admit | surface `content_hash`/`base_checkpoint`/`scope`/`signature` from the adapter_genome_v2 block onto `xmind_lora_t`; assert + verify HMAC in `gov_admit` before binding |
| **OPEN** | `ai/xmind/src/xmind_easy.c:117` | §8.3 "No model artifact loads without hash verification" — engine now REPORTS a real sha256 but does not REFUSE on mismatch (no expected hash passed in) | add an `expected_sha256` param to `xmind_easy_init`/load that refuses on mismatch (verify-before-materialize) |
| **OPEN** | `training/peft/model.py` | prefix/prompt operators (`prefix_tuning`,`prompt_tuning`,`p_tuning`,prefix half of mam/unipelt) have real math but are **never consumed** by `OmniPEFTBlock` (additive-delta only) | wire `apply_prefix_to_attention`/soft-prompt concat into the base attention forward, or mark these methods unsupported in METHOD_REGISTRY |
| **OPEN** | `training/peft/conflict.py:176` | `compute_delta_cosine_similarity` (the only NUMERIC conflict-threshold primitive) is defined-not-called | call it in `prune()`; reject pairs below a configured cosine threshold |
| **OPEN** | `training/scripts/train_peft.py:648-657` | MLX PEFT fail-OPEN: `np.load` can't read `.safetensors` → caught → **trains on RANDOM init** (no raise). `omni run-peft` routes here | load via `safetensors.load`, read config from the ckpt, fail-CLOSED on load error; or route omni to canonical `pt/train_peft.py` |
| **OPEN** | `training/scripts/serve_raw_model.py:64` | no byte serve path — requires SentencePiece `tokenizer.model` byte exports never produce; the byte wire-flow ends in a server that crashes | add a byte-mode branch keyed on `byte_vocab.json` using the byte+3 contract |
| **OPEN** | `_xmind/` (top) vs `ai/tokenless-agent/src/_xmind/` | two distinct `_xmind` packages; which binds depends on cwd/sys.path — a path-order change silently swaps engines | rename top-level → `xmind_federation` (or merge) so they can't collide |
| **OPEN (5 of 18)** | `tests/` | ADR-0002 §12 required tests: 1/18 present by name; 12 behaviorally covered under other names; **5 genuinely uncovered**: `adr_immutability`, `no_archive_taxonomy_import`, `adapter_conflict_threshold`, `no_direct_memory_write_from_adapter`, `l7_critical_manual_reset` | add the 5 real tests; alias/rename the 12 covered ones to satisfy the §13 literal naming gate |
| **OPEN** | CI / suite | a green `pytest` with `libxmind-core` unbuilt SKIPS the entire C-engine set (generation/adapter/parity) — green is hollow on the core path | CI must `make` ai/xmind and treat those skips as FAIL in the verify lane |

## MEDIUM (spec-literal record shapes + enforcement)

| status | file | gap | resolution |
|---|---|---|---|
| **OPEN** | `memory/experience_atom.py` | ExperienceAtom missing ADR-0001 §8.2 fields: `source_hashes`,`lineage_ref`,`contradiction_links`,`correction_history`,`privacy_class`,`retention_mode` | add fields + populate `source_hashes`/`lineage` on `create` |
| **OPEN** | `memory/recall_trail.py` | the ADR-0002 §7.3 RecallTrail (`trail_id`,`expansion_depth`,`stop_reason`,`confidence_before/after`,…) is never constructed | emit a §7.3 RecallTrail from `jog_my_memory`/`_memory_recall` with real `expansion_depth`/`stop_reason` |
| **OPEN** | `sensory/evidence.py` | EvidenceEnvelope missing §6.3 fields: `source_kind`,`source_id_hash`,`timestamp_ns`,`retention_hint`; uses `salience` where §6.3 says `confidence` | add the 4 fields + a `confidence` alias |
| **PARTIAL** | `materialization/materialization_record.py` | implements ADR-0001 §11.2 shape, not ADR-0002 §8.3 field NAMES (inter-ADR conflict). The model_artifact record populates §8.3 VALUES (source_hash/materialized_at/tensor_roles/rollback) via the §11.2 field names | add §8.3 field aliases, or a new ADR reconciling §8.3↔§11.2; the values are present (model_artifact verified) |
| **PARTIAL** | `heptagon/determinant_record.py` | implements §10.1 not §10.2 field names (inter-ADR conflict); no §10.2 consumer reads the missing names | reconcile via a new ADR or add §10.2 aliases |
| **OPEN** | `training/scripts/validate_adapter.py:156-193` | `weights_exist` is warning-only and nests the weight checks under it → a weightless adapter promotes with `--force`; the docstring-promised "shape check" is unimplemented | make `weights_exist` error-severity; hoist weight/size checks; implement or drop the shape-check claim |
| **OPEN** | `training/scripts/omni_training_program.py:300` | `run` subcommand delegates to `scripts/run_retrain.py` which does not exist | create `run_retrain.py` or repoint to `pt/train_byte.py` |
| **OPEN** | `governance/gate_evaluators.py:53` | `create_default_gate_chain()` non-instantiable (StubHarness lacks `cycle()`) — the 7-gate Council chain is dead-on-arrival IF called (scaffold; never on the live path) | give `_StubHarness` both an arg-tolerant `__init__` and a neutral `cycle()`; add a test |
| **OPEN** | `ai/xmind/src/gguf_reader.c:248` | `arr_count * esz` size math has no upper bound → overflow / huge seek on a crafted GGUF | bound-check `arr_count` vs remaining file size before the multiply |

## LOW (hygiene / labels / docs / dead)

| status | file | gap |
|---|---|---|
| **CLOSED** | `cognitive_pipeline.py:537` | `context_available = len(shards)>0 or True` constant-True → removed `or True` (6a51bf6) |
| **OPEN** | `api.py:374` | `/v1/heptagon/status` labels invert L4/L7 (reports L4_enforcement/L7_verification; ADR has L7=enforcement) |
| **OPEN** | `heptagon/node_registry.py` | instantiated + status-advertised but never queried on the turn path; its `LAYERS` taxonomy matches neither ADR-0001 §6 nor the status labels (3 namings) |
| **OPEN** | `federation_adapter.py` | dead AND broken (calls `XMindClient(member_name=…)` which the real client doesn't accept) |
| **OPEN** | `_xmind/client.py:60`, `__init__.py` | "Citadel Council" persona string + "council" docstrings violate neutral-taxonomy (top-level federation template) |
| **OPEN** | `soul_manager/soul_manager.py:353` | XStore ctypes path sets no `argtypes`/`restype` (size_t truncation); get/put/delete mask transient errors as "absent" (dead pkg) |
| **OPEN** | `ai/companion/src/agent-bridge.ts:89`, `global.d.ts:7` | doc typos: `:8090`→`:8091`; `/healthz`→`/v1/health` |
| **OPEN** | `ai/xmind/src/quantize.c:247` | K-quant "simplified layout" — risk for non-Q4_0 quants (KJVA is Q4_0, parity-verified, not live) |
| **CONFIRMED ORPHANS** | `training/scripts/eval_byte.py`, `eval_final.py` | 0 refs repo-wide (superseded by benchmark_byte/eval_clean_ppl) |

## Verified NON-gaps (cleared — do not re-flag)
- The 37 PEFT operators implement genuine method-specific math (no stub operators).
- `pt/` canonical PyTorch path COMPLETE (real loop, parity-locked 18.98M arch, real ppl).
- Covenant enforcer: all 8 rules evaluated (none stubbed), fail-closed, CALLED live.
- `drift_signal` computes a real weighted drift_index, CALLED live.
- `soul_manager` AES-GCM is REAL (Tier-1 xsec FFI / Tier-2 `cryptography`, fail-closed); but the
  Python package is NOT called by the live runtime (memory continuity is agent-side).
- `ai/tts/tts_engine.c` is a real formant synth; companion `tsc --noEmit` clean.
- `net`/`pal`/`xnet` shims are real POSIX; `sec`/`xstore`/`xisc`/context/telemetry are honest no-ops.

## Closure status (updated as clusters land)
**CLOSED (11):** real SHA-256 CRITICAL · shards route_type bug · context_available · promote rollback
· EvidenceEnvelope §6.3 · companion doc typos · **§9.2 PEFT-router admission gate** (rules 1-3 now
CALLED; +`test_adapter_genome_scope.py`) · **ExperienceAtom §8.2 fields** · **train_peft fail-CLOSED**
(was silent random-weights) · heptagon/status L4/L7 label inversion · flaky `test_text_path_is_unchanged`.

**PARTIAL (2):** C `adapter_runtime.gov_admit` §9.2 base/scope — the Python router half is done; the
live-C half needs a cross-side contract (training writes the base GGUF sha; engine compares to its
weight_sha256) — deferred rather than risk breaking adapter loading. · `conflict.compute_delta_cosine_similarity`
needs the loaded weight-deltas at prune time (MLX) — wired-as-available, not yet on the metadata-only path.

**CLOSED (19):** + the 5 ADR-0002 §12 acceptance tests (adapter_genome_scope, adr_immutability,
no_archive_taxonomy_import, no_direct_memory_write_from_adapter, l7_critical_manual_reset) ·
_xmind Citadel-Council taxonomy neutralized · validate_adapter weight-gate now blocks weightless
adapters (+accepts safetensors) · gguf_reader arr_count overflow guard.

**OPEN (~12):** distillation (mislabeled SFT → real KL) · prefix/prompt operator wiring into the
attention forward · serve byte path · _xmind two-package rename · gate_evaluators StubHarness.cycle()
(scaffold) · RecallTrail §7.3 construction · MaterializationRecord §8.3 / DeterminantRecord §10.2 field
aliases · omni run_retrain.py · node_registry / federation_adapter disposition · soul_manager XStore
argtypes · CI build-gate (treat C-test skips as FAIL). Each has a one-line next step above. Closing in
clusters, in order; not rushed.
