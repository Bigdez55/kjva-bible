# Go Microservices Migration -- Compliance Framework & Drift Detection Strategy

**Document ID:** ELSON-GO-COMPLIANCE-2026-02-25
**Version:** 1.0.0
**Status:** DRAFT (Awaiting Approval)
**Owner:** Fintech Integrity Auditor
**Classification:** CRITICAL -- This document governs migration of code that touches REAL MONEY
**Last Updated:** 2026-02-25

---

## Table of Contents

1. [Executive Summary & Risk Assessment](#1-executive-summary--risk-assessment)
2. [Compliance Documentation Template](#2-compliance-documentation-template)
3. [Drift Detection Strategy](#3-drift-detection-strategy)
4. [Verification & Validation Matrix](#4-verification--validation-matrix)
5. [Regression Test Plan](#5-regression-test-plan)
6. [Production Readiness Checklist](#6-production-readiness-checklist)
7. [Incident Response Additions](#7-incident-response-additions)
8. [Change Management Process](#8-change-management-process)
9. [Appendix A: Golden File Catalog](#appendix-a-golden-file-catalog)
10. [Appendix B: Financial Precision Specification](#appendix-b-financial-precision-specification)

---

## 1. Executive Summary & Risk Assessment

### 1.1 Migration Scope

We are extracting 3 Go microservices from the Python FastAPI monolith:

| Service | Python Source Files | Risk Level | Touches Money |
|---------|-------------------|------------|---------------|
| **Market Data Gateway** | `market_data.py`, `market_data_processor.py`, `market_data_streaming_enhanced.py` | HIGH | Indirectly (price feeds inform trade decisions) |
| **Risk Engine** | `risk_management.py` (1,567 lines), `circuit_breaker.py`, `risk_config.py`, `risk_management.py` (trading_engine), `adaptive_parameters.py` | CRITICAL | Yes (risk gate approves/rejects trades) |
| **Order Router** | `trade_executor.py`, `broker/alpaca.py` (870+ lines), `broker/base.py`, `broker/paper.py`, `broker/factory.py`, execution strategies (TWAP, VWAP, Iceberg) | CRITICAL | **YES -- Direct Alpaca API integration, real USD** |

### 1.2 Invariants That Must Hold

These are non-negotiable correctness constraints. Violation of ANY of these during migration is a **CRITICAL** defect that blocks Go service deployment:

1. **Financial Precision Invariant**: Go services MUST NOT introduce floating-point drift in monetary calculations. All dollar amounts must use `decimal` or integer-cents representation. The current Python codebase uses `Decimal` in `alpaca.py` and `float64` in `risk_management.py` -- the Go migration must standardize on `shopspring/decimal` or equivalent.

2. **Risk Gate Invariant**: For identical inputs, the Go Risk Engine must produce the same APPROVED/WARNING/REJECTED decision as the Python `RiskManagementService`. A false APPROVED in Go when Python would REJECTED means real money loss.

3. **Order Execution Invariant**: The Go Order Router must never:
   - Submit a live order when paper mode is configured
   - Submit an order that the Risk Engine would reject
   - Lose an order (queue must be persistent or WAL-backed)
   - Double-submit an order on retry

4. **Data Integrity Invariant**: Go services reading from the same PostgreSQL database must produce identical query results. No ORM-level caching differences, no stale reads for financial data.

5. **API Contract Invariant**: Go service HTTP/gRPC responses must be byte-for-byte JSON-compatible with Python responses for all consumers (React frontend, auto-trading loop, EFT agents).

### 1.3 Known Risks from Current Python Codebase

Based on code audit of the source files:

| Finding | File | Line | Severity | Migration Risk |
|---------|------|------|----------|----------------|
| `RiskMetrics` uses `float` for `portfolio_value`, `daily_var` | `risk_management.py` | 41-55 | HIGH | Go must NOT replicate this -- use `decimal` |
| `Quote` struct in Go plan uses `float64` for `Price` | `GO_MICROSERVICES_IMPLEMENTATION.md` | 71-82 | HIGH | Prices should use string or fixed-point |
| `Order.Quantity` uses `float64` in Go plan | `GO_MICROSERVICES_IMPLEMENTATION.md` | 909 | CRITICAL | Fractional shares require precision > float64 |
| Circuit breaker state is DB-persisted (`circuit_breaker_state` table) | `circuit_breaker.py` | 29-43 | HIGH | Go must read/write same table schema |
| `average_cost` vs `average_price` attribute naming | `alpaca.py:804` (previously fixed) | HIGH | Go must use consistent field naming |
| Hardcoded NYSE holiday calendar (2026 only) | `market_data.py` | 28-57 | MEDIUM | Go must replicate or use shared calendar service |
| VaR uses parametric method (Z-score 1.645) | Risk Engine Go plan | 413 | LOW | Must match Python's calculation exactly |

---

## 2. Compliance Documentation Template

### 2.1 Feature Parity Tracker

Each feature migrated from Python to Go must be tracked in this matrix. One row per function/method.

**Template:**

```
SERVICE: [Market Data Gateway | Risk Engine | Order Router]
FEATURE_ID: [GO-MDG-001 | GO-RE-001 | GO-OR-001]
```

| Field | Description |
|-------|-------------|
| **Feature ID** | Unique identifier (e.g., `GO-RE-001`) |
| **Python Source** | File path + function name (e.g., `risk_management.py:RiskManagementService.calculate_portfolio_risk()`) |
| **Go Target** | File path + function name (e.g., `internal/risk/portfolio.go:RiskCalculator.CalculatePortfolioRisk()`) |
| **Input Schema** | JSON schema or protobuf message type for inputs |
| **Output Schema** | JSON schema or protobuf message type for outputs |
| **Business Logic Hash** | SHA-256 of the normalized business logic description |
| **Python Test File** | Path to existing Python test covering this feature |
| **Go Test File** | Path to new Go test mirroring the Python test |
| **Golden File** | Path to golden input/output capture file |
| **Precision Requirement** | Tolerance (e.g., "exact match", "within 0.01%", "within 1 cent") |
| **Status** | NOT_STARTED / IN_PROGRESS / IMPLEMENTED / TESTED / VERIFIED / CERTIFIED |
| **Certified By** | Auditor sign-off (must be different person than implementer) |
| **Certification Date** | ISO 8601 timestamp |

### 2.2 API Contract Registry

Every endpoint served by Go that was previously served by Python.

| Endpoint | Method | Python Handler | Go Handler | Request Schema | Response Schema | Status Codes | Error Format | Contract Test |
|----------|--------|---------------|------------|----------------|----------------|--------------|-------------|---------------|

**Contract compliance means:**
- Same HTTP status codes for same error conditions
- Same JSON field names, types, and nesting
- Same error response structure: `{"detail": "...", "status_code": N}`
- Same pagination format (if applicable)
- Same header requirements (Authorization, Content-Type)

### 2.3 Data Integrity Verification Log

For each database table accessed by Go services:

| Table | Columns Read | Columns Written | Python ORM Model | Go Access Pattern | Index Usage | Transaction Boundaries | Verified |
|-------|-------------|----------------|-------------------|-------------------|-------------|----------------------|----------|
| `portfolios` | `id, user_id, total_value, cash_balance` | None (read-only for risk) | `Portfolio` | Direct SQL / sqlx | `idx_portfolios_user_id` | READ COMMITTED | [ ] |
| `holdings` | `id, portfolio_id, symbol, quantity, average_cost` | None (read-only for risk) | `Holding` | Direct SQL / sqlx | `idx_holdings_portfolio_id` | READ COMMITTED | [ ] |
| `trades` | All columns | `status, filled_quantity, filled_price, updated_at` | `Trade` | Direct SQL / sqlx | `idx_trades_portfolio_id`, `idx_trades_status` | SERIALIZABLE for writes | [ ] |
| `circuit_breaker_state` | `state_json, updated_at, instance_id` | `state_json, updated_at, instance_id` | `CircuitBreakerState` | Direct SQL / sqlx | PK only | READ COMMITTED | [ ] |

### 2.4 Performance SLA Registry

| Service | Metric | Python Baseline | Go Target | Go SLA (Must Meet) | Measurement Method |
|---------|--------|----------------|-----------|--------------------|--------------------|
| Market Data Gateway | Quote Latency P50 | 45ms | 4ms | < 20ms | Prometheus histogram |
| Market Data Gateway | Quote Latency P99 | 500ms | 25ms | < 100ms | Prometheus histogram |
| Market Data Gateway | Throughput | 1K/s | 150K/s | > 10K/s | Rate counter |
| Market Data Gateway | WebSocket fanout (1K) | 50ms | 2ms | < 10ms | Trace timing |
| Risk Engine | Full Portfolio Risk | 200ms | 15ms | < 50ms | Prometheus histogram |
| Risk Engine | VaR Calculation | 50ms | 3ms | < 15ms | Prometheus histogram |
| Risk Engine | Update Frequency | 1Hz | 10Hz | > 5Hz | Counter / interval |
| Order Router | Order Submit Latency | 100ms | 0.8ms | < 10ms | Prometheus histogram |
| Order Router | Throughput | 100/s | 50K/s | > 1K/s | Rate counter |
| Order Router | Queue Operations | 1ms | 1us | < 100us | Benchmark test |

### 2.5 Security Posture Checklist

| Requirement | Python Implementation | Go Equivalent | Verified |
|-------------|----------------------|---------------|----------|
| JWT validation on every request | FastAPI Depends(get_current_user) | gRPC interceptor / middleware | [ ] |
| API key rotation for Alpaca | `get_secret()` from GCP Secret Manager | Same GCP Secret Manager client | [ ] |
| Rate limiting per user | In-memory + Redis fallback (`security.py`) | Go rate limiter (token bucket) | [ ] |
| PII never in logs | Structured logging with scrubbing | `slog` with PII filter hook | [ ] |
| TLS for all inter-service communication | Cloud Run default | gRPC TLS / mTLS | [ ] |
| Input validation (symbol format, quantity bounds) | Pydantic v2 models | Go struct validation tags + custom validators | [ ] |
| Paper/Live mode isolation | `AlpacaBroker(use_paper=True/False)` | Build-time or env-var flag, never runtime toggle | [ ] |
| No secrets in environment (use Secret Manager) | `get_secret()` | Same pattern via GCP client library | [ ] |

---

## 3. Drift Detection Strategy

### 3.1 Schema Drift Detection

**Problem:** Go and Python services return JSON responses consumed by the React frontend and auto-trading loop. Any structural difference causes silent failures.

**Strategy: Contract-First with JSON Schema Validation**

```
Phase 1: CAPTURE (Before Go development begins)
  - For each Python endpoint being migrated, capture 100+ real response samples
  - Generate JSON Schema from samples using json-schema-inferrer
  - Store schemas in: /backend/contracts/schemas/{service}/{endpoint}.schema.json
  - These schemas become the SINGLE SOURCE OF TRUTH

Phase 2: VALIDATE (During Go development)
  - Go service responses are validated against the same JSON schema in CI
  - Tool: github.com/santhosh-tekuri/jsonschema/v5 (Go)
  - Any schema violation = build failure

Phase 3: MONITOR (In production, during shadow mode)
  - Sidecar comparison proxy intercepts both Python and Go responses
  - Structural diff tool compares field presence, types, nesting
  - Alert on ANY structural divergence (even if values differ)
```

**Implementation:**

```
/backend/contracts/
  schemas/
    market-gateway/
      get_quote.schema.json
      get_quotes.schema.json
      stream_quote.schema.json
    risk-engine/
      portfolio_risk.schema.json
      trade_assessment.schema.json
      circuit_breaker_status.schema.json
    order-router/
      submit_order.schema.json
      order_status.schema.json
      execution_report.schema.json
  golden/
    market-gateway/
      get_quote_AAPL.golden.json
      get_quote_BTCUSD.golden.json
    risk-engine/
      portfolio_risk_3_holdings.golden.json
      portfolio_risk_empty.golden.json
      portfolio_risk_single.golden.json
    order-router/
      submit_market_buy.golden.json
      submit_limit_sell.golden.json
      partial_fill.golden.json
```

### 3.2 Logic Drift Detection

**Problem:** The Go Risk Engine must produce mathematically identical results to Python for VaR, Beta, Sharpe, Drawdown, and HHI calculations. Even tiny numerical differences can flip a APPROVED/REJECTED decision.

**Strategy: Differential Testing with Fixed-Seed Inputs**

```
Step 1: REFERENCE IMPLEMENTATION (Python)
  - Create a standalone Python script that:
    1. Accepts JSON portfolio input (positions, returns, weights)
    2. Runs RiskManagementService.calculate_portfolio_risk()
    3. Outputs JSON with all computed metrics
  - This script becomes the "oracle"
  - Located at: /backend/tests/golden/risk_oracle.py

Step 2: GO IMPLEMENTATION
  - Go Risk Engine accepts same JSON input
  - Outputs same JSON structure
  - Located at: /backend/go/risk-engine/cmd/oracle/main.go

Step 3: COMPARISON HARNESS
  - CI job runs both oracles with 1000+ test vectors
  - Compares every numeric field with configurable tolerance
  - Default tolerance: 0.0001 (0.01%) for percentages, $0.01 for dollar amounts
  - ANY field exceeding tolerance = CRITICAL CI failure
  - Located at: /backend/tests/golden/compare_risk.sh

Step 4: CONTINUOUS MONITORING
  - Cron job runs comparison daily with randomized portfolios
  - Alerts on any drift introduced by dependency updates (numpy, gonum)
```

**Tolerance Matrix (Risk Engine):**

| Metric | Absolute Tolerance | Relative Tolerance | Rationale |
|--------|-------------------|-------------------|-----------|
| VaR (95% daily) | $0.01 | 0.01% | Financial precision requirement |
| CVaR (95% daily) | $0.01 | 0.01% | Financial precision requirement |
| Portfolio Beta | N/A | 0.001 | Statistical measure, small differences acceptable |
| Sharpe Ratio | N/A | 0.001 | Statistical measure |
| Max Drawdown | N/A | 0.0001 | Percentage, tight tolerance |
| Volatility | N/A | 0.001 | Statistical measure |
| Concentration (HHI) | N/A | 0.0001 | Sum of squared weights, deterministic |
| Risk Check Result | EXACT | N/A | Decision must be identical (APPROVED/WARNING/REJECTED) |

### 3.3 Data Drift Detection

**Problem:** Go and Python reading from the same database could produce different results due to ORM behavior, connection pooling, transaction isolation, or caching.

**Strategy: Read-Path Audit**

```
1. QUERY AUDIT
   - Extract every SQL query generated by Python SQLAlchemy ORM for migrated endpoints
   - Capture using SQLAlchemy event listeners: engine.echo = True
   - Verify Go sqlx queries produce identical result sets
   - Store captured queries in: /backend/contracts/queries/{service}/

2. TRANSACTION BOUNDARY AUDIT
   - Map every Python endpoint to its transaction boundaries
   - Order writes: MUST use SERIALIZABLE isolation
   - Risk reads: READ COMMITTED is acceptable (eventual consistency OK for metrics)
   - Market data reads: No transaction required (cache-first)

3. CONNECTION POOL VERIFICATION
   - Python: SQLAlchemy connection pool (pool_size=5, max_overflow=10)
   - Go: pgxpool with identical pool configuration
   - Verify: Go connection count does not exceed Python's under same load

4. SCHEMA MIGRATION COORDINATION
   - HARD RULE: All schema changes go through Alembic migrations FIRST
   - Go services MUST NOT run migrations
   - Go services read schema version from alembic_version table on startup
   - If schema version is unknown, Go service refuses to start (fail-safe)
```

### 3.4 Configuration Drift Detection

**Problem:** Risk parameters (max position size, daily loss limit, circuit breaker thresholds) must be identical across Python and Go services.

**Strategy: Single Source of Truth for Risk Configuration**

```
Current State (Python):
  - risk_config.py: Hardcoded defaults
  - circuit_breaker.py: Thresholds in CircuitBreaker class
  - risk_management.py: Constants at module level
  - adaptive_parameters.py: Dynamic parameter adjustment

Target State:
  - SINGLE config file: /backend/config/risk_parameters.yaml
  - Python reads via pydantic-settings or YAML loader
  - Go reads via viper or direct YAML parse
  - CI job validates both services parse identical values
  - Any parameter change requires PR review from both Python and Go owners

Config schema:
```

```yaml
# /backend/config/risk_parameters.yaml
version: "2026-02-25.1"

risk_limits:
  max_position_pct: 0.15          # 15% of portfolio
  max_daily_loss_pct: 0.05        # 5% daily loss trigger
  max_single_trade_pct: 0.10      # 10% of portfolio per trade
  min_cash_reserve_pct: 0.05      # Keep 5% cash minimum

var_parameters:
  confidence_level: 0.95
  z_score: 1.645
  trading_days_per_year: 252
  risk_free_rate: 0.04            # 4% annual
  lookback_days: 252

circuit_breaker:
  system:
    threshold: 0.10               # 10% portfolio loss
    cooldown_minutes: 30
  volatility:
    threshold_high: 0.25          # 25% annualized
    threshold_extreme: 0.40       # 40% annualized
  daily_loss:
    threshold_pct: 0.05           # 5% daily
    cooldown_minutes: 60
  api_failure:
    consecutive_failures: 3
    cooldown_minutes: 5

position_sizing:
  min_position_pct: 0.0001       # 0.01% minimum
  max_position_pct: 0.25         # 25% maximum (overridable by risk profile)
  default_confidence_weight: 0.5

market_hours:
  timezone: "America/New_York"
  open_hour: 9
  open_minute: 30
  close_hour: 16
  close_minute: 0
  early_close_hour: 13
  early_close_minute: 0
```

### 3.5 Deployment Drift Detection

**Problem:** After migration, multiple service versions will be running. We need to know exactly which version of each service is deployed at any time.

**Strategy: Version Manifest + Health Endpoint**

```
1. VERSION MANIFEST
   Every Go binary embeds build metadata at compile time:
     - Git commit SHA
     - Build timestamp
     - Go version
     - Config schema version (from risk_parameters.yaml)
   Injected via: go build -ldflags "-X main.Version=..."

2. HEALTH ENDPOINT CONTRACT
   Every Go service exposes: GET /health
   Response:
   {
     "service": "risk-engine",
     "version": "go-v1.0.0-abc1234",
     "config_version": "2026-02-25.1",
     "status": "healthy",
     "uptime_seconds": 3600,
     "python_parity_version": "commit-f22689b",
     "last_golden_test": "2026-02-25T10:00:00Z",
     "golden_test_status": "PASS"
   }

3. DEPLOYMENT REGISTRY
   Cloud Run service revisions tracked in:
   /backend/deployment/version_manifest.json
   Updated by CI on every deploy:
   {
     "python_api": {"revision": "elson-api-00042-abc", "commit": "f22689b"},
     "market_gateway": {"revision": "market-gw-00001-def", "commit": "..."},
     "risk_engine": {"revision": "risk-eng-00001-ghi", "commit": "..."},
     "order_router": {"revision": "order-rt-00001-jkl", "commit": "..."}
   }

4. CROSS-SERVICE COMPATIBILITY MATRIX
   Before deploy, CI verifies:
   - Go service config_version matches Python config_version
   - Go service protobuf schema version is compatible
   - Database schema version (alembic_version) is supported
```

---

## 4. Verification & Validation (V&V) Matrix

### 4.1 Market Data Gateway V&V

**Source:** `backend/app/services/market_data.py`, `market_data_processor.py`, `market_data_streaming_enhanced.py`
**Target:** `backend/go/market-gateway/`

| V&V ID | Category | Test Description | Input | Expected Output | Tolerance | Priority | Status |
|--------|----------|-----------------|-------|----------------|-----------|----------|--------|
| MDG-001 | Quote Accuracy | Single equity quote (AAPL) | `GET /quote?symbol=AAPL` | Price, bid, ask, volume match live provider | Exact (string comparison for prices) | P0 | [ ] |
| MDG-002 | Quote Accuracy | Crypto quote (BTC/USD) | `GET /quote?symbol=BTC/USD` | Price in USD, 8 decimal places | Exact | P0 | [ ] |
| MDG-003 | Quote Accuracy | Invalid symbol | `GET /quote?symbol=ZZZZZZZ` | 404 with error detail | Exact structure | P0 | [ ] |
| MDG-004 | Quote Accuracy | Batch quotes (10 symbols) | `GET /quotes?symbols=AAPL,MSFT,...` | All 10 quotes returned, no missing | Exact structure | P0 | [ ] |
| MDG-005 | Historical Data | Daily bars (1 year) | `GET /bars?symbol=AAPL&period=1y` | 252 trading days of OHLCV | Values match yfinance within 0.01% | P1 | [ ] |
| MDG-006 | Historical Data | Intraday bars (1 day, 5min) | `GET /bars?symbol=AAPL&period=1d&interval=5m` | 78 bars (6.5 hours / 5 min) | Values match provider | P1 | [ ] |
| MDG-007 | Historical Data | Weekend/holiday request | Request for Saturday data | Empty result or previous close | Match Python behavior | P1 | [ ] |
| MDG-008 | WebSocket Format | Subscribe to AAPL | `{"action":"subscribe","symbols":["AAPL"]}` | `{"type":"quote","symbol":"AAPL","price":...}` | JSON structure exact match | P0 | [ ] |
| MDG-009 | WebSocket Format | Multi-symbol subscribe | Subscribe to 50 symbols | All 50 receive updates | No missing symbols | P0 | [ ] |
| MDG-010 | WebSocket Format | Unsubscribe | `{"action":"unsubscribe","symbols":["AAPL"]}` | No more AAPL updates, others continue | Behavioral | P1 | [ ] |
| MDG-011 | WebSocket Format | Malformed message | `{"garbage": true}` | Error message, connection not closed | Match Python error format | P1 | [ ] |
| MDG-012 | Cache Behavior | Fresh cache hit | Request same symbol within TTL | Cached response, `is_stale: false` | Exact | P1 | [ ] |
| MDG-013 | Cache Behavior | Stale cache | Request after TTL but before stale TTL | Stale data returned, refresh triggered | Behavioral | P1 | [ ] |
| MDG-014 | Cache Behavior | Expired cache | Request after stale TTL | Fresh fetch from provider | Behavioral | P1 | [ ] |
| MDG-015 | Cache Behavior | Force refresh | `GET /quote?symbol=AAPL&force_refresh=true` | Always fetches from provider | Latency > cache hit | P2 | [ ] |
| MDG-016 | Provider Fallback | Primary provider down | Mock Yahoo Finance failure | Fallback to Alpha Vantage | Data returned, source field updated | P0 | [ ] |
| MDG-017 | Provider Fallback | All providers down | Mock all provider failures | 503 with graceful error | Match Python 503 format | P0 | [ ] |
| MDG-018 | Provider Fallback | Provider recovery | Primary comes back after fallback | Switches back to primary | Source field updated | P2 | [ ] |
| MDG-019 | Rate Limit | Exceed provider rate limit | 100 rapid requests | Queued and throttled, no 429 to user | All requests eventually served | P1 | [ ] |
| MDG-020 | Rate Limit | User-level rate limit | >60 requests/minute from one user | 429 after threshold | Match Python rate limit behavior | P1 | [ ] |
| MDG-021 | Market Hours | Quote during market hours | Request at 2:00 PM ET on trading day | Live quote | Fresh data | P1 | [ ] |
| MDG-022 | Market Hours | Quote outside market hours | Request at 8:00 PM ET | Last close data or pre-market | Match Python behavior | P1 | [ ] |
| MDG-023 | Market Hours | NYSE holiday | Request on Thanksgiving | Holiday message, previous close data | Match Python holiday handling | P2 | [ ] |

### 4.2 Risk Engine V&V

**Source:** `backend/app/services/risk_management.py`, `backend/app/trading_engine/risk/`, `backend/app/trading_engine/engine/circuit_breaker.py`
**Target:** `backend/go/risk-engine/`

| V&V ID | Category | Test Description | Input | Expected Output | Tolerance | Priority | Status |
|--------|----------|-----------------|-------|----------------|-----------|----------|--------|
| RE-001 | VaR | Parametric VaR, 3-stock portfolio | Positions with 252 days of returns | VaR95 in USD | $0.01 or 0.01% | P0 | [ ] |
| RE-002 | VaR | VaR with single position | One stock, full weight | VaR = position_vol * Z * value | $0.01 | P0 | [ ] |
| RE-003 | VaR | VaR with empty portfolio | No positions | VaR = 0 | Exact | P0 | [ ] |
| RE-004 | VaR | VaR with correlated positions | 2 highly correlated stocks | Portfolio VaR < sum of individual VaRs | Relationship preserved | P0 | [ ] |
| RE-005 | CVaR | Expected shortfall | Same as RE-001 | CVaR >= VaR | $0.01 or 0.01% | P0 | [ ] |
| RE-006 | Beta | Portfolio beta, diversified | 10-stock portfolio | Weighted beta | 0.001 | P0 | [ ] |
| RE-007 | Beta | Beta with no benchmark data | Empty benchmark returns | Default beta = 1.0 | Exact | P0 | [ ] |
| RE-008 | Beta | Beta with single data point | 1 day of returns | Default beta = 1.0 | Exact | P1 | [ ] |
| RE-009 | Sharpe | Sharpe ratio, positive | Portfolio with 15% return, 20% vol | (0.15 - 0.04) / 0.20 = 0.55 | 0.001 | P0 | [ ] |
| RE-010 | Sharpe | Sharpe ratio, zero volatility | All returns identical | Sharpe = 0 | Exact | P0 | [ ] |
| RE-011 | Sharpe | Sharpe ratio, negative | Portfolio with -5% return | Negative Sharpe | 0.001 | P1 | [ ] |
| RE-012 | Drawdown | Max drawdown calculation | Known drawdown series | Exact drawdown percentage | 0.0001 | P0 | [ ] |
| RE-013 | Drawdown | No drawdown (monotone increasing) | Monotonically increasing equity curve | Drawdown = 0 | Exact | P1 | [ ] |
| RE-014 | HHI | Concentration, equal weights | 10 positions, 10% each | HHI = 0.10 | 0.0001 | P0 | [ ] |
| RE-015 | HHI | Concentration, single position | 1 position, 100% | HHI = 1.0 | Exact | P0 | [ ] |
| RE-016 | HHI | Concentration, extreme skew | 1 position at 90%, 10 at 1% | HHI = 0.8110 | 0.0001 | P1 | [ ] |
| RE-017 | Decision | APPROVED: Low risk trade | Small position, diversified portfolio | `check_result: "approved"` | Exact decision | P0 | [ ] |
| RE-018 | Decision | WARNING: Moderate risk | 15% position concentration | `check_result: "warning"` | Exact decision | P0 | [ ] |
| RE-019 | Decision | REJECTED: Exceeds limits | 50% position, circuit breaker active | `check_result: "rejected"` | Exact decision | P0 | [ ] |
| RE-020 | Decision | REQUIRES_CONFIRMATION | Trade OK but unusual size | `check_result: "requires_confirmation"` | Exact decision | P0 | [ ] |
| RE-021 | Circuit Breaker | System breaker trigger | Daily loss > 10% | Status = OPEN, trading suspended | Exact state | P0 | [ ] |
| RE-022 | Circuit Breaker | Volatility breaker | Annualized vol > 40% | Status = RESTRICTED or OPEN | Match Python thresholds | P0 | [ ] |
| RE-023 | Circuit Breaker | Daily loss breaker | Daily P&L < -5% | Status changes, cooldown starts | Match Python cooldown logic | P0 | [ ] |
| RE-024 | Circuit Breaker | Breaker recovery (half-open) | After cooldown expires | Status = HALF_OPEN, limited trading | Match Python state machine | P0 | [ ] |
| RE-025 | Circuit Breaker | Breaker persistence | Service restart | State restored from DB | `circuit_breaker_state` table read | P0 | [ ] |
| RE-026 | Edge Case | Penny stock (price < $1) | Position with $0.50 stock | Correct VaR, no division by zero | $0.01 | P0 | [ ] |
| RE-027 | Edge Case | Very large portfolio ($10M+) | 100 positions, $10M total | All metrics computed correctly | 0.01% | P1 | [ ] |
| RE-028 | Edge Case | Negative returns only | All positions down every day | Max drawdown = correct, VaR = large | 0.01% | P1 | [ ] |
| RE-029 | Edge Case | Zero-value position | Holding with quantity=0 | Excluded from calculations | No NaN/Inf | P0 | [ ] |
| RE-030 | Precision | Float vs Decimal comparison | Same portfolio in Python (float) and Go | Results within tolerance | See tolerance matrix | P0 | [ ] |
| RE-031 | Concurrency | Parallel risk calculations | 100 simultaneous portfolio risk requests | All return correct results | No race conditions (go test -race) | P0 | [ ] |

### 4.3 Order Router V&V

**Source:** `backend/app/trading_engine/engine/trade_executor.py`, `backend/app/services/broker/alpaca.py`, execution strategies
**Target:** `backend/go/order-router/`

| V&V ID | Category | Test Description | Input | Expected Output | Tolerance | Priority | Status |
|--------|----------|-----------------|-------|----------------|-----------|----------|--------|
| OR-001 | Execution | Market buy, paper mode | BUY 10 AAPL, paper=true | Order filled, paper broker response | Exact status codes | P0 | [ ] |
| OR-002 | Execution | Market sell, paper mode | SELL 10 AAPL (existing position) | Order filled | Exact | P0 | [ ] |
| OR-003 | Execution | Limit buy | BUY 10 AAPL @ $150 | Order queued, fills when price <= $150 | Exact queue behavior | P0 | [ ] |
| OR-004 | Execution | Stop loss | SELL 10 AAPL stop @ $140 | Triggers when price <= $140, market order | Exact trigger logic | P0 | [ ] |
| OR-005 | Execution | Stop limit | SELL 10 AAPL stop $140, limit $139 | Triggers at $140, fills only >= $139 | Exact | P1 | [ ] |
| OR-006 | Partial Fill | Partial fill handling | BUY 1000 low-liquidity stock | Multiple fill events, running total | Quantity tracking exact | P0 | [ ] |
| OR-007 | Partial Fill | Partial fill status | After 500 of 1000 filled | Status = PARTIALLY_FILLED | Exact | P0 | [ ] |
| OR-008 | Partial Fill | Full fill after partials | After all fills complete | Status = FILLED, total = requested | Exact | P0 | [ ] |
| OR-009 | TWAP | Time-Weighted Average Price | BUY 1000 AAPL over 1 hour | ~17 child orders (every ~3.5 min) | Slice count +/- 1 | P1 | [ ] |
| OR-010 | VWAP | Volume-Weighted Average Price | BUY 1000 AAPL tracking VWAP | Execution price within 0.1% of VWAP | 0.1% of VWAP | P1 | [ ] |
| OR-011 | Iceberg | Iceberg order | BUY 10000, display 500 | Only 500 visible at a time | Queue management | P1 | [ ] |
| OR-012 | Trailing Stop | Trailing stop buy | Trail $5 from high | Adjusts trigger as price rises | Exact adjustment logic | P1 | [ ] |
| OR-013 | Trailing Stop | Trailing stop sell | Trail $3 from high | Triggers when price drops $3 from peak | Exact trigger | P1 | [ ] |
| OR-014 | OCO | One-Cancels-Other | Take profit $160 + Stop loss $140 | First hit cancels the other | Exact lifecycle | P1 | [ ] |
| OR-015 | OCO | OCO with partial fills | Profit target partially filled | Stop still active until profit fully filled | Correct state machine | P1 | [ ] |
| OR-016 | Paper/Live | Paper mode isolation | Paper trade submitted | NEVER hits live Alpaca API | Verify with mock/spy | P0 | [ ] |
| OR-017 | Paper/Live | Live mode gating | Live trade submitted | Hits real Alpaca API (test with paper creds) | Correct URL routing | P0 | [ ] |
| OR-018 | Paper/Live | Mode cannot change at runtime | Attempt to toggle paper/live mid-session | Rejected -- restart required | Error returned | P0 | [ ] |
| OR-019 | Kill Switch | Global kill switch activation | Admin sends kill signal | All pending orders cancelled, no new orders | Order count = 0 | P0 | [ ] |
| OR-020 | Kill Switch | Kill switch persistence | Service restart after kill | Kill switch state restored | DB-backed state | P0 | [ ] |
| OR-021 | Kill Switch | Kill switch release | Admin releases kill | Trading resumes, queued orders re-evaluated | Correct resume behavior | P0 | [ ] |
| OR-022 | Idempotency | Duplicate order submission | Same order ID submitted twice | Second submission returns existing order | No double execution | P0 | [ ] |
| OR-023 | Idempotency | Retry after timeout | Order submitted, no response, retry | Single execution | Idempotency key check | P0 | [ ] |
| OR-024 | Error Handling | Alpaca API 403 (insufficient funds) | Order exceeding buying power | Correct error mapping: "Insufficient funds" | Match Python error messages | P0 | [ ] |
| OR-025 | Error Handling | Alpaca API 422 (invalid params) | Invalid symbol "ZZZZZZZ" | Correct error mapping | Match Python messages | P0 | [ ] |
| OR-026 | Error Handling | Alpaca API 429 (rate limit) | Rapid order submission | Retry with backoff, not user-facing 429 | Transparent retry | P1 | [ ] |
| OR-027 | Error Handling | Alpaca API 500 | Alpaca server error | Retry up to 3 times, then fail | Same retry policy as Python | P0 | [ ] |
| OR-028 | Error Handling | Network timeout to Alpaca | Connection hangs | Timeout at 10s, retry | Same timeout as Python | P0 | [ ] |
| OR-029 | Position Tracking | Buy updates average cost | BUY 10 @ $100, BUY 10 @ $110 | Avg cost = $105 | $0.01 | P0 | [ ] |
| OR-030 | Position Tracking | Sell reduces quantity | SELL 5 from 20 shares | Quantity = 15, avg cost unchanged | Exact | P0 | [ ] |
| OR-031 | Position Tracking | Full close deletes position | SELL all shares | Position removed | Clean state | P0 | [ ] |
| OR-032 | Crypto | Crypto symbol normalization | BUY BTC/USD | Order uses BTCUSD for submission | Match alpaca.py normalization | P1 | [ ] |
| OR-033 | Crypto | Options symbol parsing | AAPL260320C00150000 | Correctly identified as option | Regex match | P2 | [ ] |
| OR-034 | Queue Ordering | FIFO for same priority | 3 orders at same priority | Executed in submission order | Exact order | P0 | [ ] |
| OR-035 | Queue Ordering | Priority ordering | High-priority before low-priority | High-priority dequeued first | Exact order | P0 | [ ] |
| OR-036 | Concurrency | Concurrent order submissions | 100 simultaneous orders | All processed, no lost orders | go test -race clean | P0 | [ ] |

---

## 5. Regression Test Plan

### 5.1 Shadow Mode Architecture

The primary regression strategy is **shadow mode**: both Python and Go services process every request, but only Python's response is returned to the user. Go's response is logged and compared.

```
                   +---> Python Service ---> Response to User
                   |
User Request ----> Load Balancer (with shadow)
                   |
                   +---> Go Service ---> Shadow Log (comparison only)
                                          |
                                          v
                                    Comparison Worker
                                          |
                                    +-----+-----+
                                    |           |
                                  MATCH      DIVERGENCE
                                    |           |
                                  Log OK     ALERT + Log
```

**Implementation via Cloud Run Traffic Splitting:**

```yaml
# Phase 1: 0% Go traffic (shadow only)
gcloud run services update elson-api \
  --tag shadow-go=0 \
  --set-env-vars SHADOW_GO_ENDPOINT=https://market-gateway-xxx.run.app

# Phase 2: 1% Go traffic (canary)
# Phase 3: 10% Go traffic
# Phase 4: 50% Go traffic
# Phase 5: 100% Go traffic
# Phase 6: Python decommission (NEVER delete, archive only)
```

### 5.2 Golden File Testing Strategy

**Phase 1: Capture (Python)**

```python
# /backend/tests/golden/capture_golden_files.py
"""
Run against LIVE Python API to capture golden input/output pairs.
Each capture includes:
  - Request (method, path, headers, body)
  - Response (status, headers, body)
  - Timestamp
  - Service version (git commit)
"""

CAPTURE_SCENARIOS = {
    "market_gateway": [
        {"method": "GET", "path": "/api/v1/market/quote/AAPL", "tag": "equity_quote"},
        {"method": "GET", "path": "/api/v1/market/quote/BTC/USD", "tag": "crypto_quote"},
        {"method": "GET", "path": "/api/v1/market/quotes?symbols=AAPL,MSFT,GOOGL", "tag": "batch_quotes"},
        {"method": "GET", "path": "/api/v1/market/history/AAPL?period=1m", "tag": "history_1m"},
    ],
    "risk_engine": [
        {"method": "GET", "path": "/api/v1/risk/portfolio-metrics", "tag": "portfolio_metrics"},
        {"method": "POST", "path": "/api/v1/risk/assess-trade", "body": SAMPLE_TRADE, "tag": "trade_assessment"},
        {"method": "GET", "path": "/api/v1/risk/risk-score/AAPL", "tag": "symbol_risk"},
        {"method": "POST", "path": "/api/v1/risk/validate-portfolio", "body": SAMPLE_PORTFOLIO, "tag": "validate"},
    ],
    "order_router": [
        {"method": "POST", "path": "/api/v1/trading/buy", "body": MARKET_BUY, "tag": "market_buy"},
        {"method": "POST", "path": "/api/v1/trading/sell", "body": MARKET_SELL, "tag": "market_sell"},
        {"method": "GET", "path": "/api/v1/trading/orders", "tag": "open_orders"},
        {"method": "DELETE", "path": "/api/v1/trading/orders/{id}", "tag": "cancel_order"},
    ],
}
```

**Phase 2: Validate (Go)**

```go
// /backend/go/shared/goldentest/golden_test.go
func TestGoldenFiles(t *testing.T) {
    goldenDir := "../../../contracts/golden/"
    files, _ := filepath.Glob(goldenDir + "*.golden.json")

    for _, file := range files {
        t.Run(filepath.Base(file), func(t *testing.T) {
            golden := loadGoldenFile(file)

            // Replay request against Go service
            resp := replayRequest(golden.Request)

            // Compare response structure (not values for live data)
            assertStructuralMatch(t, golden.Response, resp)

            // For deterministic endpoints, compare values
            if golden.Deterministic {
                assertValueMatch(t, golden.Response, resp, golden.Tolerance)
            }
        })
    }
}
```

### 5.3 Property-Based Testing

For the Risk Engine, property-based testing catches edge cases that golden files miss.

**Properties to verify:**

```
PROPERTY 1: VaR Monotonicity
  For any portfolio P, adding a position with higher volatility
  must increase or maintain portfolio VaR.
  forall P, pos: VaR(P + pos) >= VaR(P) if vol(pos) > vol(P)

PROPERTY 2: HHI Bounds
  For any portfolio P with N positions:
  1/N <= HHI(P) <= 1.0

PROPERTY 3: Drawdown Bounds
  For any return series: 0.0 <= MaxDrawdown <= 1.0

PROPERTY 4: Beta Neutrality
  A portfolio that IS the benchmark must have beta = 1.0

PROPERTY 5: Sharpe Sign
  If annualized_return > risk_free_rate, Sharpe > 0
  If annualized_return < risk_free_rate, Sharpe < 0

PROPERTY 6: Order Conservation
  For any set of N submitted orders, exactly N execution reports
  are produced (filled, cancelled, or rejected -- never lost).

PROPERTY 7: Position Invariant
  After BUY x then SELL x of same symbol: position = 0

PROPERTY 8: Kill Switch Completeness
  After kill switch activation, open_orders.count() == 0
```

**Go implementation using `gopter`:**

```go
// /backend/go/risk-engine/internal/risk/portfolio_property_test.go
func TestHHIBounds(t *testing.T) {
    properties := gopter.NewProperties(gopter.DefaultTestParameters())

    properties.Property("HHI is between 1/N and 1.0", prop.ForAll(
        func(weights []float64) bool {
            // Normalize weights
            total := sum(weights)
            for i := range weights {
                weights[i] /= total
            }
            hhi := calculateHHI(weights)
            n := float64(len(weights))
            return hhi >= 1.0/n - 0.0001 && hhi <= 1.0 + 0.0001
        },
        gen.SliceOfN(10, gen.Float64Range(0.01, 1.0)),
    ))

    properties.TestingRun(t)
}
```

### 5.4 Load Testing Protocol

**Tool:** `k6` (Grafana) or `ghz` (gRPC)

```
PHASE 1: Baseline (Python only)
  - 100 concurrent users, 5-minute sustained
  - Measure: P50, P95, P99 latency; throughput; error rate
  - Record as baseline

PHASE 2: Go Service Solo
  - Same load against Go service
  - Must meet SLA targets from Section 2.4
  - Run with: go test -race -count=1 (verify no races under load)

PHASE 3: Shadow Mode Load
  - Both Python and Go processing same requests
  - Verify Go does not degrade Python's performance
  - Compare response divergence rate

PHASE 4: Soak Test
  - 24-hour sustained test at 50% peak load
  - Monitor: memory growth (goroutine leak), connection pool exhaustion, cache size
  - Go services must have ZERO memory growth trend over 24 hours
```

**k6 Script Template:**

```javascript
// /backend/tests/load/risk_engine_load.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export let options = {
  stages: [
    { duration: '1m', target: 10 },    // Ramp up
    { duration: '5m', target: 100 },   // Sustained
    { duration: '1m', target: 0 },     // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<50'],    // P95 < 50ms (Go SLA)
    http_req_failed: ['rate<0.001'],    // Error rate < 0.1%
  },
};

export default function () {
  let res = http.post('http://localhost:50052/risk.RiskService/CalculatePortfolioRisk',
    JSON.stringify(SAMPLE_PORTFOLIO));
  check(res, { 'status is 200': (r) => r.status === 200 });
  sleep(0.1);
}
```

---

## 6. Production Readiness Checklist

### 6.1 Market Data Gateway -- Production Readiness

```
FUNCTIONAL REQUIREMENTS
[ ] All 23 V&V tests (MDG-001 through MDG-023) pass
[ ] Golden file tests pass for all captured scenarios
[ ] Provider fallback chain works (Yahoo -> Alpha Vantage -> Finnhub -> Polygon)
[ ] Cache TTL behavior matches Python (fresh/stale/expired)
[ ] WebSocket message format matches Python exactly (JSON structure)
[ ] NYSE holiday calendar produces same results as Python for 2026
[ ] Market hours detection matches Python (open/close/early close)
[ ] Batch quote endpoint handles 100+ symbols without timeout
[ ] Error responses match Python error format exactly

NON-FUNCTIONAL REQUIREMENTS
[ ] P50 latency < 20ms (quote request)
[ ] P99 latency < 100ms (quote request)
[ ] Throughput > 10K requests/second (benchmark test)
[ ] WebSocket fanout < 10ms for 1000 subscribers
[ ] Memory usage stable over 24-hour soak test (no leak)
[ ] Graceful shutdown (drains WebSocket connections, flushes cache)
[ ] Startup time < 5 seconds
[ ] Health endpoint responds within 100ms

SECURITY REQUIREMENTS
[ ] No Alpaca API keys in Go binary or logs
[ ] GCP Secret Manager integration tested
[ ] Rate limiting per user ID implemented and tested
[ ] Input validation: symbol format, query parameter bounds
[ ] No PII in structured logs
[ ] TLS for gRPC inter-service communication

MONITORING REQUIREMENTS
[ ] Prometheus metrics: request_duration_seconds (histogram)
[ ] Prometheus metrics: request_total (counter by status)
[ ] Prometheus metrics: cache_hit_ratio (gauge)
[ ] Prometheus metrics: websocket_connections (gauge)
[ ] Prometheus metrics: provider_errors_total (counter by provider)
[ ] Structured JSON logging (compatible with Cloud Logging)
[ ] Trace propagation (OpenTelemetry context from Python)
[ ] Alert: cache_hit_ratio < 0.5 for > 5 minutes
[ ] Alert: provider_errors_total > 10/minute

ROLLBACK VERIFICATION
[ ] Can route 100% traffic back to Python in < 2 minutes
[ ] Cloud Run revision history preserved (previous Python revision)
[ ] No database schema changes that would break Python rollback
[ ] Rollback tested in staging environment
[ ] Rollback runbook documented and rehearsed

DOCUMENTATION
[ ] API contract documentation (OpenAPI or protobuf docs)
[ ] Deployment runbook (Cloud Run commands)
[ ] Troubleshooting guide (common failure modes)
[ ] Architecture diagram (data flow from providers to cache to clients)
```

### 6.2 Risk Engine -- Production Readiness

```
FUNCTIONAL REQUIREMENTS
[ ] All 31 V&V tests (RE-001 through RE-031) pass
[ ] Golden file tests pass for all portfolio scenarios
[ ] Property-based tests pass (1000 iterations minimum)
[ ] Differential test: Go vs Python oracle, 1000 portfolios, all within tolerance
[ ] Circuit breaker state machine matches Python exactly (all transitions)
[ ] Circuit breaker persistence: state survives restart via DB
[ ] Risk parameters loaded from shared YAML config
[ ] All 4 risk check results produced correctly (APPROVED/WARNING/REJECTED/REQUIRES_CONFIRMATION)
[ ] VaR, CVaR, Beta, Sharpe, Drawdown, HHI all within tolerance
[ ] Edge cases: empty portfolio, single position, penny stocks, $10M+ portfolio

NON-FUNCTIONAL REQUIREMENTS
[ ] Full portfolio risk calculation < 50ms (100 positions)
[ ] VaR calculation < 15ms
[ ] Risk stream updates at > 5Hz
[ ] Memory usage < 50MB (100 positions)
[ ] go test -race passes with 0 data races
[ ] Memory stable over 24-hour soak test
[ ] Graceful shutdown (completes in-flight calculations)

SECURITY REQUIREMENTS
[ ] User ID validated against authenticated session
[ ] No portfolio data leaked across user boundaries
[ ] Risk parameters cannot be modified via API (config-only)
[ ] GCP Secret Manager for database credentials

MONITORING REQUIREMENTS
[ ] Prometheus metrics: risk_calculation_duration_seconds (histogram by type)
[ ] Prometheus metrics: circuit_breaker_state (gauge by breaker type)
[ ] Prometheus metrics: risk_decisions_total (counter by result)
[ ] Prometheus metrics: goroutine_count (gauge -- monitor for leaks)
[ ] Alert: any CRITICAL risk decision divergence from Python shadow
[ ] Alert: calculation_duration P99 > 100ms
[ ] Alert: goroutine_count growing > 10/minute for > 5 minutes

ROLLBACK VERIFICATION
[ ] Python risk_management.py still deployed and functional
[ ] gRPC routing can be reverted to Python in < 2 minutes
[ ] circuit_breaker_state table compatible with both Python and Go readers
[ ] No risk parameter changes during migration window

DOCUMENTATION
[ ] Mathematical specification for each metric (formulae, references)
[ ] Tolerance justification document
[ ] Circuit breaker state machine diagram
[ ] Risk parameter configuration guide
```

### 6.3 Order Router -- Production Readiness

```
FUNCTIONAL REQUIREMENTS
[ ] All 36 V&V tests (OR-001 through OR-036) pass
[ ] Golden file tests pass for all order scenarios
[ ] Alpaca API integration tested with paper trading account
[ ] Paper/live mode isolation verified (paper NEVER hits live API)
[ ] All order types: market, limit, stop, stop-limit
[ ] Partial fill handling: status tracking, average price calculation
[ ] TWAP execution: slicing, timing, child order management
[ ] VWAP execution: volume profile tracking, execution benchmarking
[ ] Iceberg orders: display quantity management, queue replenishment
[ ] Trailing stop: dynamic trigger adjustment, both buy and sell
[ ] OCO orders: correct cancellation lifecycle
[ ] Kill switch: activation, persistence, release
[ ] Idempotency: duplicate detection, no double execution
[ ] All Alpaca error codes mapped to user-friendly messages
[ ] Crypto symbol normalization (BTC/USD -> BTCUSD for orders)
[ ] Queue ordering: FIFO within same priority, priority ordering

NON-FUNCTIONAL REQUIREMENTS
[ ] Order submit latency < 10ms (excluding Alpaca API)
[ ] Queue throughput > 1K orders/second
[ ] Queue operations < 100us
[ ] Zero order loss under any failure mode (WAL or persistent queue)
[ ] go test -race passes with 0 data races
[ ] Memory stable over 24-hour soak test
[ ] Graceful shutdown (no orders in-flight lost)

SECURITY REQUIREMENTS
[ ] Alpaca API credentials from GCP Secret Manager only
[ ] Paper/live mode set at startup, not toggleable at runtime
[ ] User authorization verified before order submission
[ ] Order size limits enforced (max position %, max order value)
[ ] Audit log for every order submission, fill, and cancellation
[ ] No Alpaca API keys in logs at any level

MONITORING REQUIREMENTS
[ ] Prometheus metrics: order_submit_duration_seconds (histogram)
[ ] Prometheus metrics: order_fill_duration_seconds (histogram)
[ ] Prometheus metrics: orders_total (counter by status: filled, cancelled, rejected)
[ ] Prometheus metrics: queue_depth (gauge)
[ ] Prometheus metrics: alpaca_api_duration_seconds (histogram)
[ ] Prometheus metrics: alpaca_api_errors_total (counter by error code)
[ ] Alert: queue_depth > 100 for > 1 minute
[ ] Alert: alpaca_api_errors_total > 5/minute
[ ] Alert: any order_submit_duration P99 > 1 second
[ ] Alert: kill_switch activated (immediate page)

ROLLBACK VERIFICATION
[ ] Python trade_executor.py and alpaca.py still deployed
[ ] All pending orders in Go queue can be drained before rollback
[ ] No orders lost during rollback transition
[ ] Rollback tested with live paper trading account
[ ] Rollback runbook includes: drain queue -> cancel pending -> switch routing -> verify

DOCUMENTATION
[ ] Order lifecycle state machine diagram
[ ] Alpaca API error code mapping table
[ ] Kill switch activation and release runbook
[ ] TWAP/VWAP/Iceberg algorithm specification
[ ] Paper vs live mode configuration guide
```

---

## 7. Incident Response Additions

### 7.1 New Runbooks Required

| Runbook ID | Title | Trigger | Owner |
|------------|-------|---------|-------|
| RB-GO-001 | Market Data Gateway Degraded | Cache hit ratio < 50% for > 5 min | SRE |
| RB-GO-002 | Risk Engine Divergence | Shadow comparison shows >0.1% drift | Fintech Integrity Auditor |
| RB-GO-003 | Order Router Queue Backup | Queue depth > 100 for > 1 min | SRE + Quant Architect |
| RB-GO-004 | Alpaca API Integration Failure | 3+ consecutive Alpaca 5xx errors | SRE |
| RB-GO-005 | Circuit Breaker State Corruption | Go and Python disagree on breaker state | Fintech Integrity Auditor |
| RB-GO-006 | Kill Switch Activation | Manual or automated kill switch | On-call engineer |
| RB-GO-007 | Go Service Goroutine Leak | Goroutine count growing > 10/min for > 5 min | SRE |
| RB-GO-008 | Go Service Memory Pressure | RSS > 80% of container limit | SRE |
| RB-GO-009 | Rollback to Python | Any CRITICAL issue in Go service | On-call engineer |
| RB-GO-010 | Dual-Write Inconsistency | Go and Python write conflicting data to same DB table | Fintech Integrity Auditor |

### 7.2 Runbook Template: RB-GO-009 (Rollback to Python)

```
TITLE: Emergency Rollback from Go to Python Service
SEVERITY: CRITICAL (only invoked for production-impacting issues)

PREREQUISITES:
  - Confirm Python service revision is still deployed (check Cloud Run revisions)
  - Confirm Python service health endpoint returns "healthy"

STEP 1: DRAIN GO SERVICE (2 minutes)
  a. Set Go service to reject new requests:
     gcloud run services update [GO_SERVICE] --max-instances=0
  b. Wait for in-flight requests to complete (watch queue depth metric)
  c. For Order Router: verify queue_depth = 0 before proceeding
     IF queue_depth > 0: wait up to 5 minutes, then cancel all pending orders

STEP 2: SWITCH ROUTING (1 minute)
  a. Update gRPC router to point back to Python:
     gcloud run services update elson-api \
       --set-env-vars RISK_ENGINE_URL=local \
       --set-env-vars MARKET_DATA_URL=local \
       --set-env-vars ORDER_ROUTER_URL=local
  b. Verify Python service is handling requests (check logs)

STEP 3: VERIFY (5 minutes)
  a. Run smoke test suite against Python endpoints
  b. Verify auto-trading loop is functional (if running)
  c. Check circuit breaker state consistency
  d. Verify no orphaned orders in Go queue

STEP 4: POST-MORTEM
  a. Preserve Go service logs (export to GCS bucket)
  b. Capture Go service metrics snapshot
  c. Create incident report with root cause
  d. Update this runbook if new failure mode discovered

ESCALATION:
  - If rollback fails: page Apex Coordinator + Reliability Sentinel
  - If orders were lost: page Quant Architect + immediate Alpaca support contact
  - If money was affected: page ALL senior engineers + legal notification within 1 hour
```

### 7.3 Escalation Paths

```
SEVERITY 1 (Money at Risk):
  Order Router submits incorrect order / double execution / live-when-paper
  0 min: Auto-alert all on-call engineers
  0 min: Kill switch auto-activates
  5 min: Rollback to Python (RB-GO-009)
  15 min: Apex Coordinator + Quant Architect paged
  30 min: Full incident bridge
  1 hour: Legal notification if customer funds affected

SEVERITY 2 (Risk Miscalculation):
  Risk Engine approves trade that Python would reject
  0 min: Alert Fintech Integrity Auditor
  5 min: Switch to Python risk engine (RB-GO-009 Step 2 only)
  15 min: Audit all trades approved by Go in last hour
  30 min: Determine if corrective trades needed

SEVERITY 3 (Data Quality):
  Market Data Gateway returns stale or incorrect prices
  0 min: Alert SRE
  5 min: Check provider health, cache state
  15 min: If not resolved, failover to Python market data
  30 min: Investigate root cause

SEVERITY 4 (Performance Degradation):
  Go service exceeds SLA but still functional
  0 min: Alert SRE
  15 min: Investigate (connection pool, goroutine count, memory)
  30 min: If not improving, scale up or rollback
  1 hour: Root cause analysis
```

### 7.4 Monitoring & Alerting Additions

**New Grafana Dashboards:**

```
1. "Go Microservices Overview"
   - Service health (up/down per service)
   - Request rate and error rate (per service)
   - Latency distributions (P50/P95/P99 per service)
   - Resource usage (CPU, memory, goroutines per service)

2. "Python vs Go Shadow Comparison"
   - Response divergence rate (per endpoint)
   - Latency comparison (Python vs Go, side by side)
   - Value divergence heatmap (which fields differ most)
   - Error category distribution

3. "Order Router Operations"
   - Queue depth over time
   - Order lifecycle funnel (submitted -> filled/rejected)
   - Alpaca API latency and error rate
   - Kill switch status (prominent indicator)
   - Paper vs live order count

4. "Risk Engine Accuracy"
   - VaR divergence from Python (histogram)
   - Decision agreement rate (APPROVED/REJECTED match %)
   - Circuit breaker state timeline
   - Calculation latency by metric type
```

**New Alert Rules (PagerDuty):**

```yaml
# /backend/monitoring/go_service_alerts.yaml
alerts:
  - name: go_order_router_kill_switch
    condition: kill_switch_active == 1
    severity: critical
    channel: pagerduty
    message: "Kill switch activated on Order Router -- all trading halted"

  - name: go_risk_engine_divergence
    condition: risk_decision_divergence_rate > 0.001  # 0.1%
    duration: 5m
    severity: critical
    channel: pagerduty
    message: "Risk Engine Go/Python decision divergence > 0.1%"

  - name: go_market_data_stale
    condition: cache_hit_ratio < 0.3
    duration: 10m
    severity: high
    channel: slack
    message: "Market Data Gateway cache hit ratio critically low"

  - name: go_goroutine_leak
    condition: rate(goroutine_count[5m]) > 10
    duration: 10m
    severity: high
    channel: slack
    message: "Goroutine count growing -- potential leak in {service}"

  - name: go_order_queue_backup
    condition: order_queue_depth > 50
    duration: 2m
    severity: high
    channel: pagerduty
    message: "Order queue depth > 50 -- possible processing stall"

  - name: go_alpaca_api_errors
    condition: rate(alpaca_api_errors_total[5m]) > 1
    duration: 5m
    severity: high
    channel: slack
    message: "Elevated Alpaca API error rate"
```

---

## 8. Change Management Process

### 8.1 API Contract Change Review

Any change to an API contract between Python and Go services requires the following process:

```
STEP 1: PROPOSAL
  - File a GitHub issue tagged `api-contract-change`
  - Include: endpoint affected, current schema, proposed schema, rationale
  - Include: backward compatibility analysis
  - Assign: both Python and Go service owners as reviewers

STEP 2: IMPACT ANALYSIS
  - Identify all consumers of the endpoint (frontend, auto-trading, EFT agents)
  - Determine if change is additive (new field) or breaking (removed/renamed field)
  - For breaking changes: create migration plan with version negotiation

STEP 3: SCHEMA UPDATE
  - Update JSON schema in /backend/contracts/schemas/
  - Update protobuf definition (if gRPC)
  - Generate golden file with new schema
  - Both Python and Go CI must pass against new schema

STEP 4: COORDINATED DEPLOY
  - For additive changes: Go deploys first (new field), then Python (if needed)
  - For breaking changes:
    a. Deploy version that supports BOTH old and new
    b. Migrate all consumers to new format
    c. Remove old format support
  - Never deploy a breaking change to one service without the other

STEP 5: VERIFICATION
  - Run shadow comparison with new schema
  - Verify frontend handles both old and new format (graceful degradation)
  - Run golden file tests
```

### 8.2 Feature Parity Verification After Each Change

```
After every Go service change (PR merged to main):

1. CI PIPELINE (Automated)
   [ ] Go unit tests pass (go test ./...)
   [ ] Go race detector clean (go test -race ./...)
   [ ] Go linter clean (golangci-lint run)
   [ ] Golden file tests pass
   [ ] JSON schema validation passes
   [ ] Differential oracle test passes (Go vs Python, 100 test vectors)

2. SHADOW MODE VERIFICATION (Automated, 1 hour after deploy)
   [ ] Shadow comparison shows 0% structural divergence
   [ ] Shadow comparison shows < 0.01% value divergence (for deterministic endpoints)
   [ ] No new error types in Go that don't exist in Python

3. FEATURE PARITY CHECKLIST (Manual, before marking CERTIFIED)
   [ ] Feature parity tracker updated (Section 2.1)
   [ ] V&V matrix row marked VERIFIED
   [ ] Golden file updated if behavior changed
   [ ] Production readiness checklist items still green
```

### 8.3 Breaking Change Communication Protocol

```
BREAKING CHANGE = Any change that would cause a consumer to fail if it does not update.

EXAMPLES:
  - Removing a JSON field from a response
  - Changing a field type (string -> number)
  - Changing an enum value (APPROVED -> approved)
  - Changing error response format
  - Changing HTTP status code for an error condition
  - Changing gRPC message structure

PROTOCOL:
  1. Announce in #elson-engineering Slack channel
  2. Create GitHub issue with `breaking-change` label
  3. Minimum 1-week notice before breaking change is deployed
  4. All affected teams must acknowledge in the issue
  5. Deploy with feature flag (old behavior = default, new = opt-in)
  6. After all consumers migrated, flip default
  7. After 2 weeks with no issues, remove old behavior

EXCEPTIONS:
  - Security vulnerabilities: 24-hour notice, break immediately if CRITICAL
  - Data corruption bugs: immediate break is acceptable to prevent further damage
```

### 8.4 Migration Milestone Gates

No Go service advances to the next phase without ALL items in the previous gate checked:

```
GATE 1: Development Complete
  [ ] All V&V tests written and passing
  [ ] Golden file tests passing
  [ ] Property-based tests passing
  [ ] Code review by someone who did NOT write the code
  [ ] go vet, golangci-lint, staticcheck all clean
  [ ] go test -race clean
  [ ] No TODO/FIXME/HACK in production code paths

GATE 2: Shadow Mode Ready
  [ ] Shadow proxy implemented and tested
  [ ] Comparison worker logging all divergences
  [ ] Grafana dashboard for shadow comparison operational
  [ ] Alert rules configured for divergence
  [ ] Rollback runbook documented and rehearsed

GATE 3: Canary Ready (1% traffic)
  [ ] 72 hours of shadow mode with < 0.01% divergence
  [ ] Load test completed at 2x expected peak
  [ ] Soak test completed (24 hours)
  [ ] Rollback tested from canary to 0%
  [ ] On-call engineer briefed on new service

GATE 4: Gradual Rollout (10% -> 50%)
  [ ] 1 week at 1% with 0 incidents
  [ ] Performance SLAs met at current traffic level
  [ ] No goroutine leaks (memory stable for 1 week)
  [ ] Circuit breaker compatibility verified

GATE 5: Full Migration (100% Go)
  [ ] 2 weeks at 50% with 0 incidents
  [ ] All performance SLAs met at full traffic
  [ ] Python service marked for archive (NOT delete)
  [ ] Python service revision preserved in Cloud Run for rollback
  [ ] Documentation updated to reflect Go as primary

GATE 6: Python Decommission (ARCHIVE ONLY)
  [ ] 30 days at 100% Go with 0 incidents
  [ ] Python service stopped (0 instances) but NOT deleted
  [ ] Python code moved to /backend/archive/python/ (NOT deleted)
  [ ] Decision log entry: ADR for Python decommission
```

---

## Appendix A: Golden File Catalog

Files to be created and maintained in `/backend/contracts/golden/`:

```
market-gateway/
  equity_quote_AAPL.golden.json
  equity_quote_MSFT.golden.json
  crypto_quote_BTCUSD.golden.json
  batch_quotes_10.golden.json
  history_daily_1y.golden.json
  history_intraday_5m.golden.json
  websocket_subscribe.golden.json
  websocket_quote_update.golden.json
  error_invalid_symbol.golden.json
  error_provider_down.golden.json

risk-engine/
  portfolio_risk_3_holdings.golden.json
  portfolio_risk_10_holdings.golden.json
  portfolio_risk_empty.golden.json
  portfolio_risk_single.golden.json
  portfolio_risk_penny_stock.golden.json
  trade_assessment_approved.golden.json
  trade_assessment_warning.golden.json
  trade_assessment_rejected.golden.json
  trade_assessment_requires_confirm.golden.json
  circuit_breaker_all_closed.golden.json
  circuit_breaker_system_open.golden.json
  circuit_breaker_volatility_restricted.golden.json
  symbol_risk_high_vol.golden.json
  symbol_risk_low_vol.golden.json
  error_invalid_portfolio.golden.json

order-router/
  market_buy_paper.golden.json
  market_sell_paper.golden.json
  limit_buy.golden.json
  limit_sell.golden.json
  stop_loss.golden.json
  stop_limit.golden.json
  partial_fill_sequence.golden.json
  cancel_order.golden.json
  order_status_pending.golden.json
  order_status_filled.golden.json
  error_insufficient_funds.golden.json
  error_invalid_symbol.golden.json
  error_rate_limited.golden.json
  error_trading_halted.golden.json
```

---

## Appendix B: Financial Precision Specification

### B.1 Mandatory Type Mappings

| Domain | Python Type | Go Type | Serialization |
|--------|-----------|---------|---------------|
| Dollar amounts (prices, costs, P&L) | `decimal.Decimal` | `shopspring/decimal.Decimal` | JSON string: `"150.25"` |
| Share quantities (fractional) | `decimal.Decimal` | `shopspring/decimal.Decimal` | JSON string: `"10.5"` |
| Percentages (returns, weights) | `float` | `float64` | JSON number: `0.0534` |
| Statistical measures (VaR, Beta) | `float` | `float64` | JSON number: `0.0534` |
| Integer counts (volume, trade count) | `int` | `int64` | JSON number: `1234567` |

### B.2 Rounding Rules

| Context | Rounding Mode | Precision |
|---------|--------------|-----------|
| USD amounts | ROUND_HALF_UP | 2 decimal places |
| Share quantities | ROUND_DOWN | 6 decimal places (Alpaca supports fractional) |
| Crypto quantities | ROUND_DOWN | 8 decimal places |
| Percentages for display | ROUND_HALF_UP | 4 decimal places |
| Internal calculations | No rounding until final output | Full precision |

### B.3 Known Float64 Danger Zones

```
DANGER: float64 cannot represent $0.10 exactly
  0.1 + 0.1 + 0.1 = 0.30000000000000004 (NOT 0.3)

MITIGATION: All dollar amounts use shopspring/decimal in Go
  d1, _ := decimal.NewFromString("0.1")
  d2, _ := decimal.NewFromString("0.1")
  d3, _ := decimal.NewFromString("0.1")
  sum := d1.Add(d2).Add(d3)  // Exactly 0.3

EXCEPTION: Statistical calculations (VaR, Beta, Sharpe) may use float64
  because the tolerance is 0.01% and float64 precision is ~15 significant digits.

HARD RULE: Any Go code path that:
  1. Reads a price from the database
  2. Calculates an order amount
  3. Writes a dollar amount to the database
  4. Sends a dollar amount to Alpaca API
  MUST use shopspring/decimal. float64 is FORBIDDEN in these paths.
```

---

## Appendix C: File Reference Map (Python Source -> Go Target)

| Python File | Key Functions | Go Target File | Go Functions | V&V IDs |
|-------------|--------------|----------------|--------------|---------|
| `services/market_data.py` | `MarketDataService.get_quote()` | `market-gateway/internal/provider/provider.go` | `Provider.GetQuote()` | MDG-001 to MDG-004 |
| `services/market_data.py` | `MarketDataService.get_historical_data()` | `market-gateway/internal/provider/provider.go` | `Provider.GetHistory()` | MDG-005 to MDG-007 |
| `services/market_data.py` | `is_trading_day()`, NYSE calendar | `market-gateway/internal/calendar/calendar.go` | `IsTradingDay()` | MDG-021 to MDG-023 |
| `services/market_data_streaming_enhanced.py` | WebSocket streaming | `market-gateway/internal/streaming/websocket.go` | `StreamingHub.Broadcast()` | MDG-008 to MDG-011 |
| `services/risk_management.py` | `RiskManagementService.calculate_portfolio_risk()` | `risk-engine/internal/risk/portfolio.go` | `RiskCalculator.CalculatePortfolioRisk()` | RE-001 to RE-016 |
| `services/risk_management.py` | `RiskManagementService.assess_trade()` | `risk-engine/internal/risk/assessment.go` | `AssessTrade()` | RE-017 to RE-020 |
| `trading_engine/engine/circuit_breaker.py` | `CircuitBreaker` class | `risk-engine/internal/breaker/circuit_breaker.go` | `CircuitBreaker` struct | RE-021 to RE-025 |
| `trading_engine/engine/trade_executor.py` | `TradeExecutor.execute_strategy_signal()` | `order-router/internal/execution/executor.go` | `Executor.SubmitOrder()` | OR-001 to OR-005 |
| `services/broker/alpaca.py` | `AlpacaBroker.place_order()` | `order-router/internal/broker/alpaca.go` | `AlpacaClient.SubmitOrder()` | OR-016 to OR-018 |
| `services/broker/alpaca.py` | `_normalize_crypto_symbol()` | `order-router/internal/broker/alpaca.go` | `normalizeCryptoSymbol()` | OR-032 |
| `trading_engine/strategies/execution/twap_strategy.py` | TWAP logic | `order-router/internal/execution/twap.go` | `TWAPExecutor` | OR-009 |
| `trading_engine/strategies/execution/vwap_strategy.py` | VWAP logic | `order-router/internal/execution/vwap.go` | `VWAPExecutor` | OR-010 |
| `trading_engine/strategies/execution/iceberg_strategy.py` | Iceberg logic | `order-router/internal/execution/iceberg.go` | `IcebergExecutor` | OR-011 |

---

*End of Compliance Framework Document*

**Next Steps:**
1. Review and approve this framework
2. Create the `/backend/contracts/` directory structure
3. Begin golden file capture from Python production
4. Establish shared risk_parameters.yaml as single source of truth
5. Set up CI pipeline for differential testing
6. Create Grafana dashboards for shadow mode comparison

**Certification:** This document must be approved by:
- [ ] Fintech Integrity Auditor (author)
- [ ] Apex Quant Architect (mathematical correctness)
- [ ] Reliability Security Sentinel (security posture)
- [ ] The Architect (API contracts and schema design)
