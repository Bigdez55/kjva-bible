# ADR-S49-04 — Runtime Wiring Reconciliation (covenant gate, Heptagon L6, §12 spine)

- **Status:** Accepted
- **Date:** 2026-05-31
- **Supersedes/relates:** ADR-S49-01 (cognitive architecture doctrine), ADR-S49-02 (class-name reconciliation)
- **Source of truth:** UNIFIED_MASTER_TECH_PACK.md §4.4, §12; CONFORMANCE_CROSS_COMPARISON_2026-05-31.md

## Context

The audit found three runtime-wiring defects. The DO_NOT_MODIFY contract files
(`governance/covenant_enforcer.py`, `heptagon/{harness,layers,unified_model_spec}`,
`soul_manager/*`) were **correct**; the bugs were entirely in the **modifiable callers**
under `ai/tokenless-agent/src/`. All fixes are applied at the caller; no protected file
is touched.

## Decision

1. **Covenant gate fail-closed (`api.py`).** The caller invoked
   `CovenantEnforcer.evaluate()` (does not exist — the method is `enforce()`), compared
   against `EnforcementAction.HARD_STOP` (the enum is ALLOW/BLOCK/WARN), and read
   `cov_result.reason` (no such field) — all inside a bare `except Exception` that
   swallowed the resulting `AttributeError` and let the request proceed to inference.
   Net effect: **every covenant block was silently bypassed.**
   Fix: call `enforce(req.message)`, block on `cov_result.is_blocked` with
   `cov_result.summary()`, and on any enforcement error **raise 422 (fail closed)** —
   an enforcement failure must never pass a request through.

2. **Heptagon L6 calibrator wiring (`agent.py`).** `ParameterCalibrator()` was called
   with no args but its constructor requires `entity_id`; the `TypeError` was caught by
   the degradation guard, leaving `calibrator = None` — **L6 calibration was dead**.
   Fix: `ParameterCalibrator(entity_id=agent_id)`; the degradation log is raised from
   `debug` to `warning` so future silent degradation is visible (fail-loud).

3. **§12 pipeline spine (`cognitive_pipeline.py`) — sequenced after sensory modules.**
   The §12 flow (`build_evidence_envelope` → `DecisionGateChain.evaluate` fail-closed →
   `SoulManager.retrieve` → Heptagon⇄SoulManager reflex → `OmniPEFT.route_adapters` →
   writeback quality gate → lineage) depends on the sensory evidence modules
   (`sensory/{evidence,router,home_security}.py`) and extended memory modules, which are
   built in Phase 4. The full spine is wired in/after Phase 4 against those modules; the
   `DecisionGateChain` is wired **fail-closed** (NOT_EVALUATED / missing blocking gate ⇒ DENY).

## Consequences

- Covenant enforcement is now actually enforced and fails closed.
- L6 calibration participates in the cognitive loop.
- Apex §22 acceptance remains 9/9 (+latency) — no regression on the request hot path.
- Remaining §12 enhancements are tracked as Phase-4-dependent, not deferred indefinitely.

## Guardrails honored

No edits to any DO_NOT_MODIFY surface. Changes limited to
`ai/tokenless-agent/src/{api.py,agent.py}` (and, in Phase 4+, `cognitive_pipeline.py`).
