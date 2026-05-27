# Pre-Implementation Baseline Audit: 24-Week Autonomous Bot Sprint

**Date:** 2026-02-26
**Auditor:** Fintech Integrity Auditor (Apex)
**Purpose:** Establish compliance baseline before any code modifications begin.
**Scope:** Pre-Sprint + Milestone 1 files

---

## 1. Files To Be Modified — Current State

### 1.1 `backend/app/trading_engine/engine/circuit_breaker.py`

| Metric | Value |
|--------|-------|
| Lines | 711 |
| Test File | NONE (AT RISK) |
| Type Hints | Good — all method signatures typed |
| Imports | `random`, `json`, `os`, `threading`, `yaml`, `logging` |

**Code Quality Issues:**
- CRITICAL: `datetime.now()` used without timezone at lines 337, 346, 489 (naive datetimes)
- CRITICAL: State persisted to local JSON file (`circuit_breaker_status.json`) — ephemeral on Cloud Run containers
- HIGH: `_check_single_breaker` line 479 uses `random.random()` for half-open trade admission — non-deterministic, untestable
- HIGH: `check()` returns `Tuple[bool, CircuitBreakerStatus]` but callers sometimes treat as bare bool
- MEDIUM: `_load_config` silently falls back to empty config `{}` on error (line 172), then `_load_status` may fail silently too
- MEDIUM: Singleton via module-level global `_circuit_breaker_instance` — no thread-safety on initialization

**Thread Safety:** Uses `threading.RLock()` for all state mutations. Adequate for single-process. Not safe across Cloud Run instances (no distributed locking).

### 1.2 `backend/app/services/auto_trading_service.py`

| Metric | Value |
|--------|-------|
| Lines | 1211 |
| Test File | `tests/test_auto_trading.py` (184 lines — minimal) |
| Type Hints | Good — all method signatures typed |
| Imports | `asyncio`, `json`, `structlog`, `datetime`, `sqlalchemy` |

**Code Quality Issues:**
- CRITICAL: Class-level mutable dicts (`_running_tasks`, `_active_strategies`, etc.) shared across all instances. In a multi-worker deployment, these are per-process singletons — no cross-instance coordination.
- CRITICAL: `_auto_trading_loop` line 333: `if not circuit_breaker.check():` — `check()` returns a tuple which is ALWAYS truthy. The circuit breaker gate NEVER fires. (Previously flagged 2026-02-23, NOT YET FIXED)
- HIGH: `_session_factory` is a class-level `Optional[Callable]` set by the first user to start trading. If two users start concurrently, one overwrites the other's factory.
- HIGH: `_active_strategy_names` accessed via `hasattr(cls, "_active_strategy_names")` at line 263 and 403 — suggests it may not always be initialized.
- MEDIUM: `strategy.update_performance({"pnl": 0.0})` at line 665 always logs 0.0 P&L — placeholder, not real tracking.
- MEDIUM: Outcome backfill marks rows as `outcome_filled_at` when only `price_at_1h` is available (line 1049). 4h and 1d may never be filled if the bot stops.
- LOW: Gate numbering gap: 1,2,3,4,5,7,8,9,10 (gate 6 missing; gate 7 used for both AI hold and AI below-threshold).

**Thread Safety:** asyncio-based (single event loop). Class-level state dicts are NOT asyncio-safe if modified concurrently by multiple coroutines (e.g., two users calling start/stop simultaneously).

### 1.3 `backend/app/services/broker/alpaca.py`

| Metric | Value |
|--------|-------|
| Lines | 971 |
| Test Files | `test_alpaca_broker_comprehensive.py` (903 lines), `test_alpaca_integration.py` (594 lines) |
| Type Hints | Good — all method signatures typed |
| Imports | `logging`, `datetime`, `Decimal`, `typing`, `settings`, `BrokerError` |

**Code Quality Issues:**
- MEDIUM: `get_account_info` returns `float(response.get("equity", 0))` — loses precision. Financial data should use `Decimal`.
- MEDIUM: `get_positions` returns `float(position.get("qty", 0))` — same float precision issue.
- MEDIUM: `reconcile_holdings_from_alpaca` line 922 does `db_session.commit()` — caller has no control over transaction boundaries. If this is called within a larger transaction, it commits prematurely.
- LOW: `get_market_hours` imports `datetime` and `pytz` inside the method body (lines 466-467) — already imported at module level.
- LOW: `list_tradable_assets` default `limit=50000` but docstring says "default 2000" (line 934).

**Thread Safety:** Stateless per-request (good). `_api_request` inherited from `ApiBaseBroker` — uses `requests.Session` which is NOT thread-safe. Acceptable since each TradeExecutor creates its own broker instance.

### 1.4 `backend/app/main.py`

| Metric | Value |
|--------|-------|
| Lines | 249 |
| Test File | NONE (AT RISK) |
| Type Hints | Minimal (FastAPI handles via annotations) |

**Code Quality Issues:**
- MEDIUM: `_restore_trading_sessions` runs as a fire-and-forget `asyncio.create_task` (line 98). If it fails, the failure is logged but there's no retry mechanism. Active sessions will silently NOT restore.
- MEDIUM: Session restoration opens a DB session without the retry loop that `base.py` implements for initial connection. Cloud SQL Proxy startup race still possible.
- LOW: `import app.trading_engine.strategies  # noqa: F401` side-effect import — correct but fragile. If any strategy file has a top-level error, the entire app fails to start.

**Thread Safety:** Single async event loop, adequate.

### 1.5 `backend/app/api/api_v1/endpoints/auto_trading.py`

| Metric | Value |
|--------|-------|
| Lines | 640 |
| Test File | Covered by `test_auto_trading.py` (184 lines — minimal) |
| Type Hints | Good — Pydantic models for all request/response schemas |

**Code Quality Issues:**
- MEDIUM: `start_auto_trading` opens a manual `SessionLocal()` (line 123) outside FastAPI DI. This is intentional (portfolio check) but the session is not wrapped in a try/except for DB errors — only a finally for close.
- LOW: `export_fine_tuning_data` creates a generator function but DB session from FastAPI DI may close before the streaming response completes. Should use a dedicated session.
- LOW: `_pct` helper (line 593) does not guard against p0==0 properly — `if p0 and p1` would pass for p0=0.001.

---

## 2. New Files To Be Created (Confirmed Non-Existent)

| Planned File | Status | Purpose |
|-------------|--------|---------|
| `backend/app/models/trading_session_metrics.py` | DOES NOT EXIST | Per-session performance metrics (Sharpe, drawdown, P&L) |
| `backend/app/models/trading_risk_event.py` | DOES NOT EXIST | Risk event log (breaker trips, limit violations) |
| `backend/app/models/trading_audit_log.py` | DOES NOT EXIST | Immutable audit trail (all state changes) |
| `backend/app/models/tax_lot.py` | DOES NOT EXIST | FIFO/LIFO cost basis for tax reporting |

**NOTE:** Each of these will require:
1. A new Alembic migration file
2. Registration in `backend/app/models/__init__.py`
3. Import in `backend/app/db/base.py` (if `create_all()` is used)
4. Schema drift check before production deployment (per MEMORY.md rules)

---

## 3. Model Schema Baseline

### 3.1 All Model Files (21 files, 2984 total lines)

| File | Lines | Key Tables/Classes |
|------|-------|--------------------|
| `__init__.py` | 141 | Re-exports all models |
| `account.py` | 118 | Account (broker accounts) |
| `ai_interactions.py` | 65 | AIInteraction |
| `auto_trading_session.py` | 25 | AutoTradingSession |
| `beneficiary.py` | 20 | Beneficiary |
| `education.py` | 311 | EducationModule, UserProgress, QuizQuestion, etc. |
| `family.py` | 370 | FamilyGroup, FamilyMember, CustodialAccount, etc. |
| `holding.py` | 110 | Holding (DB model) + Position (lightweight class) |
| `linked_account.py` | 21 | LinkedAccount |
| `market_data.py` | 145 | MarketDataPoint, Asset, Watchlist |
| `notification.py` | 64 | Notification |
| `portfolio.py` | 370 | Portfolio, PortfolioHistory, PerformanceMetrics |
| `risk.py` | 13 | (Minimal — imports only) |
| `security.py` | 256 | DeviceFingerprint, LoginSession, WebAuthnCredential, etc. |
| `sentinel_triggers.py` | 104 | SentinelTrigger |
| `subscription.py` | 175 | SubscriptionPlan, UserSubscription, Payment |
| `trade.py` | 229 | Trade, RoundupTransaction, TradeExecution |
| `trade_decision_log.py` | 56 | TradeDecisionLog |
| `trusted_contact.py` | 39 | TrustedContact |
| `user.py` | 282 | User |
| `user_settings.py` | 70 | UserSettings |

### 3.2 TradeDecisionLog Columns (Current)

```
id                  Integer PK
user_id             Integer FK(users.id) indexed
portfolio_id        Integer FK(portfolios.id)
symbol              String(20) indexed
decided_at          DateTime(tz) server_default=now() indexed
strategy_name       String(100)
mode                String(20)  -- 'paper' | 'live'
market_context      JSON
model_prompt        Text
model_raw_response  Text
action              String(10) NOT NULL  -- BUY | SELL | HOLD
confidence          Numeric(5,4)
reasoning           Text
risk_factors        Text  -- JSON string
signal_source       String(20) NOT NULL  -- 'ai' | 'rule_based'
trade_id            String(36) FK(trades.id) nullable
price_at_decision   Numeric(18,8)
price_at_1h         Numeric(18,8)
price_at_4h         Numeric(18,8)
price_at_1d         Numeric(18,8)
outcome_filled_at   DateTime(tz)
```

**Planned additions (not yet implemented):**
- `position_size_pct` — AI-recommended position sizing
- `portfolio_value_at_decision` — for normalized P&L calculation
- `slippage_bps` — execution quality tracking

### 3.3 Holding Model (Current)

```
id                              Integer PK
symbol                          String(20) indexed
asset_type                      String(50) NOT NULL  -- "stock", "crypto", "bond", "etf"
quantity                        Numeric(18,8) NOT NULL
average_cost                    Numeric(18,8) NOT NULL
current_price                   Numeric(18,8) NOT NULL
market_value                    Numeric(18,8) NOT NULL
unrealized_gain_loss            Numeric(18,8) default=0
unrealized_gain_loss_percentage Numeric(18,8) default=0
target_allocation_percentage    Numeric(18,8) nullable
current_allocation_percentage   Numeric(18,8) nullable
sector                          String(100) nullable default="Unknown"
portfolio_id                    Integer FK(portfolios.id) NOT NULL
created_at                      DateTime(tz) server_default=now()
updated_at                      DateTime(tz) onupdate=now()
```

**Note:** `asset_type` is `String(50)` not an Enum. Currently only "stock" is used by AlpacaBroker. Options/crypto implementation will need this field expanded or an Enum migration.

**Note:** Numeric precision is `(18,8)` — adequate for stock prices. Crypto (BTC fractions to 8 decimal places) is covered. Options Greeks may need higher precision.

### 3.4 Position Class (Non-DB)

The `Position` class in `holding.py` lines 47-110 uses `float` for `quantity` and `cost_basis` — NOT `Decimal`. This is used by `TradeExecutor` for in-memory position tracking. Financial precision risk during high-frequency execution.

---

## 4. Alembic Migration Chain

### HEAD: `add_bot_sessions_20260224`

Full chain (newest to oldest):

```
add_bot_sessions_20260224
  |
merge_heads_2026_02_23
  |-- add_trade_decision_log_2026_02
  |     |
  |     add_performance_indexes_2026_02 (*)
  |
  |-- add_address_columns_2026_02
        |
        add_ssn_columns_2025_02
          |
          c1b26df926d8 (portfolio/trade enhancements)
            |
            fe05daf7e673 (education tables)
              |
              add_webauthn_2025_12_06
                |
                efe8d9e3ce31 (security tables)
                  |
                  sync_schema_2025_07_14 (manual sync)
                    |
                    0c1cc482b9b3 (subscription payments)
                      |
                      7a32be28d1fe (subscription billing)
                        |
                        1167a82d321b (INITIAL)

(*) add_performance_indexes_2026_02 has TWO parents due to merge:
    - via merge f18101facea7 with a1b2c3d4e5f6 (sentinel tables)
    - a1b2c3d4e5f6 revises add_ssn_columns_2025_02
```

### Migration Count: 16 files total

### Merge Points:
1. `f18101facea7` merges `a1b2c3d4e5f6` + `add_performance_indexes_2026_02`
2. `merge_heads_2026_02_23` merges `add_address_columns_2026_02` + `add_trade_decision_log_2026_02`

**WARNING:** The chain has TWO merge migrations already. Adding 4 new model files will likely require a 3rd merge if any branch from existing chain. Recommend creating all new migrations as a linear chain off the current HEAD.

---

## 5. Feature Engineering Baseline

### File: `backend/app/trading_engine/data/feature_engineering.py` (561 lines)

### Class: `FeatureEngineering` — 61 indicators across 10 categories

| Category | Method | Indicators Generated |
|----------|--------|---------------------|
| Moving Averages | `add_moving_averages()` | SMA(5,10,20,50,200), EMA(5,10,20,50,200), MA_strength(5,10,20,50,200) = **15 features** |
| Bollinger Bands | `add_bollinger_bands()` | bb_middle, bb_std, bb_upper, bb_lower, bb_width, bb_pct = **6 features** |
| RSI | `add_rsi()` | rsi, rsi_overbought, rsi_oversold = **3 features** |
| MACD | `add_macd()` | macd, macd_signal, macd_hist, macd_cross_up, macd_cross_down = **5 features** |
| Stochastic | `add_stochastic_oscillator()` | stoch_k, stoch_d, stoch_cross_up, stoch_cross_down, stoch_overbought, stoch_oversold = **6 features** |
| ATR | `add_atr()` | atr, atr_pct = **2 features** |
| OBV | `add_obv()` | obv, obv_momentum = **2 features** |
| Momentum | `add_momentum_indicators()` | price_roc_5, price_roc_10, price_roc_20, mfi = **4 features** |
| Volatility | `add_volatility_indicators()` | returns, volatility_10, volatility_20, gk_volatility = **4 features** |
| Candlestick | `add_candlestick_patterns()` | doji, hammer, shooting_star, bullish_engulfing, bearish_engulfing = **5 features** |
| Returns | `add_returns()` | ret_1d, ret_3d, ret_5d, ret_10d, ret_20d, ret_60d, direction_1d, direction_5d, direction_20d = **9 features** |

**Total: 61 features**

### Other Classes in Same File:
- `SentimentFeatures` — Simulated sentiment (NOT real NLP). Uses `np.random.normal()`. **PLACEHOLDER ONLY.**
- `DataCombiner` — Merges market data with sentiment/economic data. Uses deprecated `fillna(method="ffill")` at line 512.
- `prepare_ml_features()` — Train/test split utility function.

### DUPLICATION WARNING (Previously Flagged):
1. `services/market_data_processor.py` duplicates SMA/EMA/MACD/RSI/BB
2. `strategies/moving_average.py` duplicates inline SMA/RSI/MACD/volume
3. `auto_trading_service.py:690-700` has its own `_calculate_rsi()` implementation

**ANY new DRL feature pipeline MUST import from `feature_engineering.py`, not create a 5th implementation.**

---

## 6. Strategy Registry Baseline

### Registry: `backend/app/trading_engine/strategies/registry.py` (217 lines)

### Categories (11 defined):
`TECHNICAL`, `MOMENTUM`, `MEAN_REVERSION`, `ARBITRAGE`, `BREAKOUT`, `ML`, `SENTIMENT`, `PORTFOLIO`, `EXECUTION`, `GRID`, `OPTIONS`

**Note:** `ML`, `SENTIMENT`, `PORTFOLIO`, and `OPTIONS` categories are defined but have ZERO registered strategies. These are the DRL integration points.

### Registered Strategies (20 total):

| # | Name | Category | File | Lines |
|---|------|----------|------|-------|
| 1 | `rsi_strategy` | TECHNICAL | `technical/rsi_strategy.py` | 12,335 |
| 2 | `bollinger_bands` | TECHNICAL | `technical/bollinger_bands.py` | 14,904 |
| 3 | `macd_strategy` | TECHNICAL | `technical/macd_strategy.py` | 13,358 |
| 4 | `ichimoku_cloud` | TECHNICAL | `technical/ichimoku.py` | 17,191 |
| 5 | `adx_trend` | TECHNICAL | `technical/adx_trend.py` | 15,041 |
| 6 | `stochastic` | TECHNICAL | `technical/stochastic.py` | 9,265 |
| 7 | `candlestick_patterns` | TECHNICAL | `technical/candlestick_patterns.py` | 21,541 |
| 8 | `support_resistance` | BREAKOUT | `breakout/support_resistance.py` | 14,319 |
| 9 | `opening_range` | BREAKOUT | `breakout/opening_range.py` | 13,914 |
| 10 | `donchian_breakout` | BREAKOUT | `breakout/donchian_breakout.py` | 15,484 |
| 11 | `statistical_mean_reversion` | MEAN_REVERSION | `mean_reversion/statistical_reversion.py` | 12,712 |
| 12 | `rsi_mean_reversion` | MEAN_REVERSION | `mean_reversion/rsi_reversion.py` | 10,810 |
| 13 | `momentum_factor` | MOMENTUM | `momentum/momentum_factor.py` | 12,256 |
| 14 | `trend_following` | MOMENTUM | `momentum/trend_following.py` | 13,758 |
| 15 | `pairs_trading` | ARBITRAGE | `arbitrage/pairs_trading.py` | 15,181 |
| 16 | `grid_trading` | GRID | `grid/grid_trading.py` | 12,025 |
| 17 | `dca_strategy` | GRID | `grid/dca_strategy.py` | 12,397 |
| 18 | `vwap_execution` | EXECUTION | `execution/vwap_strategy.py` | 18,328 |
| 19 | `twap_execution` | EXECUTION | `execution/twap_strategy.py` | 18,165 |
| 20 | `iceberg_execution` | EXECUTION | `execution/iceberg_strategy.py` | 13,700 |

**Plus 1 non-registered strategy:**
- `MovingAverageStrategy` in `strategies/moving_average.py` (15,654 lines) — NOT registered in `StrategyRegistry`. Used as a standalone legacy strategy.

### Base Class Contract:
```python
class TradingStrategy(ABC):
    @abstractmethod
    async def generate_signal(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Returns {'action': 'buy'|'sell'|'hold', 'confidence': float, 'price': float, ...}"""

    @abstractmethod
    async def update_parameters(self, new_parameters: Dict[str, Any]) -> bool: ...
```

### DRL Integration Point:
- Register under `StrategyCategory.ML`
- Must implement `generate_signal()` returning the standard signal dict
- DRL models output continuous weights `[-1, 1]` — requires an adapter to map to `{'action': ..., 'confidence': ..., 'price': ...}`
- `auto_trading_service.py:518-523` expects `signal.get("action") in {"buy","sell"}`

### Risk Profile Mapping (in auto_trading.py):
```python
STRATEGY_PROFILES = {
    "conservative": ["rsi_strategy", "bollinger_bands"],
    "balanced": ["macd_strategy", "rsi_strategy", "bollinger_bands"],
    "aggressive": ["momentum_factor", "trend_following", "macd_strategy"],
}
```

---

## 7. Summary Risk Matrix

| Finding | Severity | File | Line(s) | Fix Required Before Sprint |
|---------|----------|------|---------|---------------------------|
| Circuit breaker gate never fires (tuple truthiness) | CRITICAL | auto_trading_service.py | 333 | YES |
| Circuit breaker state in ephemeral JSON file | CRITICAL | circuit_breaker.py | 160, 184-190 | YES (migrate to DB) |
| Class-level mutable dicts (race condition) | CRITICAL | auto_trading_service.py | 38-55 | YES |
| Naive `datetime.now()` (no UTC) | CRITICAL | circuit_breaker.py | 337, 346, 489 | YES |
| DRL signal contract mismatch | CRITICAL | (planned) | N/A | Before DRL integration |
| Session factory overwrite on concurrent start | HIGH | auto_trading_service.py | 103 | Before multi-user |
| `random.random()` in half-open breaker | HIGH | circuit_breaker.py | 479 | Before production |
| Feature engineering 4x duplication | HIGH | multiple | multiple | Before DRL features |
| Zero test coverage for circuit_breaker | HIGH | circuit_breaker.py | all | Before modifications |
| Zero test coverage for feature_engineering | HIGH | feature_engineering.py | all | Before DRL features |
| `float()` for financial data in broker | MEDIUM | alpaca.py | 288-296, 305-320 | P2 |
| Position class uses `float` not `Decimal` | MEDIUM | holding.py | 55-56 | Before live trading |
| Outcome backfill marks complete at 1h only | MEDIUM | auto_trading_service.py | 1049 | P2 |
| Deprecated `fillna(method="ffill")` | LOW | feature_engineering.py | 512 | P3 |
| Docstring/code limit mismatch | LOW | alpaca.py | 934 | P4 |
