# Wave 4 AI E2E Audit (2026-03-02)

## Final Grade: B+

Files audited: agent.py, api.py, model_manager.py, mail_tool.py,
file_tool.py, system_tool.py, test_agent.py (66), test_api.py (64), test_mail_tool.py (76)

## P0 Findings

### P0-A: Circuit breaker never trips on Ollama outage (UNFIXED as of 2026-03-02)
- `generate()` returns _FALLBACK_MESSAGE as a normal ModelResponse (latency_ms=0)
- `guarded_call()` sees ok=True, latency=0 — records SUCCESS to circuit breaker
- k8s /healthz returns 200 throughout the outage — no restart signal
- **Fix**: When generate() returns fallback, record latency_ms=30_001 to breaker
  OR raise a typed exception that guarded_call catches and maps to breaker.record(ok=False)
  before returning the friendly response to the user.

## P1 Findings

### P1-1: JWT validation conditional on IDENTITY_JWT_PUBLIC_KEY (dev default = unset)
- When env var is unset, _validate_user_token() is a complete no-op
- Any service-token holder can pass arbitrary req.user without identity check
- Fix: Add logger.warning at module load when key is unset

### P1-2: FileTool.read_doc() / save_doc() bypass _validate_path()
- doc_id passed directly to URL: f"{base}/docs/{doc_id}" — traversal surface
- Fix: Apply _validate_path(str(doc_id)) before URL construction

### P1-3: SystemTool.settings() and .power() exist, not in _ALLOWED_TOOLS, zero tests
- Latent surface if developer adds to _ALLOWED_TOOLS without auditing
- Fix: Add "NOT REGISTERED" docstring + assert test

### P1-4: AI tests excluded from pyproject.toml testpaths (confirmed still present)
- Must run: pytest ai/genesys-ai/tests separately
- CI YAML must explicitly include this step

## P2 Findings

### P2-1: BrowserTool.click() / .type() — no CSS selector sanitization
- _sanitize_payload_all_strings only applies PII patterns, not char allowlist
- Fix: _validate_selector() with alphanumeric + safe CSS chars allowlist

### P2-2: DriftMetricsBuffer.summary() — 3 separate O(n) passes (advisory-level at maxlen=100)

### P2-3: _sanitize_user_id strips Cc/Cs but NOT Cf (zero-width format chars)
- U+200C/U+200D/U+00AD can visually disguise user IDs in provenance log
- Fix: Add "Cf" to category exclusion set — 1 char change

### P2-4: validate_response_text() truncation loop is O(n²/100) for large inputs
- Worst case at current scale (~25 KB): ~150 iterations — acceptable
- Fix if _MAX_RESPONSE_BYTES ever raised: use binary-search slice

## Advisory Findings

### A-1: No config.py — configuration scattered across 3 files, no startup validation
- Fix: Pydantic BaseSettings or manual validation function at module load

### A-2: _HALLUCINATION_PATTERNS does not strip canonical TOOL_CALL format
- If tool not in _ALLOWED_TOOLS (ignored), raw "TOOL_CALL: {...}" appears in response
- Fix: Add re.compile(r"TOOL_CALL\s*:\s*\{.*?\}", re.DOTALL) to _HALLUCINATION_PATTERNS

### A-3: _RETRY_BACKOFF_S=1.0 means 2-retry sequence blocks thread for 3s minimum
- Acceptable for single-user EliteBook x360; document the trade-off

### A-4: Dual tone validation (dispatch layer + MailTool.draft()) returns different schemas
- Dispatch: {"status":"ignored","reason":"invalid_tone","tool":...}
- MailTool direct: {"status":"error","reason":"invalid_tone: '...'..."}
- Fix: Remove validation from MailTool.draft(), keep only in dispatch layer

## Critical Test Coverage Gap

**JWT active branch = 0% coverage**
- _validate_user_token() lines 249-273 (api.py) — never exercised
- All 64 test_api.py JWT tests run with IDENTITY_JWT_PUBLIC_KEY unset (no-op path)
- Need 4-5 tests with a real Ed25519 test keypair
- Use cryptography.hazmat.primitives.asymmetric.ed25519 to generate test keys inline

## What Is Working Well

- output validation: 10KB ceiling + 4 hallucination patterns, 12 tests, all auth-gated
- DriftMetricsBuffer: ring buffer, auth-gated /metrics/drift, 5 tests including rate verification
- PII redaction: 5 pattern types, 2 layers (preload + agent), 18 tests
- TOOL_CALL parsing: raw_decode() handles nested JSON, first-match semantics correct
- Tool allowlist: frozenset gate before all dispatch logic
- hmac.compare_digest: timing-safe token comparison
- health_check() TTL cache: 30s, prevents thundering-herd, invalidate_health_cache() available
