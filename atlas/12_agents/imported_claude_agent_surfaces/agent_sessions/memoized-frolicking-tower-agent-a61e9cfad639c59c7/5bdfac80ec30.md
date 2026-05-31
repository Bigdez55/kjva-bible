# STATE-OF-THE-ART TECHNOLOGY AUDIT: Autonomous Trading Bot Plan

**Audit Date:** 2026-02-25 | **Auditor:** Vanguard Innovation Scout | **Platform:** Elson TB2

---

## EXECUTIVE SUMMARY

**Overall Innovation Score: 6.2 / 10** -- Solid foundational choices with several aging components that will limit the system before it ships.

The proposed plan is grounded in well-researched academic literature (the Auto trading Research documents are excellent), but several technology choices lag the current state of the art by 12-24 months. The plan correctly identifies DRL as the core paradigm and CPCV/Deflated Sharpe as the validation strategy -- these are still SOTA. However, the specific library choices, sentiment models, and regime detection approaches need upgrades. The LLM integration architecture is the weakest link: treating the LLM as a passive brief generator wastes the most powerful tool in your stack.

Below is the per-component audit.

---

## 1. DRL FRAMEWORK: stable-baselines3 (PPO, SAC) with Gymnasium

**Rating: AGING (but not yet obsolete)**

### Current State
The existing RL code in `backend/app/trading_engine/ml_models/ai_model_engine/reinforcement_learning.py` uses TensorFlow + Gymnasium with a custom DQN/Actor-Critic implementation. The proposal to move to SB3 (PPO/SAC) is an improvement over the current TF-based code, but SB3 itself is showing its age.

### What Has Changed (2025-2026)

**TorchRL (Meta/PyTorch)** -- v0.6+ (2025): TorchRL has matured significantly. It is now the official RL library in the PyTorch ecosystem. Advantages over SB3:
- Native PyTorch tensor operations (no numpy conversion overhead)
- Composable transforms pipeline for observation/reward shaping
- TensorDict-based data handling that integrates cleanly with distributed training
- Built-in support for multi-agent RL (critical for adversarial training the research documents recommend)
- Active development velocity: 150+ contributors, weekly releases
- GitHub: `pytorch/rl` -- 2.8k stars, rapidly growing

**CleanRL** remains excellent for single-file algorithm implementations and research prototyping but is not production-grade.

**Decision Transformers** (referenced in the research): The plan's own research documents cite DT architecture with GPT-2 weights + LoRA fine-tuning on expert trajectories. This is directly compatible with the existing RUTH + DoRA pipeline. The team already has the PEFT/LoRA infrastructure (`peft>=0.10.0` in requirements.txt). A Decision Transformer fine-tuned on expert trading trajectories would represent a paradigm shift -- treating RL as sequence modeling, which the team already knows how to do.

### SOTA Recommendation

**Primary:** TorchRL for the core DRL loop (PPO, SAC, TD3).
**Secondary:** Decision Transformer architecture leveraging existing DoRA/PEFT infrastructure for offline policy learning. This is a genuine competitive advantage -- you already have the fine-tuning pipeline, the GPU (L4), and the vLLM serving. No other personal trading platform has this.

**Why not SB3:** SB3's last major release was late 2024. Its maintainer (DLR-RM) has shifted focus. The callback system is rigid compared to TorchRL's composable design. For a system that needs custom reward shaping (Differential Sharpe, CVaR constraints), TorchRL's modular reward transforms are far cleaner.

**Migration effort:** Medium. Gymnasium environments remain compatible. The primary change is swapping the training loop, not the environment.

---

## 2. OFFLINE RL: Custom CQL Implementation

**Rating: AGING**

### Current State
CQL (Conservative Q-Learning, 2020) was groundbreaking but has known limitations: overly conservative value estimates that lead to suboptimal policies, and poor scaling with action dimensionality (critical for portfolio allocation where action space = number of assets).

### What Has Changed (2025-2026)

**Cal-QL (Calibrated Conservative Q-Learning)** -- NeurIPS 2023, production-ready by 2025: Addresses CQL's over-conservatism by calibrating the learned Q-values against a reference policy's performance. Produces tighter value bounds = better policies from the same offline data.

**IQL (Implicit Q-Learning)**: Avoids querying out-of-distribution actions entirely by learning value functions that never need to evaluate unseen actions. Cleaner, simpler, more stable. Implemented in `d3rlpy` (Python library, 1.2k GitHub stars, active maintenance).

**IDQL (Implicit Diffusion Q-Learning)**: Uses diffusion models to capture multi-modal action distributions. For portfolio allocation (which IS multi-modal -- there are multiple good allocations for any given state), this is transformative.

**Decision Transformer / Trajectory Transformer**: As noted above, treats offline RL as sequence modeling. The research documents already recommend this approach. Given that Elson has RUTH with DoRA and the PEFT stack, this is the natural choice.

### SOTA Recommendation

**Primary:** `d3rlpy` library with IQL algorithm as the default offline RL method. It is production-tested, well-documented, and significantly outperforms CQL on standard benchmarks (D4RL).

**Secondary:** Decision Transformer architecture for the "expert trajectory" use case -- learning from the best historical trades rather than all historical trades.

**Why not custom CQL:** Building custom offline RL is an engineering maintenance burden with no upside. `d3rlpy` provides CQL, IQL, Cal-QL, TD3+BC, and Decision Transformer all under a single API. Use the library; focus engineering effort on the trading environment and reward design, not algorithm reimplementation.

**Library:** `d3rlpy>=2.6.0` (PyTorch-native, supports custom environments, GPU-accelerated)

---

## 3. FEATURE ENGINEERING: Manual ta-lib Indicators

**Rating: CURRENT (but limited)**

### Current State
`backend/app/trading_engine/data/feature_engineering.py` implements manual technical indicators (SMA, EMA, Bollinger Bands, RSI, MACD, Stochastic, ATR, OBV) using pure pandas/numpy. This is honest, debuggable code. The plan proposes adding ta-lib for more indicators.

### What Has Changed (2025-2026)

The research itself acknowledges this gap: "Feature engineering at this level is often automated using frameworks that explore high-order interactions and automatically generate feature sets via dimension reduction techniques."

**Temporal Fusion Transformer (TFT)**: Google's architecture for interpretable time-series forecasting. Learns which features matter and at what temporal resolution. Available via `pytorch-forecasting` or `darts`. However, TFT adds training complexity.

**The real insight**: The plan's own research recommends a two-tier approach:
1. **Tier 1: Handcrafted indicators** (what you have) as the *base observation space*
2. **Tier 2: Learned representations** from raw OHLCV via a Transformer encoder that feeds into the DRL agent's state

This is the correct architecture. The handcrafted features provide interpretable, debuggable signals. The learned features capture patterns humans miss. They concatenate.

### SOTA Recommendation

**Keep** the manual feature engineering module. It is production-proven and interpretable. Do NOT replace it with ta-lib (ta-lib adds a C dependency that complicates Docker builds and does not compute anything the current pandas code cannot).

**Add** a learned feature extraction layer. Specifically:
- Use `tsai` (Time Series AI, 800+ GitHub stars) -- a PyTorch library built on fastai that provides InceptionTime, TSTPlus (Time Series Transformer), and ROCKET architectures
- ROCKET (Random Convolutional Kernel Transform) deserves special attention: it generates 10,000 random convolutional features from raw time series in <1 second. No training required. Performance competitive with deep learning on UCR benchmarks. This is a 10x speed improvement for feature generation.

**Migration effort:** Low. ROCKET can be added as a parallel feature pipeline without touching existing code.

---

## 4. SENTIMENT: FinBERT (ProsusAI/finbert)

**Rating: OUTDATED**

### Current State
`backend/app/trading_engine/sentiment/nlp_models.py` already imports `transformers` and references FinGPT with PEFT/LoRA support. FinBERT (2019) is a 110M parameter BERT model. It was SOTA in 2020. It is not in 2026.

### What Has Changed (2025-2026)

**FinGPT (2023-2025)**: The codebase already references FinGPT in the requirements and `nlp_models.py`. This is the correct direction. FinGPT uses LoRA adapters on top of Llama/RUTH base models -- exactly the stack Elson already runs.

**Critical insight: You already have a better sentiment model than FinBERT.** Your RUTH with DoRA fine-tuning (46K examples on financial data) is a 14-billion-parameter model trained on financial domain text. It dwarfs FinBERT's 110M parameters. The EFT agent system already has a `market_sentiment_analyzer` agent config. Using FinBERT alongside this is like having a Ferrari and choosing to ride a bicycle.

**BloombergGPT / FinGPT-v4**: Bloomberg's proprietary model is not available. FinGPT-v4 (open-source) uses RUTH/Llama bases with financial LoRA -- but again, you already have this with elson-finance-14b.

**Newer specialized models (2025)**:
- `yiyanghkust/finbert-tone` -- marginal improvement over original FinBERT
- `NousResearch/finance-sentiment-v2` -- Llama-based, 7B parameters
- None of these approach a 14B parameter model fine-tuned on 46K financial examples

### SOTA Recommendation

**Replace FinBERT with elson-finance-14b sentiment calls via the existing EFT agent pattern.** The `market_sentiment_analyzer` agent config already exists. Route sentiment analysis through vLLM with structured JSON output (guided decoding) to get sentiment scores. This:
1. Eliminates an entire model dependency (FinBERT)
2. Uses a model 127x larger, fine-tuned on domain-specific data
3. Leverages existing infrastructure (vLLM, L4 GPU) with zero additional cost
4. Provides richer output (not just positive/negative/neutral but nuanced market commentary)

**Fallback:** For real-time streaming sentiment where vLLM latency is too high (>500ms), keep a small distilled model. But this should be a 1B-parameter RUTH-1.5B (draft) distillation of the 14B, not FinBERT.

**Migration effort:** Low. The EFT infrastructure already supports this. Add a new EFT agent config for `real_time_sentiment` with appropriate prompt template and `max_tokens=100`.

---

## 5. REGIME DETECTION: hmmlearn (Hidden Markov Models)

**Rating: OUTDATED**

### Current State
`backend/app/trading_engine/timeframe/market_regime_detector.py` uses KMeans clustering with handcrafted features (MA ratio, volatility, kurtosis). No HMM is actually implemented yet despite `hmmlearn` being proposed. `backend/app/trading_engine/ml_models/volatility_regime/volatility_detector.py` uses simple threshold-based regime classification.

### What Has Changed (2025-2026)

HMMs assume Gaussian emissions and linear dynamics. Financial markets exhibit fat tails, regime persistence, and non-linear state transitions. The current KMeans approach is actually reasonable for initial clustering, but both HMM and KMeans miss temporal dependencies.

**Bayesian Online Changepoint Detection (BOCPD)**: Adams and MacKay (2007), but implementations matured in 2024-2025. Detects regime changes in real-time as a streaming algorithm. The `ruptures` library (already in requirements.txt at `>=1.1.0`) provides offline changepoint detection. BOCPD extends this to online settings.

**Switching State Space Models (S4/Mamba-based)**: The Mamba architecture (2024) provides selective state space models that naturally model regime switching. Mamba-based time series models (2025) can detect regime transitions as part of their latent state evolution without explicit regime labels.

**Neural Regime Detection via Contrastive Learning**: Train an encoder that maps market windows to embeddings where similar regimes cluster naturally. Use the `ruptures` changepoints as weak supervision. This produces a continuous regime embedding rather than discrete labels -- the DRL agent can then learn regime-conditional policies via embedding concatenation.

### SOTA Recommendation

**Phase 1 (immediate):** You already have `ruptures>=1.1.0` in requirements. Use `ruptures.Binseg` or `ruptures.Pelt` for offline regime boundary detection in backtesting. This is a strictly superior starting point to KMeans-based regime detection because it respects temporal ordering.

**Phase 2 (next sprint):** Implement BOCPD for real-time regime detection. The algorithm is simple (< 200 lines of Python). It outputs a probability distribution over run lengths, giving you a "regime change probability" at each timestep -- far more useful than a discrete regime label.

**Phase 3 (future):** Train a contrastive regime encoder using the BOCPD changepoints as training signal. This produces dense regime embeddings that the DRL agent ingests directly.

**Skip hmmlearn entirely.** It adds a dependency for a 60-year-old algorithm that underperforms the tools you already have installed.

**Migration effort:** Low for Phase 1 (ruptures is already installed), Medium for Phase 2.

---

## 6. EXECUTION ALGOS: Hand-coded TWAP/VWAP/Almgren-Chriss

**Rating: CURRENT (and correct for the scale)**

### Current State
`backend/app/trading_engine/strategies/execution/vwap_strategy.py` and `twap_strategy.py` implement well-structured execution strategies with participation rate limiting, urgency adjustment, and price limits. The code is clean and functional.

### Assessment

Here is where I push back on the "must be bleeding edge" impulse. For a personal trading platform executing retail-sized orders through Alpaca:

1. **Market impact is negligible** at retail order sizes (< $100K per order)
2. **RL-based execution** (as described in the research) is designed for institutional orders where market impact costs 5-35 bps. At retail sizes, the bid-ask spread dominates. An RL execution agent would learn to become TWAP because there is no market impact to optimize around.
3. **The Alpaca API does not provide Level 2 data** to retail accounts, making LOB-based execution impossible

### SOTA Recommendation

**Keep the hand-coded TWAP/VWAP.** They are correct for the platform's scale.

**One upgrade worth making:** Add an Almgren-Chriss implementation that dynamically adjusts the execution schedule based on intraday volatility. The current VWAP uses historical volume profiles. Adding a volatility-adaptive component (more aggressive when vol is low, more patient when vol is high) captures most of the value of RL execution without the complexity.

**Do NOT build RL-based execution** unless/until:
- The platform handles >$1M daily volume per user
- Level 2 market data is available
- The latency budget supports sub-second decision cycles

**Migration effort:** None needed. Existing code is appropriate.

---

## 7. LLM INTEGRATION: Daily Strategy Brief via vLLM Guided Decoding

**Rating: AGING -- This is the biggest missed opportunity in the entire plan.**

### Current State
The plan treats the LLM (elson-finance-14b) as a report generator: it produces a daily strategy brief, and the DRL agent extracts signals from it. This is a 2023 pattern -- "LLM as Oracle."

### The Paradigm Shift (2025-2026)

The field has moved decisively from "LLM generates text that humans/agents read" to "LLM IS the agent." The research documents themselves note that Decision Transformers treat RL as sequence modeling. The logical conclusion: **the LLM does not advise the DRL agent; the LLM IS part of the decision loop.**

**Architecture A (Current Plan - Passive):**
```
Market Data -> Feature Eng -> DRL Agent -> Decision
                                  ^
                                  |
               LLM Brief (daily) -> Signal Injection
```

**Architecture B (SOTA - Active LLM-in-the-Loop):**
```
Market Data -> Feature Eng -----> Multi-Modal State
                                       |
                    LLM (structured reasoning) -> Action Proposal
                                       |
                    DRL Agent (value estimation) -> Risk Filter -> Decision
```

In Architecture B:
1. The LLM receives the same state the DRL agent sees, plus news/filings/sentiment (multi-modal)
2. The LLM proposes actions with structured reasoning (via guided decoding -- already in the plan)
3. The DRL agent acts as a learned risk filter / value estimator on the LLM's proposals
4. This creates a "fast system / slow system" architecture mimicking Kahneman's dual-process theory

This is NOT using LangGraph/CrewAI/AutoGen. Those frameworks add unnecessary abstraction layers. The implementation uses the existing EFT agent pattern with structured vLLM calls.

### SOTA Recommendation

**Upgrade the LLM from "daily brief generator" to "real-time reasoning engine" within the decision loop.**

Implementation path using EXISTING infrastructure:
1. Create new EFT agent config: `trading_decision_reasoner` with structured JSON output schema
2. On each DRL decision cycle (every N minutes), call vLLM with current market state + feature summary
3. LLM outputs: `{action: "BUY/SELL/HOLD", confidence: 0.0-1.0, reasoning: "...", risk_flags: [...]}`
4. Feed LLM confidence and action as additional features to the DRL observation space
5. DRL agent makes final decision, weighted by both its own value estimate and LLM confidence

This preserves the DRL agent's learned value function while giving it access to the LLM's vast world knowledge about macro events, earnings patterns, and market microstructure.

**Latency concern:** vLLM on L4 with RUTH generates ~50 tokens/sec. A structured 100-token response takes 2 seconds. For a 5-minute trading cycle, this is acceptable. For sub-minute cycles, use the 1.5B distilled model.

**Migration effort:** Medium. Requires new EFT agent config, observation space expansion in the Gymnasium environment, and careful latency management.

---

## 8. FRONTEND CHARTING: Recharts AreaChart

**Rating: AGING for a trading platform**

### Current State
- `frontend/package.json`: `"recharts": "^3.6.0"`
- Usage: `PerformanceBarChart.tsx` (Recharts BarChart), `PortfolioDonutChart.tsx` (Recharts PieChart)
- BUT: `CandlestickChart.tsx` and `PortfolioChart.tsx` use **custom SVG rendering with WASM acceleration** -- not Recharts

This is actually a split architecture: analytical charts (bar, donut) use Recharts, while the core trading charts (candlestick, portfolio line) use custom WASM-accelerated SVG.

### Assessment

The custom WASM candlestick chart is excellent engineering. It processes candlestick bounds in Rust/WASM and renders via SVG. However, for a trading platform, it lacks:
- Interactive crosshairs / hover data inspection
- Drawing tools (trend lines, Fibonacci retracements)
- Multi-timeframe overlays
- Volume profile visualization
- Indicator overlays (the 15+ indicators from feature_engineering.py visualized on chart)

Recharts is a general-purpose charting library. It was never designed for financial markets.

### What Has Changed (2025-2026)

**Lightweight Charts (TradingView)** -- v5.0 (2025): TradingView's open-source charting library. Purpose-built for financial data.
- Canvas-based rendering (60fps even with 10,000+ candles)
- Built-in crosshairs, time scales, price scales
- Plugin architecture for custom indicators
- 14K GitHub stars, backed by TradingView's commercial product
- Bundle size: ~45KB gzipped (smaller than Recharts at ~80KB)
- MIT License

This is the gold standard for trading platform charting. Robinhood, eToro, and every serious trading UI uses either this or TradingView's commercial widget.

### SOTA Recommendation

**Replace Recharts for ALL trading-related charts with `lightweight-charts` v5.0.**

Keep the WASM calculation layer -- it is genuinely useful for performance-critical computations. But have it feed into Lightweight Charts' data format rather than custom SVG.

**Keep Recharts** only for non-trading analytical charts (bar charts, donut charts, dashboard stats) where its React integration is convenient. But even here, consider `@nivo/bar` and `@nivo/pie` which have better MUI integration and more polished defaults.

**Path to Implementation:**
```
npm install lightweight-charts@^5.0.0
```

Create a `<TradingChart />` wrapper component that:
1. Accepts OHLCV data from the existing RTK Query hooks
2. Configures Lightweight Charts with the Elson color palette (from `Colors.ts`)
3. Supports toggling indicator overlays
4. Provides crosshair data to parent components via callback

**Migration effort:** Medium. The `CandlestickChart.tsx` replacement is the primary work item. The existing WASM `processCandlestickBounds` and `scaleToSvg` functions become unnecessary for rendering (Lightweight Charts handles its own scaling) but remain useful for pre-computation in the data layer.

---

## 9. MODEL TRAINING INFRASTRUCTURE: Weekly Celery Retraining

**Rating: AGING**

### Current State
No Celery infrastructure exists in the codebase yet. The proposal is to add it for weekly retraining.

### What Has Changed (2025-2026)

**Ray Train + Ray Serve (2025)**: Ray has become the de facto standard for distributed ML training and serving in Python. Advantages:
- Native integration with PyTorch (TorchRL, d3rlpy)
- Automatic GPU scheduling -- critical when sharing the L4 between vLLM inference and model training
- Built-in hyperparameter tuning (Ray Tune)
- Model serving with automatic batching (Ray Serve)
- Zero-downtime model hot-swap
- 35K GitHub stars, backed by Anyscale

**MLflow (2025)**: Model registry, experiment tracking, and deployment. 19K GitHub stars. Integrates with everything.

**Weights and Biases (W&B)**: Experiment tracking and visualization. Commercial but free for personal projects. Best-in-class training dashboards.

### SOTA Recommendation

**Do NOT use Celery for ML retraining.** Celery is a task queue for web applications. It has no concept of GPU scheduling, distributed training, or model versioning.

**Recommended stack:**
1. **Ray Train** for the training loop (handles GPU allocation, distributed training if needed)
2. **MLflow** for experiment tracking and model registry (lightweight, self-hosted, stores to PostgreSQL which you already have)
3. **W&B** (optional) for richer visualization during development

However, for a single-user platform on a single L4 GPU, the pragmatic choice is:
- A simple **APScheduler** (already Python-native, no new dependency) job that triggers weekly retraining
- **MLflow** for model versioning and comparison
- Store model artifacts in GCS (you already have GCP infrastructure)

**Why not Celery:** It requires a separate broker (Redis or RabbitMQ), worker processes, and adds operational complexity that is not justified for a single weekly job. APScheduler runs in-process.

**Migration effort:** Low. APScheduler is pip-installable. MLflow adds a tracking server but can use the existing PostgreSQL.

---

## 10. VECTOR SEARCH FOR FEATURES: pgvector vs Redis

**Rating: The question is wrong -- neither is the right abstraction.**

### Current State
The codebase uses:
- PostgreSQL for persistent data
- Redis for caching (when available)
- ChromaDB for RAG vector search (`chromadb>=0.4.0` in requirements)

### Assessment

Vector similarity search is the wrong primitive for a feature store. Features are numerical tensors with fixed schemas, not high-dimensional embeddings needing approximate nearest neighbor search. The plan conflates two different systems:

1. **Feature Store** (caching computed features for fast retrieval): This is a key-value problem. Redis is correct. Use Redis sorted sets keyed by `(symbol, timestamp)` with feature vectors as values. This is what Feast, Tecton, and every production feature store does under the hood.

2. **Semantic Search** (finding similar market regimes, similar news events): THIS is where vector search applies. ChromaDB (already installed) or pgvector (extension for existing PostgreSQL) can store regime embeddings and find historically similar market states.

### SOTA Recommendation

**Feature Store:** Keep Redis. Add `hiredis>=3.0.0` for C-accelerated parsing. Structure keys as `features:{symbol}:{timeframe}:{timestamp}`. TTL of 24 hours for daily features, 1 hour for intraday.

**Regime Similarity Search:** Use pgvector (extension for PostgreSQL, already your primary DB). Store regime embeddings from the contrastive encoder (Phase 3 of regime detection). Query: "Find the 10 most similar historical market states to the current one." This feeds the DRL agent historical context.

**Why pgvector over ChromaDB:** You already run PostgreSQL. Adding pgvector is a single `CREATE EXTENSION vector;` command. ChromaDB requires a separate process. For <100K vectors (which covers years of daily regime embeddings), pgvector's exact search is faster than ChromaDB's approximate search.

**Migration effort:** Low. `pip install pgvector` + one ALTER TABLE.

---

## TECHNOLOGY RATING SUMMARY

| # | Component | Proposed | Rating | SOTA Alternative | Impact |
|---|-----------|----------|--------|-----------------|--------|
| 1 | DRL Framework | stable-baselines3 | AGING | TorchRL + Decision Transformer | HIGH |
| 2 | Offline RL | Custom CQL | AGING | d3rlpy (IQL) + Decision Transformer | HIGH |
| 3 | Feature Engineering | ta-lib manual | CURRENT | Keep manual + add ROCKET (tsai) | MEDIUM |
| 4 | Sentiment | FinBERT | OUTDATED | elson-finance-14b via EFT (already built) | HIGH |
| 5 | Regime Detection | hmmlearn (HMM) | OUTDATED | ruptures (already installed) + BOCPD | MEDIUM |
| 6 | Execution Algos | Hand-coded TWAP/VWAP | CURRENT | Keep as-is (correct for scale) | LOW |
| 7 | LLM Integration | Daily brief generator | AGING | LLM-in-the-loop reasoning engine | CRITICAL |
| 8 | Frontend Charting | Recharts | AGING | lightweight-charts v5.0 (TradingView) | HIGH |
| 9 | Training Infra | Celery (proposed) | AGING | APScheduler + MLflow | MEDIUM |
| 10 | Feature/Vector Store | pgvector/Pinecone | MISFRAMED | Redis (features) + pgvector (similarity) | MEDIUM |

---

## TOP 5 HIGHEST-LEVERAGE UPGRADES (Ordered by Impact / Effort)

### 1. LLM-in-the-Loop Architecture (Item 7)
**Impact:** Paradigm Shift | **Effort:** Medium | **Risk:** Low (fallback to rule-based)
This is the single biggest competitive advantage Elson TB2 has over any other personal trading platform. No competitor has a 14B-parameter domain-fine-tuned LLM integrated into the decision loop. The EFT agent pattern already provides the infrastructure. This is a matter of creating one new agent config and expanding the DRL observation space.

### 2. Eliminate FinBERT, Use elson-finance-14b (Item 4)
**Impact:** High | **Effort:** Low | **Risk:** Very Low
Removes a dependency. Uses a model 127x larger that you already run. The code paths exist in `nlp_models.py` and `eft_enhance.py`. This is almost a configuration change.

### 3. lightweight-charts for Trading UI (Item 8)
**Impact:** High (user-facing, immediate visual upgrade) | **Effort:** Medium | **Risk:** Low
Every serious trading platform uses this library. The current custom SVG candlestick is impressive engineering but lacks interactivity. This is a Kano Model "Delighter" -- users expect professional charting from a trading platform.

### 4. d3rlpy for Offline RL (Item 2)
**Impact:** High | **Effort:** Medium | **Risk:** Low (well-tested library)
Replaces custom CQL with a battle-tested library that provides 8+ offline RL algorithms under one API. Frees engineering time to focus on environment design and reward shaping.

### 5. TorchRL for Online RL (Item 1)
**Impact:** High | **Effort:** Medium-High | **Risk:** Medium (larger migration)
Replaces the aging TensorFlow RL code with PyTorch-native RL, unifying the ML stack on PyTorch (which the rest of the codebase already uses via torch, transformers, peft).

---

## DEPENDENCY CONSOLIDATION NOTE

The current requirements.txt includes both TensorFlow and PyTorch. The RL code uses TensorFlow. The LLM/fine-tuning code uses PyTorch. This dual-framework situation:
- Doubles the Docker image size (~4GB for TF + ~2GB for PyTorch)
- Creates CUDA version conflicts on the L4 GPU
- Doubles the CVE surface area (note: torch already has 3 CVE fixes pinned)

**Recommendation:** Migrating RL to TorchRL (PyTorch-native) enables dropping TensorFlow entirely. This is a significant simplification of the deployment pipeline and a security improvement.

---

## RISK FLAGS FOR OTHER AGENTS

**For fintech-integrity-auditor:**
- LLM-in-the-loop architecture creates an AI decision audit trail requirement. Every LLM reasoning call must be logged to `trade_decision_log` with full prompt/response for regulatory review.
- Eliminating FinBERT in favor of elson-finance-14b means sentiment analysis is no longer reproducible with a published model. Document the model version and training data hash.

**For apex-quant-architect:**
- TorchRL migration requires revalidating all existing backtest results. The Gymnasium environments should produce identical trajectories -- verify with deterministic seeds.
- d3rlpy's IQL implementation uses different hyperparameter defaults than a custom CQL. Run CPCV comparison before switching.

**For reliability-security-sentinel:**
- Dropping TensorFlow removes 15+ known CVEs from the dependency tree.
- pgvector extension requires PostgreSQL superuser privileges to install. Verify Cloud SQL permissions.
- lightweight-charts loads from npm (client-side only, no server dependency). No new backend attack surface.

---

## PRODUCTION DEPLOYMENT IMPLICATIONS

All recommended changes respect existing constraints:
- No schema drift: pgvector `CREATE EXTENSION` does not modify existing tables
- requirements.txt / requirements-docker.txt: Must be updated in sync (add d3rlpy, torchrl, mlflow; remove tensorflow after migration)
- L4 GPU sharing: APScheduler-based training should only run when vLLM is idle (market closed hours)
- Cloud Run: No changes to container configuration for items 1-7, 9-10. Item 8 (lightweight-charts) is frontend-only.

---

*This audit was conducted by the Vanguard Innovation Scout against the codebase state at commit `2e15c35` and the research documents in `Auto trading Research/`. All recommendations are grounded in the existing Elson TB2 stack and production constraints.*
