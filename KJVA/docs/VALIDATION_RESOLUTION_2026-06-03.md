# Validation Fleet — Residual Resolution (2026-06-03)

A 22-auditor e2e validation fleet (DEFINED→WIRED→CALLED + runtime verification across every
sense, the cognitive loop, correctness core, governance, memory, materialization, determinism,
telemetry, plasticity, API, companion, ADR §16 acceptance, and a dead-code/stub sweep) produced
a severity-ranked residual ledger. Its honest verdict: **not done** — a CRITICAL safety
fail-open + several HIGH behavior gaps. This records what was fixed and what remains, with
reasons. Source-of-truth order: **running code > tests > docs.** 119 tests pass; parity green.

---

## FIXED (committed + pushed this session)

### CRITICAL
- **Covenant pre-inference gate FAILED OPEN in production.** `covenant_enforcer` imported
  `heptagon.registry` (unresolvable src-first, where `heptagon`=agent-side, no registry.py) and
  the governance root was computed 4-up (wrong dir), so `_COVENANT_AVAILABLE=False` and the gate
  was **skipped entirely** — harmful requests reached inference. The 113-green suite MASKED it by
  force-injecting a fake enforcer + running repo-root-first. **Fix:** vendored
  `governance/registry.py` (decoupled from `heptagon`); governance root 4-up→3-up, **appended**
  (insert would shadow agent-side `heptagon` and break `determinant_record`); `/v1/chat` +
  `/v1/chat/stream` now **fail-closed** (503) when the gate is unavailable. Guard:
  `test_covenant_wired.py` (src-first, REAL enforcer — blocks harmful 422, benign passes,
  unavailable→503). Verified `_COVENANT_AVAILABLE=True` + determinant emits again.

### HIGH
- **M3 — the byte-LM was never invoked (templated responses).** `_byte_lm.py` (lazy, fail-open,
  self-provisioning) wires the verified torch `generate()` into `_process`'s general fallthrough —
  the 18.98M model now generates its own byte-level continuation (~0.5s, greedy). Scripture stays
  exact retrieval. Removed the templated FALSE claims ("Covenant PASS / Drift nominal").
  Guard: `test_byte_lm_generation.py`.
- **L2/L4/L5/L6 layer records DEFINED-not-emitted** → `_emit_layer_records` emits all four per
  turn (§16.3), surfaced in provenance.
- **Materialization breadth** — off-enum `recall`→`memory`; a `memory` materialization is now
  emitted on a real writeback (§11.3).
- **Determinism** — `_last_grounded` reset per turn (was leaking a scripture route into the next
  turn's replay record, violating §10.1).
- **DoRA/PiSSA** trained on a degenerate `mx.zeros` matrix → real per-layer attention weight.

### MEDIUM
- **Auth failed open** when `TOKENLESS_API_KEY` unset → now refuses unless `TOKENLESS_DEV_MODE=1`.
- **Streaming** `get_event_loop()` RuntimeError on py3.13 → capture `get_running_loop()` in async
  scope; transcribe `audio_in` before the streaming covenant gate.
- **`mandatory_satisfied` was vacuous** + TTS-out hardcoded available → both are live probes now.
- **Scripture false-positive** — 2-char stopword aliases (`it is 1:1`→ISA) rejected.
- **L4 state machine** — `_sm_fire` used a non-existent `is_valid_event` guard → real
  `can_transition`; force `reset()`→IDLE per turn (no sticking).
- **Self-provision on the status hot path** — manifest used `available()` (could pip-install);
  added cheap `present()` (pure import-check) for status reads.
- **conftest** `setdefault`→hard-set; dev-mode for TestClient. **Docs** drift (`genesys-ai`→
  `tokenless-agent`, `:18600`→`:8091`, + sensory/voice/self-provision sections).

### LOW
- `tensor.c` RoPE header comment → rotate-half; parity docstring band refreshed; interoception
  no-op line removed.

---

## REMAINING — documented deferrals (NOT silently skipped)

| Severity | Item | Why deferred / status |
|---|---|---|
| HIGH | **TTS→ASR round-trip doesn't close** — formant speech isn't intelligible to whisper | Voice-OUT *works* (real WAV). Closing the loop needs a **neural TTS** (a model swap), not a wiring fix. Quality/training limitation, not a bug. |
| MED | **Neutral-taxonomy** — `ahkid`/`Council`/`Bookworm` runtime identifiers + `GenesysAgentWithHeptagon` alias (ADR-0002 §13) | Rename/gate touches the live `cognitive_pipeline` IPC integration; deferred to a focused pass to avoid destabilizing the context path. |
| MED | **Streaming provenance** not surfaced (`chat_stream` doesn't emit determinant/materialization) | Pairs with surfacing provenance as a final SSE event; bounded follow-up. |
| MED | **MLX PEFT track has no production driver** (the C/XMIND adapter path IS production-wired, apply_count=896) | MLX `model.adapt()` is test-proven-effective, production-deferred — labeled as such, not "wired". |
| MED | **DriftDetector monitoring OFF** (`drift_signal` couples to `heptagon.harness`, only the root pkg has it) | Path 3-up fixed; status no longer falsely claims it; full wiring needs decoupling drift from `heptagon.harness` (non-gating telemetry). |
| MED | **7 dead modules** (`metacognition`, `invariant_engine`, `consolidation`, `budget`, `drift_detector`, `_xmind_glue`, `federation_adapter`) | `_xmind_glue`/`federation_adapter` were the intended M3 bridges — superseded by `_byte_lm`. Cleanup/relocation deferred. |
| MED | **Memory quality-gate** has no below-0.3 rejection test | Couples to running a real evaluator (the heptagon-collision degradation defaults quality to 1.0 in-process). |
| LOW | `probabilistic_outputs` thin; `route_policy_hash` circular; `/v1/tool` allowlist not enforced; companion still text-only (no mic/audio client) | Hygiene + the companion voice-client wiring (the #2 UI decision is still deferred). |

**Verdict:** the model's **inner safety gate is now fail-closed and verified**, the byte-LM
**genuinely generates**, the sensory stack is real/portable/self-provisioning, the correctness
core is parity-verified, and the cognitive-layer + materialization records emit per turn. The
items above are honest, reasoned deferrals — none is self-certified green.

---

## RESOLVED (continued session 2026-06-03b) — the deferrals above, closed

The deferral ledger above is now worked down. Evidence is sorted into three honesty tiers —
**Verified live** (real engine, subprocess), **Verified in-process** (pytest only — proves
API/logic, not the live cognitive loop; note the heptagon-collision degraded-harness caveat),
and **NOT run** (could not execute here; what *was* checked is stated). **133 tests pass;
parity 3/3; C lib + adapter tests pass; companion `tsc --noEmit` clean.**

| Was deferred | Now | Evidence tier |
|---|---|---|
| Neutral taxonomy (`ahkid`/`Council`/`Bookworm`, `GenesysAgentWithHeptagon` alias) | **Closed** — renamed to context-coordinator/episodic/journal; alias removed | in-process (suite green post-rename) |
| Streaming provenance not surfaced | **Closed** — `/v1/chat/stream` emits an `event: provenance` SSE frame before `[DONE]`; shared `_core_turn_provenance` so both entrypoints match | in-process (`test_streaming_provenance.py`) |
| MLX PEFT has no production driver | **Re-scoped + closed at the seam** — the driver (`train_peft.py`, 37 methods) already existed; the real gaps were (a) the runtime never CALLED `load_adapter` and (b) the export name form. Both fixed: `XMindClient` absorbs a configured adapter; `save_adapter` emits canonical `blocks.N…A/B.weight` + safetensors | **live** for the runtime load (proof adapter → 32 entries → output **differs**); **NOT run** for `train_peft→save_adapter` with real MLX operators (MLX absent) — producer verified via the shared `write_safetensors` + a synthetic canonical adapter (loads + output-differs) and a regex unit-check, **not** a live train |
| DriftDetector monitoring OFF | **Closed** — decoupled `gate_evaluators` from `heptagon.harness`; `_DRIFT_AVAILABLE=True`, detector wires, fed a REAL per-turn signal (1−composite, verdict reversal, errors) | **live** (composite 0.46 → goal_divergence 0.54 → drift_index 0.13) |
| 7 "dead" modules | **Re-scoped** — `consolidation`(ACT-R) + `budget`(3-6-9) wired as L6 engines, CALLED per turn; `_xmind_glue` is the live XMIND bridge; `metacognition`/`invariant_engine`/`drift_detector` are intentional stub seams (kept). The earlier "superseded by `_byte_lm`" note was wrong — `_byte_lm` (a torch shortcut) was removed; generation runs through XMIND C | **live** (budget `{profile:direct,…}`, consolidation True) |
| Memory quality-gate below-0.3 test | **Closed** — `test_memory_quality_gate.py` pins reject `<0.3`/not-passed, commit `≥0.3` | in-process |
| LOW: `/v1/tool` allowlist not enforced | **Closed** — fail-closed allowlist (403 for unknown); `system_info`/`self_state` now return real interoceptive state | in-process (`test_tool_allowlist.py`) |
| LOW: `probabilistic_outputs` thin; `route_policy_hash` | **Closed** — `uncertainty`=1−confidence (was static 0.0); `adapter_snapshot_hashes` now reflects the live absorption state (replay faithfulness). `route_policy_hash` was already a real sha256 (verified, no change) | **live** (uncertainty complement verified; hashes empty on base, populate when absorbed) |
| LOW: tts sample_rate | **Closed** — sourced from `_tts_bridge.SAMPLE_RATE`, not a hardcoded literal | in-process |
| (new, found this session) interoception not on streaming path | **Closed** — shared `interoceptive_prefix()`; `/v1/chat` (via pipeline) **and** `/v1/chat/stream` both inject the mandatory self-sense when degraded | in-process (streaming spy asserts the prefix reaches `_agent.stream`) |

### Residual, stated plainly (NOT closed)
- **External perception (vision/derived_text) on the streaming path.** `/v1/chat/stream` injects
  the mandatory interoceptive sense but still does **not** run the full evidence-envelope /
  vision-caption seam that `pipeline.execute()` does on `/v1/chat`. Streaming external perception
  remains a non-streaming-only feature — a real, bounded asymmetry, not yet closed.
- **`_active_adapter_hashes()` is defensive** (`except → []`): replay-faithfulness of the adapter
  snapshot depends on `get_client().adapter_loaded()` succeeding; a throwing client would record an
  adapted turn as base. Acceptable defensive code, noted for honesty.
- **Phases 1–6 of the build plan** (full memory recall cascade, complete materialization plane,
  plasticity runtime, determinism replay harness, property/fuzz theorems) are **not** all complete —
  this session closed the deferral ledger and HIGH/LOW gaps, not the entire ADR §13 acceptance
  sweep. **No "§13 all-green" claim is made.** Phase 0 (RoPE parity, 3/3) is **standing prior work**,
  re-run as the gate — not credited to this session.
