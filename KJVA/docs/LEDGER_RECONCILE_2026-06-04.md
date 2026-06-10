# Ledger Reconciliation — FULL_GAP_LEDGER vs code at HEAD (2026-06-04)

READ-ONLY reconciliation of every OPEN/PARTIAL row in `docs/FULL_GAP_LEDGER_2026-06-04.md`
against the code at HEAD (`5dd78fd`). Source-of-truth order: running code > test evidence >
manifests > docs. Classification bar: **CLOSED** = fix exists AND is reachable/CALLED on the
relevant path (call-site cited); **PARTIAL** = which half is missing stated; **OPEN** = not done.
Commit messages were NOT trusted — every claim is traced to a file:line with DEFINED/IMPORTED/CALLED.

## Per-row verdicts

| # | item | status | evidence (file:line · DEFINED/IMPORTED/CALLED) | what's-left (≤1 line) |
|---|------|--------|-----------------------------------------------|-----------------------|
| 1 | §9.2 adapter-activation trust chain in peft router/model | **PARTIAL** | `training/peft/router.py:177` `_admit_genome` CALLED by `route()` @145; `route()` CALLED @`model.py:331` (OmniPEFTModel/MLX path). Enforces rule2 base-model **string** compare @189, rule3 scope @192, rule1 signed-presence @196. Does NOT call `AdapterGenomeV2.verify()` (HMAC, DEFINED `v2/adapter_genome_v2.py:64`), no numeric conflict, no DPR emit. | wire `AdapterGenomeV2.verify(key)` + numeric conflict (item 6) + emit a DeterminantProbabilityRecord; note route() is exercised in OmniPEFTModel (MLX) — verify it runs live vs test/eval-only |
| 2 | distill_logit/sequence real KL vs aliased SFT | **CLOSED** | Real KL/teacher-forced math DEFINED `peft/alignment/distillation.py:100,173`. Registry repointed `train_peft.py:132-133` → `DistillationLogitTrainer`/`DistillationSequenceTrainer` (no longer SFT). `run_alignment_training` DEFINED @483, CALLS the trainers @556/559, CALLED @874. Fail-CLOSED for distill_* w/o teacher @514-521 and pre-MLX @786-792. Test: `tests/test_distillation_wiring.py`. | — |
| 3 | C adapter_runtime §9.2 base/scope/conflict VERIFIED not proxied | **PARTIAL** | base-hash VERIFIED: `adapter_runtime.c:90-94` real `strcmp(base_sha256, s_expected_base)`→`gov_refuse("base_hash:mismatch")`; `base_sha256` loaded `lora.c:379-383`; `gov_admit` CALLED @138 before bind; engine sets expected base `xmind_easy.c:285`. Scope (@98 TODO) + conflict (@111 TODO) still PROXIED (entry-count/self-degeneracy only). | surface genome `scope` (permitted layers) + cross-adapter lineage/HMAC onto `xmind_lora_t`; verify in gov_admit |
| 4 | xmind_easy.c §8.3 model-artifact REFUSE on sha mismatch | **OPEN** | `xmind_easy_init(model_path, max_seq_len)` `xmind_easy.c:99` has NO `expected_sha256` param; computes `s_weight_fingerprint` AFTER load @150, only REPORTS it @92. Model loads unconditionally. The sha is used only to gate ADAPTER admission (@285), not model materialization. | add `expected_sha256` param to init/load; refuse-before-materialize on mismatch |
| 5 | prefix/prompt operators consumed by OmniPEFTBlock forward | **PARTIAL** | prompt CLOSED: `prompt_tuning`/`p_tuning` CONSUMED via `_apply_prompt_experts` CALLED `model.py:146` inside `__call__`. prefix OPEN: `prefix_tuning` (+prefix half of mam/unipelt) explicitly inert/identity, skipped @138 ("not-yet-wired prefix-KV"). | wire prefix-KV into base attention forward, or mark prefix methods unsupported; confirm OmniPEFTBlock path runs live vs test-only |
| 6 | conflict.compute_delta_cosine_similarity called in prune() | **OPEN** | `conflict.py:176` DEFINED; sole repo reference is its own def (grep: 1 hit). `prune()` @91 uses only `check_compatibility` (explicit lists + domain clash), never the numeric primitive. | call it in `prune()`; reject pairs below a cosine threshold (this IS the numeric half of item 1) |
| 7 | train_peft base-checkpoint fail-CLOSED via mx.load | **CLOSED** | `train_peft.py:824` `mx.load` (reads safetensors+npz, not np.load); missing→`return 2` @816-819; load error→`return 2` @827-830. Teacher load same discipline @837-849. | — |
| 8 | serve_raw_model byte serve path (byte_vocab.json / byte+3) | **CLOSED** | `serve_raw_model.py:80` byte_mode keyed on `byte_vocab.json` presence; byte+3 contract @83-93,128-129; SentencePiece lazy-imported only on legacy spm path @96; raises only if neither artifact exists @98-101. | — |
| 9 | top _xmind vs ai/.../_xmind collide + rename + council strings | **PARTIAL** | Taxonomy CLOSED: `_xmind/client.py` + `__init__.py` are identity-neutral — zero "Citadel Council"/"council" persona strings (only residual is doc `_xmind/personas/README.md:3` "Council member"). Rename OPEN: top-level still named `_xmind` (no `xmind_federation`); both `_xmind` packages still exist and can collide on sys.path. | rename top-level `_xmind/`→`xmind_federation` (or merge); updates importers in api.py/federation_adapter/conftest |
| 10 | 5 §12 acceptance tests exist by name | **CLOSED** | All present + non-trivial: `test_adr_immutability.py`(32), `test_no_archive_taxonomy_import.py`(24), `test_adapter_genome_scope.py`(68, the conflict-threshold test), `test_no_direct_memory_write_from_adapter.py`(28), `test_l7_critical_manual_reset.py`(57). Real assertions verified. | — |
| 11 | CI builds ai/xmind + treats C-engine skips as FAIL | **OPEN** | No `.github/workflows` in `models v7` at all; no CI yml/sh that builds ai/xmind or fails on C-test skips. Only `ai/xmind/Makefile` exists (a build target, not a gate). | add a CI lane that `make`s ai/xmind and treats libxmind-core skips as FAIL |
| 12 | ExperienceAtom §8.2 fields present + populated | **CLOSED** | `experience_atom.py:32-36` has source_hashes/contradiction_links/correction_history/privacy_class/retention_mode + lineage @29. `create()` POPULATES source_hashes @45-48 + retention_mode @49. | — |
| 13 | RecallTrail §7.3 constructed in jog_my_memory | **CLOSED** | `recall_trail.py:24` RecallTrail has trail_id/expansion_depth/stop_reason/confidence_before-after @28-39; `jog_my_memory` CONSTRUCTS+POPULATES @64,73-79 (real trail_id, expansion_depth=1, computed stop_reason @79). CALLED on turn path `agent.py:477`, surfaced `api.py:468-472`. | (confidence_before left 0.0 — cosmetic) |
| 14 | EvidenceEnvelope §6.3 fields present + populated | **CLOSED** | `evidence.py:72-76` source_kind/source_id_hash/timestamp_ns/retention_hint/confidence. `build_evidence_envelope` POPULATES @123-127 (real `time.time_ns()`, confidence=salience). | — |
| 15 | MaterializationRecord §8.3 aliases / to_dict_v2 | **CLOSED** | `materialization_record.py:71-148` read-only @property §8.3 aliases; `to_dict_v2()` @150 emits full §8.3 key set; `__main__` self-test asserts @198-221. | aliases present (the row's bar); `to_dict_v2` consumed only in `__main__`, not on a runtime path |
| 16 | DeterminantRecord §10.2 aliases | **CLOSED** | `determinant_record.py:96-138` §10.2 @property aliases; `to_dict_v2()` @140 emits all 10 §10.2 names; `__main__` asserts @196-202. | aliases present (the row's bar); `to_dict_v2` consumed only in `__main__`, not on a runtime path |
| 17 | validate_adapter weights_exist error-severity | **CLOSED** | `validate_adapter.py:166` missing weights → `severity="error"` → `overall="fail"` @75 → "Cannot promote" @288; `--force` overrides only `warn`, not `fail` @291. A weightless adapter cannot promote even with --force. | (weight-validity sub-checks still nested under npz path @178-206; shape-check claim dropped, not implemented) |
| 18 | omni run → run_retrain.py exists | **CLOSED** | `omni_training_program.py:300` shells into `run_retrain.py`; file exists (226 lines, real delegate → pt/train_byte.py / pt/train_peft.py). | — |
| 19 | create_default_gate_chain() instantiable | **CLOSED** | `gate_evaluators.py:71` `_StubHarness.__init__(*args,**kwargs)` + `cycle()` @77. Empirically instantiated clean (ran `create_default_gate_chain()` → `GateChainExecutor`, no exception). | row also asked "add a test" — NO `test_gate_chain*` exists; remains a scaffold off the live turn path |
| 20 | gguf_reader arr_count overflow bound-check | **CLOSED** | `gguf_reader.c:251` `arr_count > (1<<26) → return GGUF_ERR_CORRUPT` BEFORE the multiply @252; 2nd reader path bounds per-element vs file_size @551-560. | — |
| 21 | api /v1/heptagon/status L4/L7 labels correct | **CLOSED** | `api.py:383` `L4_world_model = verifier`; `:386` `L7_governance = enforcer` (inversion fixed). | — |
| 22 | node_registry queried on turn path (all_nodes) | **CLOSED** | `api.py:478` `_reg.all_nodes(active_only=True)` CALLED inside `_core_turn_provenance`, which is CALLED on /v1/chat @579 and /v1/chat/stream @710. | — |
| 23 | federation_adapter dead AND broken | **PARTIAL** | NOT broken anymore: `federation_adapter.py:80-85` calls `XMindClient(member_name=,model_path=,temperature=,top_p=)` — all 4 ARE accepted by real `_xmind/client.py:192-201`. Still DEAD: referenced by nothing but itself (grep: only self). | decide disposition (delete or wire); coupled to item 9 rename (it imports `_xmind`) |
| 24 | companion doc typos :8090→:8091, /healthz→/v1/health | **CLOSED** | `agent-bridge.ts` uses `:8091` @4,41,89,121 and `/v1/health` @16,19,22,29; `global.d.ts:11` `/v1/health`. Named files clean. | residual `:8090` only in `ai/companion/Dockerfile:8` (a comment example) — outside the row's named files |

## Closed-since-stale-ledger (rows the tables above still marked OPEN/PARTIAL)

Items **2, 7, 8, 10, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 24** are now CLOSED and were verified
reachable/CALLED (or, for record-shape rows 15/16, present at the "aliases declared" bar the row set).
The stale per-row table statuses predate commits `5dd78fd…2333483`.

---

# SUMMARY — still-OPEN / PARTIAL, with file-scopes + collisions

## OPEN (4)
- **#4 — xmind_easy.c model-artifact verify-before-materialize refuse.** Files: `ai/xmind/src/xmind_easy.c` (+ its header `ai/xmind/include/xmind_easy.h` for the new param).
- **#6 — conflict.compute_delta_cosine_similarity called in prune().** Files: `training/peft/conflict.py`.
- **#11 — CI lane that builds ai/xmind and treats C-test skips as FAIL.** Files: NEW `.github/workflows/*.yml` (+ optionally a verify script). No existing file to collide on.
- **(LOW) federation/_xmind disposition** — see #9/#23 below; not separately itemized.

## PARTIAL (4)
- **#1 — §9.2 trust chain (verify + numeric conflict + DPR) on the PEFT router path.** Files: `training/peft/router.py`, `training/peft/model.py`, `training/peft/conflict.py` (+ reads `training/peft/v2/adapter_genome_v2.py`).
- **#3 — C adapter scope + conflict VERIFIED (base-hash already done).** Files: `ai/xmind/src/adapter_runtime.c`, `ai/xmind/include/lora.h`, `ai/xmind/src/lora.c`, `ai/xmind/src/xmind_easy.c`.
- **#5 — prefix-KV operator wiring (prompt half done).** Files: `training/peft/model.py` (+ `training/peft/prompt/prefix_tuning.py`).
- **#9 — rename top-level `_xmind/` → `xmind_federation` (taxonomy already neutral).** Files: top-level `_xmind/` (whole package) + importers of the **top-level** package: `ai/tokenless-agent/src/federation_adapter.py` (binds top-level via template-root sys.path insert) and `tests/conftest.py:49` (ambiguous — the collision itself). NOTE: `api.py:487 from _xmind import get_client` resolves to the **inner** `ai/tokenless-agent/src/_xmind/` (`get_client` defined only there, `_xmind/client.py:180`) — NOT touched by the top-level rename.
- **#23 — federation_adapter disposition (no longer broken, still dead).** Files: `ai/tokenless-agent/src/federation_adapter.py`.

## Parallelization collisions (CANNOT be assigned to disjoint agents)

1. **PEFT cluster — #1 + #5 + #6 must be ONE serialized work-unit.** Scope: `training/peft/{router,model,conflict}.py`.
   - #1 names router.py **and** model.py; #5 is model.py → direct file collision on `model.py`.
   - #6 (`compute_delta_cosine_similarity` defined-not-called in `conflict.py`) **IS** the numeric-conflict half of #1's trust chain — fixing #1 fully means calling it in `prune()`. Separate agents would double-edit `conflict.py` + `router.py`.

2. **xmind C cluster — #3 + #4 overlap on `ai/xmind/src/xmind_easy.c`.** #3 already wired `set_expected_base(s_weight_fingerprint)` in xmind_easy.c; #4 must edit the same file to add the model-load `expected_sha` refuse. #3 also reaches into `lora.h`/`lora.c`. Serialize or assign both to one agent.

3. **Federation cluster — #9 + #23 are coupled.** The #9 rename of top-level `_xmind/`→`xmind_federation` touches its importers: `federation_adapter.py` (#23, binds the top-level package) and `tests/conftest.py:49`. (`api.py:487`'s `from _xmind import get_client` is NOT affected — it resolves to the inner `ai/tokenless-agent/src/_xmind/`.) #23's disposition and #9's rename still cannot go to disjoint agents, via federation_adapter.py.

## Cleanly parallelizable (disjoint, no shared files)
- **#11** (new `.github/workflows/`) — touches no existing source file.
- The PEFT cluster (1+5+6), the xmind-C cluster (3+4), and the federation cluster (9+23) are mutually disjoint
  from each other and from #11 — so **4 parallel agents max**: {1,5,6} · {3,4} · {9,23} · {11}.
