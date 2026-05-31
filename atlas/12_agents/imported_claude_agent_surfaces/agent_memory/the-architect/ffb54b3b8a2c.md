# The Architect — Persistent Memory

## Key Architectural Decisions

### Holding Model Field Names (confirmed 2026-02-19)
- Average cost column: `average_cost` (NOT `average_price`, NOT `cost_basis`)
- Current price column: `current_price`
- Both are `Numeric(18, 8)` — use `Decimal(str(...))` for arithmetic
- `cost_basis` only exists as a constructor arg / instance attribute in `__init__`, not a Column

### Portfolio Model: `owner_id` vs `user_id` (confirmed 2026-02-19)
- Real DB column: `owner_id`
- `user_id` is a hybrid property expression aliasing `owner_id` (works in queries but prefer `owner_id`)
- Always use `Portfolio.owner_id` in new filter expressions

### AlpacaBroker API (confirmed 2026-02-19)
- Method: `get_account_info(account_id: str)` — NOT `get_account()`
- Returns: `{account_id, balance, buying_power, cash, currency, status, ...}`
- `balance` = equity (total portfolio value), `cash` = cash balance
- Alpaca ignores the `account_id` arg (single account per API key)
- Paper vs live: `AlpacaBroker(use_paper=True/False)`

### Sentinel TriggerType enum (confirmed 2026-02-19)
- `PORTFOLIO_DRIFT`, `PRICE_ALERT`, `RISK_THRESHOLD`, `EARNINGS_WARNING`,
  `DIVIDEND_NOTIFICATION`, `NEWS_SENTIMENT`
- Deduplication always via `_has_recent_trigger(user_id, type, symbol, hours=N)`

### Wealth Advisory Streaming — User Personalization Pattern
- Streaming endpoint (`/advisory/query/stream`) uses `llm_service.stream_with_vllm` directly
- It does NOT call `eft_enhance_response`
- To inject user context: build `user_ctx = build_user_context(current_user)`, then
  prepend to `system_prompt` AFTER `_build_vllm_prompts(request, context)` call
- `build_user_context` already imported at top of `wealth_advisory.py` (line 41)

### `notification_preferences` Column (confirmed 2026-02-19)
- Already existed in `user.py` as `Column(Text, nullable=True)` before this sprint
- Stores JSON string of preference flags
- `UserResponse` schema now exposes it; `/notifications` PUT endpoint manages it

### Router Prefix Rule (confirmed 2026-02-19 — Phase 2.4)
- If a router's `APIRouter(prefix=...)` is set in the endpoint file, do NOT pass `prefix=` again in `api.py` — it doubles the path segment.
- Phase 2.4 routers (documents, linked_accounts, beneficiaries) carry their own prefix; registered as `api_router.include_router(router)` (no extra prefix arg).

### Phase 2.4 New Files (created 2026-02-19)
- `backend/app/models/linked_account.py` — LinkedAccount model (`__tablename__ = "linked_accounts"`)
- `backend/app/models/beneficiary.py` — Beneficiary model; fields `relationship_to_user` and `beneficiary_type` (avoid SQLAlchemy name conflicts with `relationship`/`type`)
- `backend/app/api/api_v1/endpoints/documents.py` — Trade history export (CSV + JSON streaming)
- `backend/app/api/api_v1/endpoints/linked_accounts.py` — GET/POST/DELETE linked accounts
- `backend/app/api/api_v1/endpoints/beneficiaries.py` — GET/POST/DELETE beneficiaries with percentage validation
- `auth.py` additions: `PUT /password`, `POST /deactivate`, `POST /delete-account`
- Model discovery: both new models added to `backend/app/db/init_db.py` import block
- `user.py` additions: `user_settings` (Text, nullable), `linked_accounts` relationship, `beneficiaries` relationship

### Trade Model Export Pattern
- Filter trades by user: query `Portfolio.id` WHERE `owner_id == user.id`, then `Trade.portfolio_id.in_(portfolio_ids)`
- Never filter trades directly by `user_id` on Trade (it exists but portfolio-join is the authoritative ownership check)
- `TradeStatus` values must be lowercased enum: `TradeStatus(status.lower())`

### Auth Endpoint: `investment_goals` Serialization
- `UserProfileUpdate` now includes all 5 investment profile fields
- `investment_goals` is `list[str]` in the schema but stored as JSON string in DB
- Must JSON-serialize before `setattr` loop in `update_profile`
- Pattern: `if isinstance(update_dict["investment_goals"], list): json.dumps(...)`

### Python 3.13 Compatibility (2026-02-21 — Phase 7)
- **NEVER** use `datetime.utcnow()` — deprecated, will be removed in Python 3.13
- **ALWAYS** use `datetime.now(UTC)` with `from datetime import UTC`
- Migrated 401 instances across 83 backend files
- Pattern: `from datetime import datetime, UTC` then `timestamp = datetime.now(UTC)`

### Trading Service Validation (2026-02-21 — Phase 7)
- `TradeSource.USER_INITIATED` is an alias to `TradeSource.MANUAL`
- Investment type auto-detection: if `investment_amount` provided without `quantity`, use `DOLLAR_BASED`
- Validation order: quantity/amount → prices → funds check → risk limits
- Paper trades have zero commission (`trade.is_paper_trade` check in `_calculate_commission()`)
- Helper methods: `is_market_open()`, `update_order_status()` handle market hours and partial fills

### AccountPage Decomposition (2026-02-21 — Documented, deferred)
- Current: 1,899-line monolithic component
- Plan: Split into 5 tab components + main container
- Estimated effort: 28 hours (~3.5 days)
- Decision: Deferred to dedicated Frontend Architecture sprint (high blast radius)
- See: `docs/ACCOUNT_PAGE_DECOMPOSITION_PLAN.md`

### Security.py Rate Limiting Architecture (audited 2026-02-27)
- `check_login_rate_limit` correctly falls back to in-memory (`_mem_check_and_increment`) when Redis is None — CORRECT
- `check_rate_limit` (general middleware) has `return True` bypass when Redis is None — SECURITY GAP (P1)
- Fix: apply same in-memory fallback pattern to `check_rate_limit`; infrastructure already exists in the file
- `utils/rate_limiter.py` Alpaca throttling also bypasses when Redis is None — acceptable (downstream 429s are safe)
- `REDIS_URL` defaults to `redis://localhost:6379` — passes `ping()` test locally, silently fails on Cloud Run (no local Redis)

### LinkedAccount Table Deployment Gate (audited 2026-02-27)
- `linked_accounts` table was added in Phase 2.4 (2026-02-19)
- `elson_linked_accounts` localStorage key is GONE — zero references in frontend src
- Server-side migration is COMPLETE at code layer; table may not exist on Cloud SQL yet
- MUST run `SELECT EXISTS(... table_name = 'linked_accounts')` before deploying — if false, run CREATE TABLE
- No encryption needed: model stores only display-safe data (institution_name, account_type, last_four)

### RTK Query Stale Data Gaps (audited 2026-02-27)
- `getProactiveScan`: ALREADY FIXED in `useProactiveAdvisor.ts:33` — `refetchOnMountOrArgChange: true` at call site
- `getAIPortfolioAnalysis`: MISSING flag — called in `useAIInsights.ts:109` without option; add `{ refetchOnMountOrArgChange: true }`

### useInvestData Batch Consolidation (audited 2026-02-27)
- Currently fires 9 active + 1 lazy RTK Query subscriptions
- `getBatchData` endpoint exists at `GET /trading/batch-data` (backend confirmed, returns `recent_orders` not `orders`)
- Consolidation target: replace 4 subscriptions (portfolio/positions/account/orderHistory) with 1 `useGetBatchDataQuery`
- `useAIInsights.ts` already uses `useGetBatchDataQuery` — pattern proven
- Net result: 10 → 7 subscriptions; 4 → 1 mount-time network calls for portfolio data

### batch-data backend docstring bug (2026-02-27)
- `trading.py:817` docstring shows `"orders": []` but actual `BatchDataResponse` field is `recent_orders`
- Frontend RTK Query definition correctly uses `recent_orders` — runtime safe, docstring is just wrong

## Go Microservices Migration (2026-02-25)

### Services

- `backend/go/market-gateway/` — replaces market_data.py, ports :8080 (REST) + :9090 (gRPC)
- `backend/go/risk-engine/`    — replaces risk_management.py, same dual-port
- `backend/go/order-router/`   — replaces trade_execution.py + broker/alpaca.py, same dual-port

### Proto Packages

- `elson.market.v1` | `elson.risk.v1` | `elson.execution.v1`
- Proto files: `backend/go/proto/elson/{market,risk,execution}/v1/`

### Key Design Decisions

1. gRPC :9090 for Go-to-Go; REST :8080 for Python proxy and frontend
2. Order Router calls Risk Engine via gRPC — FAIL CLOSED (safety systems never degrade silently)
3. Risk Engine is READ ONLY from DB — point at read replica in Phase 2
4. Order Router uses SERIALIZABLE isolation for trades inserts + SELECT FOR UPDATE on portfolio row
5. Market Gateway: READ COMMITTED, ON CONFLICT DO NOTHING for market_data inserts
6. Health check: only "healthy" is acceptable — "degraded" returns HTTP 503
7. Rollback: `gcloud run services update-traffic <service> --to-revisions=PREV=100 --region=us-west1`

### Migration Phases

- Phase 1: Python proxies to Go via internal VPC HTTP (MARKET_GATEWAY_URL, RISK_ENGINE_URL, ORDER_ROUTER_URL env vars)
- Phase 2: Frontend hits /v2/* Go endpoints directly
- Phase 3: Python service layer deleted

### Error Format (all 3 services, FastAPI HTTPException compatible)

```json
{"detail": "...", "code": "ERROR_CODE", "service": "service-name"}
```

### DB Connection Pools

- Market Gateway: 10 max / 2 min (mixed read+insert)
- Risk Engine:    5 max / 1 min (READ ONLY)
- Order Router:   20 max (primary write service)

### Required Indexes on Cloud SQL (verify before deploy)

```sql
CREATE INDEX IF NOT EXISTS idx_market_data_symbol_timeframe ON market_data (symbol, timeframe, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_assets_active ON assets (is_active, market_cap DESC NULLS LAST);
```

### Go Build

`CGO_ENABLED=0 GOOS=linux` — Cloud Run requires static binary, no CGo.

### go.mod Dependencies

`google.golang.org/grpc v1.62.0`, `google.golang.org/protobuf v1.33.0`,
`github.com/jackc/pgx/v5 v5.5.4`, `github.com/redis/go-redis/v9 v9.5.1`,
`github.com/golang-jwt/jwt/v5 v5.2.0`

## API Contract Audit Results (2026-03-08)

Full report: `docs/ARCHITECTURE_AUDIT_2026_03.md`

### GENESYS Bridge: ALL 7 endpoints verified EXISTS

- `GET /auto-trading/signals` — no response_model (returns Dict[str,Any])
- `GET /trading/account` — TradingAccountResponse
- `GET /trading/positions` — List[PositionResponse]
- `GET /market/quote/{symbol}` — QuoteResponse, 30s TTL
- `POST /risk/assess-trade` — TradeRiskResponse
- `POST /trading/` — TradeResponse
- `GET /portfolios/` — PortfolioSummaryResponse (also at /portfolio/)

### Critical Schema Drift (2026-03-08)

`metadata_json` column in `trading_audit_logs` model exists but NOT in any migration.
Run `\d trading_audit_logs` on Cloud SQL. If absent: `ALTER TABLE trading_audit_logs ADD COLUMN metadata_json jsonb;`

### Architectural Smell (HIGH)

`_get_or_create_portfolio()` defined in `endpoints/portfolio.py`, imported by `auto_trading.py` (module-level) and `trading.py` (lazy). Move to `services/portfolio.py`.

### EFT Return Type Bug (HIGH)

`GET /auto-trading/strategies/available` returns different shapes based on EFT availability. All EFT-enhanced endpoints MUST have stable outer shape.

## Ruth Integration Architecture — Phase 5A COMPLETE (2026-03-08)

Spec: `RUTH_MASTER_SPECIFICATION.md` | Blueprint: `docs/ruth/RUTH_TECHNICAL_BLUEPRINT.md`
Migration: `backend/alembic/versions/add_ruth_tables_2026_03_08.py`

**Package:** `backend/app/ruth/` — 63 files, ~11,700 lines
**Feature flag:** `RUTH_ENABLED=False` default — all endpoints gate on `_assert_ruth_enabled()` in `ruth/api/ruth.py`
**GENESYS bridge:** `GET /api/v1/ruth/regime` — no auth required (market-level public data)

### Critical Architectural Constraints (enforce in all Phase 5B/5C work)

1. EFT Step 11 MUST NOT be parallelized — single vLLM LoRA call; parallel = 50% GPU degradation
2. `drawdown_pct` is a FRACTION (0.03 not 3.0) — enforced in GoRiskEngineClient, RiskEngine, RiskKeeper
3. Numeric(18,8) for all financial columns; Numeric(6,4) for confidence/win_rate — never Float
4. No `google.*` imports in ruth/ — cloud-agnostic; all infra via env vars + Python fallbacks
5. PII never reaches EFT layer — user_id stripped in all LLM adapter call paths
6. `SignalFusionService.fuse()` first call site: `ruth/services/ruth_trading_adapter.py:get_fusion_signals()`
7. `FinnhubSentimentService` first call site: `ruth/agents/sentiment_reader.py`
8. Kelly cap: `regime_kelly = min(half_kelly × regime_scalar, 0.20)`

### Key Schemas

- `RuthSignalOutput.pulse_score` = `min(10, conf×3 + regime_alignment×2 + source_bonus)` (model_validator)
- `RuthSignalOutput.is_actionable` = `conf >= 0.60 AND pulse >= 5.0 AND direction != HOLD`
- `RuthRegimeSnapshot.valid_until` = `created_at + 1h` (auto-set in model_validator)
- `RuthAllocationOutput` validates weights sum to 1.0 ± 0.01; enforces 5% min cash

### Five Market Regimes + Kelly Scalars

TRENDING_BULL (1.0), QUIET (0.85), MEAN_REVERTING (0.70), VOLATILE (0.40), TRENDING_BEAR (0.25)

### Go Client Timeouts

market-gateway: 500ms | order-router: 2s | risk-engine: 1s — all Python fallback on empty URL or error

### Phase 5B/5C Deferred (Group B agents)

- All 7 engine `run()` / protocol method implementations raise `NotImplementedError`
- All 12 agent `run()` methods raise `NotImplementedError`
- `RuthCore.analyze()`, `RuthContextBuilder.build()`, pipeline phase A/B methods raise `NotImplementedError`
- All memory store implementations (episodic, persistent, meta) raise `NotImplementedError`

### Import Rules

- No pipeline step imports another pipeline step; adapters never import adapters
- `RuthLLMAdapter` wraps `app.services.eft_enhance` — no direct vLLM calls
- Go env vars: `RUTH_GO_MARKET_GATEWAY_URL`, `RUTH_GO_ORDER_ROUTER_URL`, `RUTH_GO_RISK_ENGINE_URL` (empty = Python fallback)

## RUTH Inference Infrastructure (confirmed 2026-03-11)

### vLLM VM Facts
- VM: `elson-dvora-training-l4-2` (us-west1-a), L4 = 22.5GB VRAM
- RUTH bfloat16 = 28GB — does NOT fit on L4 without quantization
- Current production config: `--quantization bitsandbytes` (NF4 4-bit) = ~7-8GB weights
- Dual-server config: port 8000 (0.47 util) + port 8001 (0.45 util) = ~20.7GB used
- Model source: GCS `elson-33a95-elson-models/elson-finance-14b-production/` (pre-merged, single shard)
- Idempotency guard: startup script skips download if `/workspace/elson-model/config.json` exists
- Startup script: `GCP_AGENT/scripts/deploy-vllm.sh` (uploaded to GCS as startup-script-url)

### Config is ALREADY CLEAN (no hardcoded IPs)
- `backend/app/infra/llm.py` — single source of truth for LLM URL resolution
- Resolution order: `VLLM_BASE_URL` -> `VLLM_FALLBACK_BASE_URL` -> `localhost:8000`
- The P0 hardcoded IP at config.py:357 was already fixed — `VLLM_FALLBACK_BASE_URL` is now env-var only

### DoRA Adapter Serving Decision
- vLLM DoRA support (use_dora=True) is inconsistent as of vLLM 0.4-0.6 — DoRA math vs standard LoRA math
- PRODUCTION DECISION: pre-merge base + DoRA adapter on H100, upload merged model to GCS, serve merged
- Hot-swap via --enable-lora deferred until vLLM>=0.6 DoRA support is validated
- `deploy-vllm-dora.sh` adapter flags are architecturally correct but premature for DoRA

### Cost Optimization (unimplemented — HIGH PRIORITY)
- Static internal IP should be reserved for vLLM VM — prevents VLLM_BASE_URL updates after stop/start
- Cloud Scheduler: start VM 8:30 AM ET weekdays, stop 5 PM ET = ~79% compute cost reduction
- L4 on-demand always-on = ~$350/mo | Trading-hours-only = ~$75/mo | Spot trading-hours = ~$25/mo
- Thunder Compute: training only — no VPC peering to Cloud Run, preemption risk, wrong billing model

### Upgrade Path
- L40S (48GB) = bfloat16 full precision, single instance, ~$0.40/hr spot = next GPU target
- Speculative decoding: RUTH-1.5B draft model (future, Phase 3 roadmap)

## Frontend-Backend Integration Audit (2026-03-17)

Full detail file: `.claude/agent-memory/the-architect/api-contract-audit-2026-03-17.md`

### Critical Confirmed Bugs
1. `GET /auto-trading/pdt-status` — frontend calls it (tradingWorkspaceApi), NO backend route. Will 404.
2. `GET /analytics/sector-performance` — frontend calls it (analyticsApi), NO backend route. Will 404.
3. `POST /trading/orders` (plural, hidden alias) — frontend api.ts tradingAPI.getOpenOrders hits `GET /trading/orders` which EXISTS, but tradingAPI.placeOrder hits `POST /trading/order` — OK.
4. `analyticsApi.ts` double-path construction: baseUrl already has `/api/v1`, then it appends `/analytics`, then the query path. Net: `/api/v1/analytics/performance-summary` — CORRECT but fragile if baseUrl changes.
5. `subscriptionApi.ts` Subscription.id typed as `string`; `subscriptionService.ts` Subscription.id typed as `number` for same backend endpoint — type contract conflict across two callers.
6. Token field aliases: backend returns `access_token`; some frontend paths also try `token` field that doesn't exist — handled by dual-path `||` operator, OK but fragile.
7. `resolveApiBaseUrl()` silently falls back to `/api/v1` when cross-origin without `REACT_APP_ALLOW_CROSS_ORIGIN_API=true` — production URLs are cross-origin on Cloud Run; this MUST be set.

### Auth `register` field name divergence
- `auth.ts` sends `full_name` — backend UserRegister has `full_name` — CORRECT
- `auth.ts` RegisterData interface has `username` field, maps to `full_name` in payload — OK but confusing

## Redis Infrastructure State (confirmed 2026-03-18)

- **Memorystore: NOT provisioned** — `gcloud redis instances list --region=us-west1` returns 0 items
- **REDIS_URL secret value: `redis://localhost:6379`** — stale placeholder, never updated
- **Production behavior:** `_create_redis_client()` attempts localhost ping, fails (2s timeout), returns None
- **Rate limiting fallback: `_mem_rate_store` in security.py** — has been the actual rate limiter all along
- **Token blacklisting and biometric WebAuthn: non-functional** without Redis (both depend on Redis for storage)
- **Health check fix (2026-03-18):** `/api/v1/monitoring/health` now returns HTTP 200 for degraded (Redis/LLM/Alpaca failures); only DB failure returns 503
- **Liveness probe path:** `GET /health` (main.py, port 8080) — NOT `/api/v1/monitoring/health`; probe only fails on DB outage
- **Secret Manager fix needed:** `printf "" | gcloud secrets versions add REDIS_URL --data-file=- --project=elson-33a95`
- **Production guard added to `_create_redis_client()`:** logs WARNING and returns None if URL contains localhost in production environment — eliminates 2s cold-start penalty
- **Three files changed (deploy with next push):**
  - `backend/app/api/api_v1/endpoints/monitoring.py` — degraded = HTTP 200 (was 503)
  - `backend/app/core/security.py` — localhost production guard + structured log messages
  - `backend/app/core/config.py` — REDIS_URL default changed from hardcoded string to `None`

## Telegram Service (added 2026-03-19)

- File: `backend/app/services/telegram_service.py`
- Singleton: `telegram_service = TelegramService()` (module-level)
- Library: `python-telegram-bot>=20.0` (async v20+) — NOT YET in requirements.txt; add before deploy
- Feature flag: `TELEGRAM_ENABLED=false` (default) — safe to deploy without bot token
- Config: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_ENABLED` in `config.py`
- Security: all inbound messages silently dropped unless `chat_id == settings.TELEGRAM_CHAT_ID`
- EFT routing: free-text → `eft_generate("wealth_chat", ...)` | /status → `eft_generate("portfolio_advisor", ...)`
- Pending order pattern: `telegram_service.set_pending_order(...)` then /confirm or /cancel
- Bot startup/shutdown wired in `main.py` lifespan (after training scheduler, before market streaming start)
- `python-telegram-bot` import guarded — ImportError logs a warning, all methods return None/False gracefully
- MUST add to `requirements.txt` AND `requirements-docker.txt` before first deploy:
  `python-telegram-bot[job-queue]>=20.0,<22.0`

## NtfyCoordinator (added 2026-03-19)

- File: `backend/app/services/ntfy_coordinator.py`
- Singleton: `coordinator = NtfyCoordinator()` (module-level)
- Purpose: deduplication (5-min window per alert_type+symbol) + batching (60-second queue for non-urgent)
- IMMEDIATE types: `trade_executed`, `trade_rejected`, `circuit_breaker`, `system_error`, `caution_mode`
- Sync callers use `coordinator.send_sync(...)`, async callers use `await coordinator.send(...)`
- Flush loop registered in `main.py` lifespan via `asyncio.create_task(_ntfy_flush_loop())`
- NtfyService `ntfy._send()` is still the underlying transport — coordinator wraps it, never replaces it
- All 11 `_send_*_notification()` methods in `daily_market_intelligence.py` now route through coordinator
- 3 ntfy call sites in `auto_trading_service.py` now route through coordinator (game plan = batched; trade_executed + caution_mode = immediate)
- Opening prep and power hour use `immediate=True` because they are time-critical despite being "daily intel"
- Threading: `_lock` protects dedup cache + batch queue; I/O always happens OUTSIDE the lock

## Ruth Memory Layer Architecture (confirmed 2026-03-20)

Five stores — MetaStore is strategy performance, NOT the insights/directive store:

| Store | File | Table | Memory Type |
|-------|------|-------|-------------|
| EpisodicStore | episodic_store.py | ruth_decisions + ruth_episodes | Context + Episodic |
| PersistentStore | persistent_store.py | ruth_regime_snapshots + ruth_macro_snapshots | Snapshots |
| MetaStore | meta_store.py | ruth_strategy_performance | Meta (Kelly/perf) |
| KnowledgeStore | knowledge_store.py | ruth_knowledge_memories | Directives/lessons/insights |

All Ruth ORM models in `backend/app/ruth/models/` (NOT `backend/app/models/`).
KnowledgeStore methods are synchronous (def, not async) — DB-only, no external calls.
memory_service.py coordination wrappers for KnowledgeStore are also def (not async).

Migration: `backend/alembic/versions/add_ruth_knowledge_memory_20260320.py`
Down-revision: `add_retirement_age_to_users_2026_03_18`

## Deep Architecture Audit (2026-03-25) — see audit_2026_03_25.md for full details

Key NEW findings (not in previous audits):
- **P0-SEC:** `backend/.env` contains plaintext Alpaca live keys — git-tracked file, immediate rotation required
- **P0-DOCKER:** `frontend/Dockerfile:2` uses `rust:1.93-slim` — Rust 1.93 doesn't exist; frontend build FAILS
- **P0-ATTR:** `monthly_training.py:747` calls `settings.HF_TOKEN` — attribute doesn't exist (should be `HF_API_TOKEN`)
- **P1:** GENESYS bridge comment (`api.py:203`) says `/ruth/regime` requires no auth — but code requires JWT
- **P1:** Ruth SSE `/analyze/stream` buffers all events before sending — not real-time
- **P1:** `api.elsontrade.com` missing from `ALLOWED_ORIGINS` in `config.py` default — CORS failure in production
- **P1:** nginx `/api/` proxy missing `proxy_buffering off` — Ruth SSE broken through nginx
- **P2:** `RuthCore.health()` always returns "healthy" regardless of engine state — misleading status
- **P2:** Ruth models not imported in `alembic/env.py` — autogenerate can't detect drift
- **P2:** `cloudbuild.yaml:177` `DB_URL` variable constructed but never passed to migration job
- **P2:** `react-scripts test` in package.json but build uses Vite — split toolchain
- **P2:** `elson-backend-clnzl6xzga-uw.a.run.app` stale URL in `ALLOWED_HOSTS` default

## TieredInferenceRouter Rate Limiter (added 2026-03-21)

File: `backend/app/services/tiered_inference_router.py`
Tests: `backend/tests/test_tiered_inference_router.py`

### What was fixed
- P0-10: `TierRateLimiter` dataclass added. Daily caps: T1-T5=2500, T6=500. In-memory dict keyed by ISO date (auto-resets UTC midnight). Old date keys pruned on every `record_call()`.
- P0-10: HTTP 429 detection checks `"429"`, `"rate limit"`, `"too many requests"` in error string. On 429: `suspend_for_429(3600s)`. Does NOT open circuit breaker (separate concerns).
- P0-11: `LOCAL_LLM_ENABLED` no longer gates T1-T5. New gate: `hf_free_tiers_available = bool(LOCAL_LLM_API_KEY or HF_API_TOKEN)`. T6 still requires HF_INFERENCE_URL + HF_API_TOKEN.
- P1-7: `"v7"` removed from T1 aliases. `"v7"/"t7"/"deterministic"/"compliance"` raise `ValueError`. T7 has no LLM path — callers must invoke RiskEngine directly.

### Key invariants
- Capped tiers are skipped via `continue` in the fallback chain — never silently escalate to T6.
- `get_second_opinion()` also gates on T6 rate limiter — returns None if capped.
- `get_stats()` now exposes `rate_limiters` dict with today_calls/daily_cap/remaining/is_allowed/suspended_for_seconds.

## File Locations (Key)

- Sentinel: `backend/app/services/sentinel.py`
- Holding model: `backend/app/models/holding.py`
- Portfolio model: `backend/app/models/portfolio.py`
- AlpacaBroker: `backend/app/services/broker/alpaca.py`
- EFT enhance: `backend/app/services/eft_enhance.py`
- Auth schemas: `backend/app/schemas/auth.py`
- Auth endpoints: `backend/app/api/api_v1/endpoints/auth.py`
- Architecture audit (2026-03): `docs/ARCHITECTURE_AUDIT_2026_03.md`
- Ruth blueprint: `docs/ruth/RUTH_TECHNICAL_BLUEPRINT.md`
- Ruth knowledge memory model: `backend/app/ruth/models/ruth_knowledge_memory.py`
- Ruth knowledge store: `backend/app/ruth/memory/knowledge_store.py`

## Ruth P1 Bug Fix Audit (2026-03-21)

### P1-1: WealthEngine llm=None via _safe_import
Status: ALREADY FIXED (was present before this session)
Location: `ruth_core.py` lines 221-226 (`build_from_settings`)
Pattern: `_safe_import` calls `cls()` with zero args. After import, attributes requiring
constructor args are injected directly: `wealth_engine.llm = llm_adapter`.
Rule: ALWAYS inject post-construction when engines need collaborator references.

### P1-2: MicroEngine Step 6 skip — not documented
Status: FIXED (2026-03-21)
Location: `ruth_core.py` lines 207-212 (`build_from_settings`)
Fix: Added `logger.debug(...)` at the point where `micro_engine` is permanently None.
Context: `micro/` package has 5 individual analyst classes but no coordinator entry point.
Step 6 emits "skipped" via SSE (handled in `ruth_decision_pipeline.py` lines 289-304).
NOT an error — intentional architectural deferral.

### P1-4: MetaStore upsert_strategy_performance had zero call sites
Status: FIXED (2026-03-21)
Location: `auto_trading_service.py` after `kelly_stats_db.close()` (~line 865)
Fix: Inserts MetaStore write per 60s cycle, guarded by `sample_n >= 3`.
Kelly fraction formula: `f* = (win_rate / avg_loss) - ((1 - win_rate) / avg_win)`, clamped [0, 1].
Uses its own `_meta_db = cls._session_factory()` session with `try/finally` close.
IMPORTANT: The method is `upsert_strategy_performance()` NOT `store_strategy_performance()`.
Strategy_name "overall" aggregates all round-trip trade history for that user.

### P1-5: 12 Ruth agents never instantiated
Status: FIXED (2026-03-21) — Phase 2 boundary formally documented
Location: `ruth_core.py` lines 214-219 (`build_from_settings`)
Fix: Comment block explains agents are intentionally deferred to Phase 2 (DoRA adapters).
Phase 1 layer = 8 engine classes + EFT AGENT_REGISTRY configs. NOT the 12 agent subclasses.
