# Vanguard Disruptive Alchemist -- Persistent Memory

## Sacred Cows Identified (2026-03-08)

1. **Ruth 13-step sequential pipeline is wrong** -- Steps 1-6 have zero data dependencies. asyncio.gather fan-out reduces 6-16s to 2-6.5s. Codebase already uses asyncio.gather in 13+ locations.
2. **`rag_mode` field exists on 10/20 agents but retrieval layer was never built** -- This is the biggest gap in the EFT architecture. eft_agent_config.py defines rag_mode but no retriever connects to it.
3. **DoRA per-domain is premature** -- Base model + prompt differentiation already handles 20 agents. 46K training examples too small to split across 12 adapters. Build RAG first, then 1 DoRA for persona.
4. **Go rewrites for Ruth Core = wrong battle** -- GPU inference is 75-85% of pipeline latency. CPU computation is 0.2-0.5%. Rewriting 0.5% in Go is invisible.
5. **60s auto-trading loop wastes 70% of GPU cycles** -- Most cycles produce HOLD signals. Price-change gate before vLLM invocation eliminates waste.
6. **vLLM semaphore at 16 is unbenchmarked** -- eft_enhance.py:35 raised from 4 to 16 without L4 saturation testing. Actual 14B 4-bit throughput saturates at 6-8 concurrent.

## Key File Locations

- EFT agent configs: `backend/app/services/eft_agent_config.py` (20 agents, 322 lines)
- EFT enhance utility: `backend/app/services/eft_enhance.py` (circuit breaker, semaphore, fallback)
- Signal fusion: `backend/app/services/signal_fusion_service.py` (4-source weighted fusion)
- Regime detection: `backend/app/services/regime_detection_service.py` (5-quadrant, 1h cache)
- Signal gate: `backend/app/services/signal_gate_service.py` (isotonic calibration)
- Kelly sizer: `backend/app/trading_engine/risk/kelly_sizer.py` (fractional Kelly + vol + DD)
- Auto-trading loop: `backend/app/services/auto_trading_service.py` (~1400 lines, hot loop at line 620+)
- Ruth tables migration: `backend/alembic/versions/add_ruth_tables_2026_03_08.py` (5 tables)
- Ruth spec: `RUTH_MASTER_SPECIFICATION.md` (~1200 lines, canonical)
- WASM modules: `frontend/src/wasm/src/` (lib.rs, statistics.rs, options.rs, portfolio.rs, backtest.rs)
- Redux store: `frontend/src/store/store.ts` (15 API slices + 9 reducers)

## Disruption Scores (for future reference)

| Intervention | Impact | Effort | Score |
|---|---|---|---|
| Parallel Ruth pipeline | 8 | 3 | 9.2 |
| SSE streaming for Ruth | 9 | 2 | 8.5 |
| Prompt compression | 7 | 2 | 8.3 |
| pgvector semantic memory | 8 | 3 | 7.8 |
| RAG retrieval layer | 8 | 4 | 7.5 |
| Tiered inference (3B+14B) | 7 | 4 | 7.3 |
| Conditional loop execution | 6 | 2 | 7.0 |
| Speculative decoding | 8 | 5 | 7.0 |

## Architectural Patterns (reusable insights)

- **Continuous-state vs request-response**: Institutional quant desks pre-compute regime/macro snapshots continuously. Ruth should assemble from caches, not recompute on demand. Existing caches (regime 1h, macro 24h) already support this.
- **Pacemaker pattern**: Do not compute from scratch each cycle. Maintain continuous state, trigger on threshold crossing. Applies to auto-trading loop.
- **Hippocampal indexing**: pgvector embeddings serve as semantic indices into full JSONB decision records. Same pattern as biological memory: compressed index -> full reconstruction.
- **Immune system architecture**: RAG first (generalist + retrieval), fine-tune only after evidence of failure (specialized adapter for proven recurring patterns).

## Deliverables Produced

- `docs/DISRUPTIVE_ALCHEMIST_2026_03.md` -- Phase 4A comprehensive audit (2026-03-08)
