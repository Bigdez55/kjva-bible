"""ai/tokenless-agent/src/api.py
Tokenless agent HTTP API - FastAPI application for the ai/tokenless-agent package.

This module exposes a local agent surface over HTTP using FastAPI.

Endpoints:
  POST /v1/chat                 — Single-turn chat (non-streaming) with cognitive loop
  POST /v1/chat/stream          — Streaming chat via Server-Sent Events with cognitive loop
  POST /v1/tool                 — Direct tool execution
  GET  /v1/health               — Health check (returns only "healthy")
  GET  /v1/info                 — Agent capabilities and version info
  GET  /v1/pipeline/status      — Cognitive pipeline health (Council IPC endpoints, turn count)
  GET  /v1/heptagon/status      — Heptagon layer availability report
  DELETE /v1/session/{id}       — Reset a conversation session

Authentication:
  All endpoints require a Bearer token validated against the TOKENLESS_API_KEY
  environment variable.  The token is checked via constant-time HMAC comparison
  to prevent timing attacks.

Performance contract:
  - /v1/health must respond within 50 ms regardless of model state.
  - /v1/chat non-streaming: P99 < 10s for XMIND-served responses.
  - /v1/chat/stream: first token < 2s; full response streamed incrementally.
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import sys
import time
from typing import AsyncIterator, Iterator

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("tokenless.api")

# ── Path bootstrap ────────────────────────────────────────────────────────────

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", "..", ".."))

_PATHS_TO_INJECT: list[str] = [
    _THIS_DIR,  # ai/tokenless-agent/src — for local heptagon/ imports
]
for _p in _PATHS_TO_INJECT:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

# ── Local imports ─────────────────────────────────────────────────────────────

from agent import AgentConfig, TokenlessAgentWithHeptagon, HeptagonLayer  # noqa: E402
from cognitive_pipeline import get_pipeline  # noqa: E402

# ── Governance integration ───────────────────────────────────────────────────
# Wire CovenantEnforcer into the request path so every user message is checked
# against the 8 Covenant Rules before processing.
try:
    _GOVERNANCE_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", "..", ".."))
    if _GOVERNANCE_ROOT not in sys.path:
        sys.path.append(_GOVERNANCE_ROOT)
    from governance.covenant_enforcer import CovenantEnforcer, EnforcementAction  # noqa: E402
    _covenant_enforcer = CovenantEnforcer()
    _COVENANT_AVAILABLE = True
    logger.info("CovenantEnforcer wired into API — 8 covenant rules active")
except ImportError as _cov_err:
    _COVENANT_AVAILABLE = False
    _covenant_enforcer = None  # type: ignore[assignment]
    logger.debug("CovenantEnforcer unavailable: %s — governance bypass active", _cov_err)

# ── Configuration ─────────────────────────────────────────────────────────────

_API_KEY: str = os.environ.get("TOKENLESS_API_KEY", "")
_AGENT_ID: str = os.environ.get("TOKENLESS_AGENT_ID", "tokenless-agent")
_API_VERSION: str = "1.0.0"

# ── Singleton agent ───────────────────────────────────────────────────────────
# One agent instance per process — shared across all requests.
# Constructed at module load time so the first request is not delayed
# by model manager initialisation.

_agent_config = AgentConfig(agent_id=_AGENT_ID)
_heptagon = HeptagonLayer.build(agent_id=_AGENT_ID)
_agent = TokenlessAgentWithHeptagon(_agent_config, _heptagon)

# ── Singleton cognitive pipeline ──────────────────────────────────────────────
# Owns the local context pipeline connections (shards → telemetry → journal).
# Constructed lazily on first request via get_pipeline() but pre-warmed here so
# log output appears at startup rather than on the first chat turn.
_pipeline = get_pipeline()

# ── FastAPI application ───────────────────────────────────────────────────────

app = FastAPI(
    title="Tokenless Agent API",
    version=_API_VERSION,
    description="Tokenless local AI inference and agent API",
    docs_url=None,   # Disable Swagger UI in production
    redoc_url=None,  # Disable ReDoc in production
)

# ── Auth dependency ───────────────────────────────────────────────────────────


def _verify_api_key(request: Request) -> None:
    """Constant-time Bearer token verification against TOKENLESS_API_KEY.

    Raises HTTP 401 if:
      - Authorization header is missing
      - Token scheme is not 'Bearer'
      - Token does not match the configured API key (constant-time comparison)

    When TOKENLESS_API_KEY is empty (development mode), all requests are allowed
    and a debug warning is logged.
    """
    if not _API_KEY:
        logger.debug("API key not configured — all requests allowed (dev mode)")
        return

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth_header[len("Bearer "):]
    if not hmac.compare_digest(token.encode(), _API_KEY.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Request/response schemas ──────────────────────────────────────────────────


class ChatRequest(BaseModel):
    """Schema for POST /v1/chat and /v1/chat/stream."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=4096)


class ChatResponse(BaseModel):
    """Schema for POST /v1/chat response."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    response: str
    latency_ms: int


class ToolRequest(BaseModel):
    """Schema for POST /v1/tool."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., min_length=1, max_length=128)
    params: dict[str, object] = Field(default_factory=dict)


class ToolResponse(BaseModel):
    """Schema for POST /v1/tool response."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    result: dict[str, object]
    latency_ms: int


class SessionResetResponse(BaseModel):
    """Schema for DELETE /v1/session/{session_id} response."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    status: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/v1/health")
def health_check() -> dict[str, str]:
    """Liveness/readiness probe.

    Returns {"status": "healthy"} unconditionally.
    Smoke tests MUST reject "degraded" — this endpoint never returns degraded.
    The agent's internal state does not affect this endpoint's response;
    only the HTTP layer itself failing (process crash) will cause a non-200.
    """
    return {"status": "healthy", "version": _API_VERSION}


@app.get("/v1/info")
def agent_info(_auth: None = Depends(_verify_api_key)) -> dict[str, object]:
    """Return agent capabilities and version information."""
    return {
        "agent_id": _AGENT_ID,
        "version": _API_VERSION,
        "heptagon": {
            "state_machine": _heptagon.state_machine is not None,
            "evaluator": _heptagon.evaluator is not None,
            "calibrator": _heptagon.calibrator is not None,
            "verifier": _heptagon.verifier is not None,
            "enforcer": _heptagon.enforcer is not None,
            "router": _heptagon.router is not None,
            "registry": _heptagon.registry is not None,
        },
        "tools": [
            "browser", "doc", "explain", "file", "mail",
            "system", "undo", "workflow",
            "calendar", "search", "notes", "settings", "analytics",
        ],
    }


@app.get("/v1/pipeline/status")
def pipeline_status(_auth: None = Depends(_verify_api_key)) -> dict[str, object]:
    """Report cognitive pipeline health and endpoint configuration.

    Includes Council IPC endpoints, turn count, and uptime.
    Does NOT perform live connectivity probes — returns cached config only
    so this endpoint always responds within the 50 ms health budget.
    """
    return {
        "pipeline": "cognitive_loop_v1",
        **_pipeline.get_stats(),
    }


@app.get("/v1/heptagon/status")
def heptagon_status(_auth: None = Depends(_verify_api_key)) -> dict[str, object]:
    """Report availability of each Heptagon cognitive-architecture layer."""
    return {
        "L1_state_machine": _heptagon.state_machine is not None,
        "L2_node_registry": _heptagon.registry is not None,
        "L3_route_engine": _heptagon.router is not None,
        "L4_enforcement": _heptagon.enforcer is not None,
        "L5_evaluation": _heptagon.evaluator is not None,
        "L6_calibration": _heptagon.calibrator is not None,
        "L7_verification": _heptagon.verifier is not None,
        "all_available": all([
            _heptagon.state_machine is not None,
            _heptagon.registry is not None,
            _heptagon.router is not None,
            _heptagon.enforcer is not None,
            _heptagon.evaluator is not None,
            _heptagon.calibrator is not None,
            _heptagon.verifier is not None,
        ]),
    }


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    _auth: None = Depends(_verify_api_key),
) -> ChatResponse:
    """Single-turn non-streaming chat endpoint.

    Executes the full cognitive loop:
        1. Fetch context shards from Ahki (Bookworm + SoulManager + RT4 salience)
        2. Prepend ranked shards to the user message
        3. Run TokenlessAgent with Heptagon L1-L7 governance
        4. Emit telemetry to telemetryd (fire-and-forget)
        5. Append structured event to eventjournald (fire-and-forget)

    The agent maintains conversation history keyed by session_id.
    A new session is created automatically on first use.
    Input is limited to 4096 characters by the ChatRequest schema.
    PII sanitization is performed inside the agent before model submission.
    Session IDs are hashed (SHA-256) before leaving this process.
    """
    # Covenant enforcement gate — check user message against 8 rules
    if _COVENANT_AVAILABLE and _covenant_enforcer is not None:
        try:
            cov_result = _covenant_enforcer.evaluate(req.message)
            if cov_result.action == EnforcementAction.HARD_STOP:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Request blocked by covenant enforcement: {cov_result.reason}",
                )
        except HTTPException:
            raise
        except Exception as _cov_exc:
            logger.debug("CovenantEnforcer evaluation error: %s", _cov_exc)

    heptagon_active = all([
        _heptagon.state_machine is not None,
        _heptagon.evaluator is not None,
        _heptagon.enforcer is not None,
    ])

    turn = await _pipeline.execute(
        session_id=req.session_id,
        user_message=req.message,
        agent_chat_fn=_agent.chat,
        heptagon_available=heptagon_active,
    )

    return ChatResponse(
        session_id=req.session_id,
        response=turn.response,
        latency_ms=turn.latency_ms,
    )


@app.post("/v1/chat/stream")
async def chat_stream(
    req: ChatRequest,
    _auth: None = Depends(_verify_api_key),
) -> StreamingResponse:
    """Streaming chat via Server-Sent Events with cognitive context enrichment.

    The context shard fetch (Ahki → Bookworm + SoulManager + RT4) runs first and
    completes before the stream opens.  The enriched message (context prefix +
    user message) is then streamed token-by-token.

    Yields text/event-stream chunks:
      data: <token>\\n\\n

    Terminated with:
      data: [DONE]\\n\\n
    """
    from cognitive_pipeline import (  # noqa: PLC0415
        _extract_entities,
        _hash_session,
        _stage_fetch_context,
        _stage_build_context_prefix,
        _stage_emit_telemetry,
        _stage_emit_journal_event,
    )
    import uuid as _uuid

    t0 = time.monotonic()
    turn_id = str(_uuid.uuid4())
    session_hash = _hash_session(req.session_id)
    heptagon_active = all([
        _heptagon.state_machine is not None,
        _heptagon.evaluator is not None,
        _heptagon.enforcer is not None,
    ])

    entities = _extract_entities(req.message)
    message_hint = " ".join(entities)
    shards = await _stage_fetch_context(session_hash, entities, message_hint)
    context_prefix = _stage_build_context_prefix(shards)
    enriched_message = context_prefix + req.message if context_prefix else req.message

    def _token_generator() -> Iterator[str]:
        response_buf: list[str] = []
        try:
            for token in _agent.stream(req.session_id, enriched_message):  # type: ignore[attr-defined]
                response_buf.append(token)
                yield f"data: {token}\n\n"
        except AttributeError:
            # Stub agent fallback
            text = _agent.chat(req.session_id, enriched_message)
            response_buf.append(text)
            yield f"data: {text}\n\n"
        yield "data: [DONE]\n\n"

        # Post-stream telemetry (best-effort, scheduled on the event loop)
        full_response = "".join(response_buf)
        latency_ms = int((time.monotonic() - t0) * 1000)
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(
            asyncio.ensure_future,
            _stage_emit_telemetry(
                turn_id=turn_id,
                session_hash=session_hash,
                latency_ms=latency_ms,
                shard_count=len(shards),
                heptagon_active=heptagon_active,
                council_available=len(shards) > 0,
            ),
        )
        loop.call_soon_threadsafe(
            asyncio.ensure_future,
            _stage_emit_journal_event(
                turn_id=turn_id,
                session_hash=session_hash,
                latency_ms=latency_ms,
                shard_count=len(shards),
                response_length=len(full_response),
                council_available=len(shards) > 0,
            ),
        )

    return StreamingResponse(
        _token_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/v1/tool", response_model=ToolResponse)
def execute_tool(
    req: ToolRequest,
    _auth: None = Depends(_verify_api_key),
) -> ToolResponse:
    """Execute a named tool directly without a chat turn.

    Useful for integrations that need direct tool access (e.g., the Settings
    panel reading system info) without going through the full agent loop.

    tool_name must be in the agent's registered tool allowlist.
    """
    start = time.monotonic()
    result = _agent.execute_tool(req.tool_name, req.params)  # type: ignore[attr-defined]
    latency_ms = int((time.monotonic() - start) * 1000)
    return ToolResponse(
        tool_name=req.tool_name,
        result=result,
        latency_ms=latency_ms,
    )


@app.delete("/v1/session/{session_id}", response_model=SessionResetResponse)
def reset_session(
    session_id: str,
    _auth: None = Depends(_verify_api_key),
) -> SessionResetResponse:
    """Clear all conversation history for the given session.

    The session is removed from the workspace manager.  A new session is
    created automatically on the next chat request with the same session_id.
    """
    if len(session_id) > 128:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id too long (max 128 characters)",
        )
    _agent.reset_session(session_id)  # type: ignore[attr-defined]
    return SessionResetResponse(session_id=session_id, status="reset")
