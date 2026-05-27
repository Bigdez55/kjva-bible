# Alpha Pulse Signal Architecture Audit Report

**Plan Under Review:** `/Users/desmondearly/.claude/plans/memoized-frolicking-tower.md`
**Audit Date:** 2026-02-26
**Auditor:** Alpha Pulse Engine
**Active DoRA Domain:** Signal Architecture Validation

---

## EXECUTIVE SUMMARY

The plan describes a multi-milestone autonomous trading bot extending Elson TB2 with DRL intelligence, crypto support, and options trading. The signal architecture has **strong foundational design decisions** (ONNX inference, IQL offline RL, beta-hedged reward, separate crypto policies) but contains **4 critical signal path gaps** and **3 architectural ambiguities** that, if left unresolved, will produce signals that violate the Signal Gate protocol. The most dangerous deficiency is the **absence of any real-time per-trade signal gate** between DRL weight output and order execution.

---

## ITEM 1: SIGNAL FLOW PIPELINE

**Verdict: CONDITIONAL PASS -- requires 3 clarifications**

### What the plan describes:
```
elson-finance-14b (EFT) --> sentiment + strategy brief
                                    |
                              Feature Engineering (46-dim equity / 56-dim crypto)
                                    |
                              DRL Agent (IQL via d3rlpy) --> continuous weights [-1,1]
                                    |
                              Execution (TradeExecutor via Alpaca)
```

### What the code actually implements today:
```
per-symbol loop (60s interval)
  --> _generate_ai_trading_signal()
      --> eft_generate("trading_signals", prompt_with_OHLCV_context)
      --> parse JSON: {signal, confidence, reasoning, risk_factors}
      --> if action in {buy,sell} AND confidence >= 0.6: accept
      --> else: fall through to rule-based (MovingAverageStrategy)
  --> validate_signal() (min_confidence check, field presence)
  --> TradeExecutor.execute_strategy_signal()
```

### Signal Path Concerns:

**1a. The DRL agent does NOT exist yet.** The current pipeline is LLM-direct-to-execution with rule-based fallback. The plan's DRL layer (Milestone 3) is entirely new infrastructure. This is correctly sequenced -- M2 builds features, M3 builds DRL -- but the plan does not specify **how the DRL agent's continuous [-1,1] output integrates with the existing `_process_strategy` loop**. The current loop calls `strategy.generate_signal(market_data)` which returns `{action, confidence, price}`. The DRL agent returns continuous portfolio weights. These are fundamentally different interfaces.

**ACTION REQUIRED:** Define how `DRLStrategy.generate_signal()` maps continuous weights to discrete `{buy, sell, hold}` signals compatible with the existing `_process_strategy()` and `TradeExecutor` interface. Options:
  - Threshold-based: weight > +0.3 = buy, weight < -0.3 = sell, else hold
  - Target-position-based: compare DRL target weight to current portfolio weight, emit rebalance trades
  - The latter is correct for a portfolio optimization DRL but requires executor changes

**1b. Feature engineering happens WHERE?** The plan says `feature_engineering_service.py` produces a 46/56-dim vector. But the DRL environment (`trading_env.py`) defines `obs=46/56 dims`. So feature engineering feeds the environment, which feeds the agent. But the plan does not specify whether feature engineering runs at inference time (every 60s loop) or only during training. If only during training, the inference path needs a separate feature pipeline -- this is a common train/serve skew bug.

**1c. LLM sentiment is a FEATURE, not a separate signal path.** The plan correctly identifies 4 sentiment dims + 8 LLM signal dims in the feature vector. But the current code uses the LLM as a **direct signal generator** (BUY/SELL/HOLD), not as a feature extractor. The transition from "LLM generates trading signals directly" to "LLM generates features that feed DRL" is architecturally discontinuous. The plan should explicitly describe the deprecation path for the current LLM-direct signal mode.

---

## ITEM 2: SENTIMENT RESIDUAL ORTHOGONALIZATION

**Verdict: MARGINAL PASS -- needs augmentation**

### What the plan says:
> "Sentiment residual orthogonalized against recent return"

This is a reference to removing the price-return confound from LLM-generated sentiment. The intuition is correct: if you ask an LLM "what is the sentiment for AAPL?" and AAPL is up 5% today, the LLM will reflect that return in its sentiment score (because the model has seen price data in context). This creates spurious correlation between the sentiment feature and the target variable.

### Analysis:

**What this means mathematically:**
```
sentiment_raw = f(LLM, prompt_with_price_context)
sentiment_residual = sentiment_raw - beta * recent_return
```

Where `beta` is the OLS coefficient of `sentiment_raw` regressed on `recent_return`.

### Concerns:

**2a. Simple linear deconfounding is insufficient for a 14B parameter model.** The confound between LLM sentiment and price is NOT linear. The LLM's internal representation of "bullish" vs "bearish" is shaped by:
  - Price level relative to moving averages (already in the prompt: SMA20/SMA50)
  - RSI (already in the prompt)
  - Magnitude of recent move (change_pct, five_d_change -- both in the prompt)

A single `beta * recent_return` subtraction removes only the first-order linear confound. Higher-order and interaction confounds remain. The LLM literally receives the price data in its prompt (see `_generate_ai_trading_signal` lines 866-873), so the confounding is structural, not incidental.

**RECOMMENDED AUGMENTATION:**
  - **Option A (strong):** Run the LLM twice -- once with price context, once with price-stripped context (only qualitative news/fundamentals). The difference is the price-confounded component; the price-stripped response is the true sentiment signal. Cost: 2x LLM inference per symbol.
  - **Option B (moderate):** Use a nonlinear residualization: train a small MLP that predicts `sentiment_raw` from `[return_1d, return_5d, RSI, SMA20_pct, SMA50_pct]`, then use the residual. Requires a calibration dataset.
  - **Option C (lightweight, acceptable for v1):** Remove all quantitative data from the sentiment prompt. Feed the LLM only the symbol name, recent news headlines, and sector context. This eliminates the confound at the input level rather than trying to remove it post-hoc.

**2b. The 8-dim LLM signal in the feature vector is never specified.** The plan says "8 LLM signal" dimensions but never defines what they are. Are they: [sentiment_score, confidence, bullish_probability, bearish_probability, volatility_expectation, momentum_expectation, sector_view, macro_view]? Without this definition, the feature engineering service cannot be implemented.

---

## ITEM 3: EFT AGENT TEMPERATURES

**Verdict: PASS with minor note**

### Proposed configs:
| Agent | Temperature | Purpose |
|-------|-------------|---------|
| TRADING_BOT_STRATEGIST | 0.3 | Daily brief, includes crypto allocation % |
| SENTIMENT_ANALYZER | 0.2 | Per-symbol sentiment scoring |
| CRYPTO_MARKET_ANALYST | 0.2 | BTC trend, altseason, regulatory risk |

### Analysis:

These temperatures are **appropriate and well-calibrated** for their use cases:

- **TRADING_BOT_STRATEGIST at 0.3:** Correct. A daily brief requires some narrative flexibility (not fully deterministic) but must be grounded. The existing `trading_signals` agent uses 0.4, and the strategist brief is less latency-sensitive, so 0.3 is fine. The slightly higher temperature than SENTIMENT_ANALYZER accounts for the need to synthesize across asset classes.

- **SENTIMENT_ANALYZER at 0.2:** Correct. Sentiment scoring should be near-deterministic. You want the model to commit to a direction rather than hedging with equivocal language. Low temperature reduces variance in the sentiment feature, which is critical because this output feeds the DRL feature vector -- high-variance features reduce the signal-to-noise ratio of the policy gradient.

- **CRYPTO_MARKET_ANALYST at 0.2:** Correct for the same reason as SENTIMENT_ANALYZER. Crypto regime classification (altseason vs BTC-dominant, regulatory risk level) should be categorical, not creative.

**Minor note:** The existing `trading_signals` agent (temp=0.4) generates JSON. If the new agents also return structured JSON (which they should for feature engineering), consider lowering `trading_signals` to 0.3 for consistency. Higher temperature increases JSON malformation probability -- this is the root cause of the P1 "trading_signals JSON parse" bug already documented in MEMORY.md.

---

## ITEM 4: SIGNAL GATING -- REAL-TIME PER-TRADE GATE

**Verdict: FAIL -- critical gap**

### What the plan describes:
> "Deflated Sharpe >0.5 at p<0.05" as a validation gate in `paper_validation_service.py` (Milestone 4)

This is a **batch validation gate** -- it evaluates the overall strategy after 30 days of paper trading. This is necessary but NOT sufficient.

### What is MISSING:

**There is NO real-time signal gate before each individual trade.**

The current flow is:
1. LLM or rule-based generates signal
2. `validate_signal()` checks field presence + minimum confidence (0.6)
3. Circuit breaker checks system-level trading permission
4. Trade executes

**What should exist (per Alpha Pulse Signal Gate protocol):**

A per-trade gate that fuses:
- **Momentum Vector** (quantitative): Does the signal have positive expected alpha relative to its risk? This requires computing the signal's expected Sharpe contribution to the portfolio, not just a confidence threshold.
- **Sentiment Vector** (narrative): Is the causal direction aligned with the momentum direction? Is the Pulse Intensity above threshold? Is the Decay Factor not expired?

The current system has **NO Sharpe-based gate on individual signals.** The confidence >= 0.6 threshold from the LLM is self-reported and uncalibrated -- an LLM saying "confidence: 0.85" has no statistical relationship to the actual probability of the trade being profitable.

### REQUIRED ADDITIONS:

**4a. Pre-trade Sharpe estimation.** Before executing any trade, compute:
```python
expected_return = signal_alpha_estimate  # from DRL weight or LLM confidence calibrated to historical hit rate
expected_risk = position_size * symbol_volatility_annualized
pre_trade_sharpe = expected_return / expected_risk
if pre_trade_sharpe < 1.5:
    reject_signal("Sharpe below gate threshold")
```

This requires maintaining a rolling calibration between LLM confidence scores and realized trade outcomes (the `TradeDecisionLog` + outcome backfill already provides this data).

**4b. Confidence calibration function.** The LLM's raw confidence is NOT calibrated. Build a monotonic calibration function `f(raw_confidence) -> calibrated_probability` using isotonic regression on the outcome backfill data. Gate on `calibrated_probability >= threshold`, not raw confidence.

**4c. Signal-to-noise filter.** Before executing, check: has this symbol's recent variance decomposition yielded a systematic R-squared >= 0.45? If the asset's price is in a noise-dominated regime, no LLM or DRL signal should be trusted. The plan's `model_drift_detector.py` (M4) detects drift after the fact, but there is no pre-trade regime filter.

---

## ITEM 5: NARRATIVE-TO-QUANTITATIVE BRIDGE

**Verdict: FAIL -- specification gap**

### What the plan says:
> TRADING_BOT_STRATEGIST produces a "daily brief" with "crypto allocation %"
> Feature vector includes "4 sentiment" + "8 LLM signal" dimensions

### What is NOT specified:

**How does a text-based daily brief become an 8-dimensional numeric vector?**

There are two viable approaches, and the plan does not choose one:

**Option A: Structured JSON extraction.**
The TRADING_BOT_STRATEGIST agent returns JSON with numeric fields:
```json
{
  "market_regime": "risk_on",          // -> one-hot encode to 4 dims
  "equity_allocation_target": 0.65,     // -> 1 dim
  "crypto_allocation_target": 0.10,     // -> 1 dim
  "expected_vol_regime": "normal",      // -> 1 dim ordinal encode
  "macro_sentiment": 0.72              // -> 1 dim
}
```
This is the correct approach. It keeps the bridge explicit and auditable.

**Option B: Embedding extraction.**
Pass the text brief through the LLM and extract an internal hidden state as a dense vector, then project to 8 dims via a learned linear layer. This is more information-rich but less interpretable and harder to debug.

**REQUIRED:** Choose Option A. It aligns with the rest of the architecture (all other LLM agents return JSON), it is auditable for compliance, and it avoids the train/serve skew problem of embedding extraction.

**Additionally:** The plan says "4 sentiment" dimensions (via SENTIMENT_ANALYZER) but does not define what they are. Proposed:
```
sentiment_dims = [
    sentiment_score,          # float [-1.0, 1.0]: bearish to bullish
    sentiment_confidence,     # float [0.0, 1.0]: model certainty
    news_event_intensity,     # float [0.0, 1.0]: magnitude of recent news
    sentiment_momentum,       # float [-1.0, 1.0]: change in sentiment from prior period
]
```

---

## ITEM 6: CRYPTO SIGNAL QUALITY -- DATA AVAILABILITY

**Verdict: CONDITIONAL PASS -- degradation plan is adequate, but latency is not addressed**

### What the plan claims:

| Data | Primary | Fallback | Real-time? |
|------|---------|----------|------------|
| On-chain metrics | Glassnode API | Coingecko API | NO |
| Funding rates | Coingecko | Bybit API | DELAYED |
| BTC dominance | Coingecko | CoinMarketCap | DELAYED |

### Reality check:

**6a. On-chain metrics (active addresses, tx volume, whale signal) are NOT real-time.**
- Glassnode free tier: 24-hour delay. Professional tier ($799/mo): still 1-hour delay for most metrics.
- Coingecko: No on-chain metrics at all (only price/volume/market cap). This fallback is misleading.
- **Actual latency:** 1-24 hours depending on tier and metric.

**Impact on signal quality:** On-chain metrics with 1-24h delay are suitable for daily regime detection (the TRADING_BOT_STRATEGIST daily brief) but NOT for the 60-second trading loop. Using stale on-chain data in a real-time feature vector introduces look-ahead contamination in the opposite direction -- you are using yesterday's signal for today's trade.

**RECOMMENDATION:** Use on-chain metrics ONLY in the daily brief / regime classification. Do NOT include them in the 56-dim real-time feature vector. Reduce crypto feature dims from 56 to 53 (drop 3 on-chain dims from real-time, keep in daily brief).

**6b. Funding rates from Coingecko are snapshots, not streams.**
- Coingecko provides 8-hour funding rate snapshots for perpetual contracts.
- Alpaca (the actual broker) does NOT offer funding rate data because Alpaca crypto is SPOT, not perpetual futures.
- **If you are trading spot crypto on Alpaca, funding rates are economically irrelevant** to your positions. Funding rates affect perpetual futures holders, not spot holders.

**RECOMMENDATION:** Remove funding rates from the feature vector entirely unless you add perpetual futures trading (which Alpaca does not support). Including economically irrelevant features is noise injection.

**6c. BTC dominance: 15-minute delay via Coingecko is acceptable** for regime classification (altseason detection operates on daily/weekly timeframes).

---

## ITEM 7: SIGNAL COMBINATION -- DRL + LLM + RULE-BASED

**Verdict: FAIL -- no meta-model, no combination specification**

### Current state:
The code uses a waterfall priority:
```
1. Try AI (LLM) signal
2. If AI confidence >= 0.6 and action in {buy, sell}: use AI signal
3. Else: fall through to rule-based (MovingAverageStrategy)
```
There is NO combination. It is a simple priority chain.

### What the plan proposes (Milestone 2-3):
- DRLStrategy registered in StrategyRegistry
- LLM agents generate features that feed DRL
- But the plan does NOT specify: **when DRL is active, what happens to the LLM-direct signal path?**

### The 3-source combination problem:

With the full plan implemented, you have 3 signal sources:
1. **DRL agent:** Continuous portfolio weights, trained offline via IQL
2. **LLM (EFT):** Direct BUY/SELL/HOLD signal with confidence
3. **Rule-based:** MovingAverageStrategy crossover signal

These produce signals of fundamentally different types:
- DRL: continuous [-1, 1] (portfolio weight target)
- LLM: categorical {BUY, SELL, HOLD} + float confidence
- Rule-based: categorical {buy, sell, hold} + float confidence

### REQUIRED SPECIFICATION:

**Option A: DRL replaces LLM-direct (RECOMMENDED).**
Once DRL is trained with LLM features in its observation space, the LLM sentiment becomes an INPUT to DRL, not a parallel signal. The LLM no longer generates trade signals directly -- it generates features. The waterfall becomes:
```
1. Feature engineering (includes LLM sentiment as 4+8 dims)
2. DRL agent generates target weights
3. Rule-based ONLY as an absolute fallback when DRL model cannot load
```
This is clean, avoids conflicting signals, and is the correct architecture.

**Option B: Meta-model ensemble (NOT recommended for v1).**
Train a meta-learner (logistic regression or small MLP) on all 3 signal sources. This requires a separate training dataset of signal-level features and outcomes, introduces another model to maintain, and complicates the already-complex pipeline.

**Option C: Weighted average (DANGEROUS).**
Simple alpha-weighted combination of the 3 sources. This is the naive approach and fails because the signals have different units and are not calibrated to the same scale.

---

## ADDITIONAL SIGNAL ARCHITECTURE CONCERNS

### A1. EMBARGO VALIDATION (PASS)
- **Equity: 252-day embargo.** Correct. Standard for momentum factor lookback avoidance.
- **Crypto: 60-day embargo.** Correct. Crypto regime changes are faster; a shorter embargo is appropriate.
- **IQL choice over CQL.** Correct. IQL avoids the need for behavior policy estimation, which is critical when your replay buffer is generated by a mix of AI + rule-based signals (heterogeneous behavior policy).

### A2. BETA-HEDGED REWARD (PASS)
> "Raw PnL: 60-80% market beta. Beta-hedged: 3-5x higher SNR"

This is correct and critical. The reward function should be:
```
reward = portfolio_return - beta * market_return
```
This forces the DRL to learn ALPHA, not market-direction bets. The claimed 3-5x SNR improvement is consistent with published literature (Lopez de Prado 2018).

### A3. CIRCUIT BREAKER PERSISTENCE (CONDITIONAL PASS)
The plan correctly identifies that `circuit_breaker_status.json` must migrate to DB. The existing code (`circuit_breaker.py` line 160-189) uses file I/O which will fail in Cloud Run (ephemeral filesystem). The plan's `bot_risk_event` table is the correct fix.

### A4. WALK-FORWARD + CPCV (PASS)
Using Combinatorial Purged Cross-Validation with 10 splits + Deflated Sharpe is best-practice for financial ML validation. This correctly controls for multiple testing bias.

### A5. OUTCOME BACKFILL TRAINING LOOP (PASS)
The existing `_fill_pending_outcomes()` at lines 992-1056 provides the mechanism to build a fine-tuning / DRL replay buffer dataset from live trading decisions. This is a strong design choice -- the system learns from its own trading decisions with delayed outcome labels.

---

## SUMMARY SCORECARD

| # | Item | Verdict | Severity |
|---|------|---------|----------|
| 1 | Signal Flow Pipeline | CONDITIONAL PASS | P1 -- DRL-to-strategy interface undefined |
| 2 | Sentiment Orthogonalization | MARGINAL PASS | P2 -- linear deconfound insufficient, but acceptable for v1 |
| 3 | EFT Agent Temperatures | PASS | -- |
| 4 | Real-Time Signal Gate | **FAIL** | **P0 -- no Sharpe gate, no calibrated confidence, no regime filter** |
| 5 | Narrative-to-Quantitative Bridge | **FAIL** | **P0 -- 8-dim LLM signal + 4-dim sentiment undefined** |
| 6 | Crypto Data Availability | CONDITIONAL PASS | P1 -- on-chain latency, funding rate irrelevance for spot |
| 7 | Signal Combination (meta-model) | **FAIL** | **P0 -- 3 signal sources with no combination specification** |
| A1 | Embargo Validation | PASS | -- |
| A2 | Beta-Hedged Reward | PASS | -- |
| A3 | Circuit Breaker Persistence | CONDITIONAL PASS | P1 -- correctly identified in plan |
| A4 | CPCV + Deflated Sharpe | PASS | -- |
| A5 | Outcome Backfill | PASS | -- |

### Gate Status: **HOLD**

**3 P0 items must be resolved** before this plan can proceed to implementation:
1. Define the real-time per-trade signal gate (Sharpe mandate, confidence calibration, regime filter)
2. Specify the 4+8 dimensional LLM feature extraction schema
3. Specify the signal combination architecture (recommend DRL-subsumes-LLM)

**3 P1 items should be resolved** before Milestone 2 begins:
1. Define DRLStrategy interface compatibility with `_process_strategy()` loop
2. Remove economically irrelevant features (funding rates for spot crypto)
3. Restrict on-chain metrics to daily-cadence regime signals, not 60s feature vector

---

## RECOMMENDED PLAN AMENDMENTS

### Amendment 1: Add to Milestone 2 -- Signal Gate Service
```
New file: backend/app/services/signal_gate_service.py
  - Pre-trade Sharpe estimation (rolling 30-day calibration)
  - Confidence calibration (isotonic regression on TradeDecisionLog outcomes)
  - Regime filter (systematic R-squared check per symbol)
  - Gate verdict: PASS / HOLD / REJECT with logged reasoning
```

### Amendment 2: Add to Milestone 2 -- Feature Schema Definition
```
Define in feature_engineering_service.py:

sentiment_dims (4):
  [sentiment_score, sentiment_confidence, news_intensity, sentiment_momentum]

llm_signal_dims (8):
  [market_regime_one_hot(4), equity_alloc_target, crypto_alloc_target,
   expected_vol_regime, macro_sentiment_score]

Total: 46 base + 12 LLM = 58 equity dims (not 46)
       or LLM dims are WITHIN the 46 -- specify which interpretation
```

### Amendment 3: Add to Milestone 3 -- Signal Unification
```
Modify DRLStrategy to be the SOLE signal source when DRL model is available.
LLM becomes a feature provider, not a signal generator.
Rule-based becomes emergency fallback only (DRL model load failure).

Deprecate the LLM-direct signal path (_generate_ai_trading_signal returning
trade decisions) in favor of LLM-as-feature-extractor.
```
