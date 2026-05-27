# AI Pipeline Causal Analysis (2026-02-24)

## FATAL: Unregistered Tool Dispatch
- `doc.rewrite` sent by GO Notes preload --> NOT handled in agent.py _tool_dispatch
- `calendar.suggest` sent by GO Calendar preload --> NOT handled in agent.py _tool_dispatch
- Both return {"status":"ignored","reason":"unknown_tool"} -- Ollama never called
- Preload fallback masks failure: user sees echo of own text or hardcoded string

## Timeout Conflict Triple
- Client AbortController: 10,000ms (preload.ts)
- CircuitBreaker latency threshold: 5,000ms (api.py:42) -- trips on normal inference
- Ollama requests timeout: 45,000ms (model_manager.py:42)
- Result: Client aborts at 10s, server keeps computing up to 45s, circuit breaker records failure at 5s

## Timeout Probability Model (Llama 3.2 3B Q4, i7-8565U CPU)
- Token rate: ~10 tok/s (Q4_K_M, CPU)
- P(timeout|50 output tokens) = 0.08
- P(timeout|80 output tokens) = 0.38
- P(timeout|100 output tokens) = 0.65
- P(timeout|150 output tokens) = 0.95
- "expand" action is near-certain timeout (produces more tokens than input)

## Variance Decomposition (AI Output Quality)
- Model capability (3B Q4): 35%
- Input truncation (500 chars): 30%
- HTML stripping (semantic loss): 20%
- Prompt design: 15%
- R2=0.44 (marginal, needs empirical validation)

## Remediation Priority
1. Register doc.rewrite + calendar.suggest in agent.py (BLOCKING)
2. Align timeouts: client=60s, circuit breaker latency=30s, Ollama=45s
3. Replace stripHtml with htmlToMarkdown (preserve structure for 3B model)
4. Increase MAX_AI_EXCERPT_LEN from 500 to 2000 chars
5. Pass calendar context (events, hours) for schedule suggestions
6. Add task-specific prompts per action type
