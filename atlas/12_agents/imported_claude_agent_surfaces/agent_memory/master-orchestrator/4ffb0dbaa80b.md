# Master Orchestrator Memory

## Sprint 2026-03-08 -- COMPLETE (Phase 8 Synthesis Delivered)

### Deliverables Produced
- `docs/MASTER_AUDIT_REPORT_2026_03_08.md` -- unified sprint report (14 sections)
- `docs/ruth/RUTH_INTEGRATION_COMPLETE.md` -- Ruth completion document (9 sections)
- `COMPLIANCE_TRACKING_MANIFEST.md` updated with sprint status + CRITICAL-1 FIXED

### Ruth Package -- COMPLETE (10/10 DoD Criteria Met)
- `backend/app/ruth/` -- 64 Python files, 17,043 lines
- 8 engines, 12 subagents, 13-step pipeline, 5 DB tables, 6 API endpoints
- Alembic head: `add_ruth_tables_20260308` (via `add_price_at_5d_20260308`)
- Feature flag: RUTH_ENABLED (default False)

### P0 Blockers -- Final Status
- P0-1 FIXED: monitoring.py returns 503 for degraded
- P0-3 FIXED: vLLM IP now env-var-only
- P0-5 CONFIRMED: credential exposure -- MANUAL rotation required
- P0-8 ACCEPTABLE: bootstrap logs but continues
- P0-2, P0-4, P0-6, P0-7: RESOLVED (prior sprints)
- CRITICAL-1 FIXED: circuit breaker tuple truthiness in trade_executor.py (3 locations)

### CRITICALs Still Open (P1 Backlog)
- CRITICAL-2: Circuit breaker JSON on ephemeral disk
- CRITICAL-4: No shutdown hook for AutoTradingService
- CRITICAL-5: 5 hardcoded equity values block crypto in alpaca.py

### Dead Code Now Wired (5 systems)
- KellySizer -> ruth/engines/risk_engine.py
- SignalFusionService.fuse() -> ruth/services/ruth_trading_adapter.py
- ComplianceRulesEngine -> ruth/agents/policy_reader.py
- FinnhubSentimentService -> ruth/agents/sentiment_reader.py
- get_daily_drawdown() -> ruth/agents/risk_keeper.py

## Recurring Dependency Sequences
- Schema migration -> model __init__.py import -> API endpoint test
- New model file -> MUST add to `backend/app/models/__init__.py` imports AND `__all__` list
- Local SQLite has NO migration tracking; `create_all()` creates new tables but NEVER adds columns
- Ruth imports MUST be one-way: `ruth.adapters -> app.services` (NEVER reverse)

## Critical Patterns (Stable)

### Model Import Pattern (P0 Severity)
- Every SQLAlchemy model in `backend/app/models/` MUST be imported in `__init__.py`
- Missing imports cause `InvalidRequestError` only when relationship is first traversed

### File Conflict Prevention (MUST ENFORCE)
- `auto_trading_service.py` touched by 5+ tasks -- SAME agent, sequential, committed between
- `alpaca.py` touched by 4+ tasks -- SAME agent, sequential
- `config.py`, `main.py`, `api.py` -- single owner per commit
- NEVER let two agents edit the same file in parallel

### Alembic Safety
- ALWAYS verify single head with `alembic heads` before generating migration
- ALTER TABLE on Cloud SQL BEFORE code deploy (2026-02-15 outage precedent)
- Current head: add_ruth_tables_20260308

### Engine Import Aliases (Discovered 2026-03-08)
- `engines/__init__.py` uses backward-compat aliases for Protocol suffix mismatch
- Pattern: `SignalEngineProtocol = SignalEngine` -- prevents ImportError across phases

### Test Mock Paths (Discovered 2026-03-08)
- eft_generate patch path: `app.services.eft_enhance.eft_generate` (NOT the importing module)
- Circuit breaker: `cb.check_trading_allowed()` returns tuple, NOT `.is_triggered` property
- ATR stops: `calculate_stop(entry_price, atr, side)` NOT `calculate_atr_stop()`

## Stakeholder Preferences
- Prefers comprehensive tabulated results with PASS/WARN/FAIL
- Wants deployment recommendations with explicit checklists
- Values fixes applied during validation (proactive)

## Test Baselines (Must Maintain)
- Backend: 326 passed, 22 pre-existing failures
- Frontend (tsc --noEmit): 0 errors
- Ruth tests: 8 files, 3,284 lines (NEW baseline)
- Pre-existing failures: test_auth_flow_complete, test_alpaca_broker_comprehensive, test_enhanced_market_data

## Sprint Key Files (Reference)
- Master report: `docs/MASTER_AUDIT_REPORT_2026_03_08.md`
- Ruth completion: `docs/ruth/RUTH_INTEGRATION_COMPLETE.md`
- Sprint kickoff: `docs/MASTER_AUDIT_KICKOFF_2026_03_08.md`
- Coordinator manifest: `docs/COORDINATOR_MANIFEST_2026_03_08.md`
- Compliance manifest: `.claude/agent-memory/COMPLIANCE_TRACKING_MANIFEST.md`
