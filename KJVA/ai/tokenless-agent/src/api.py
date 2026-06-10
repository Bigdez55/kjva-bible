"""ai/tokenless-agent/src/api.py
Tokenless agent HTTP API - FastAPI application for the ai/tokenless-agent package.

This module exposes a local agent surface over HTTP using FastAPI.

Endpoints:
  POST /v1/chat                 — Single-turn chat (non-streaming) with cognitive loop
  POST /v1/chat/stream          — Streaming chat via Server-Sent Events with cognitive loop
  POST /v1/tool                 — Direct tool execution
  GET  /v1/health               — Health check (returns only "healthy")
  GET  /v1/info                 — Agent capabilities and version info
  GET  /v1/pipeline/status      — Cognitive pipeline health (context-service IPC endpoints, turn count)
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
import base64
import hmac
import json
import logging
import os
import sys
import time
from typing import AsyncIterator, Iterator, Optional

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
    # 3-up: src -> tokenless-agent -> ai -> models v7 (where governance/ lives). Was 4-up,
    # which resolved to the parent "Tokenless models" (no governance/), so the covenant
    # import failed and the gate silently fell open.
    _GOVERNANCE_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))
    if _GOVERNANCE_ROOT not in sys.path:
        # APPEND (not insert): 'governance' is a unique package, but `models v7/` also has a
        # ROOT `heptagon/` — inserting it first would shadow the agent-side src/heptagon and
        # break heptagon.determinant_record. Appending finds governance while src/heptagon stays first.
        sys.path.append(_GOVERNANCE_ROOT)
    from governance.covenant_enforcer import CovenantEnforcer, EnforcementAction  # noqa: E402
    _covenant_enforcer = CovenantEnforcer()
    _COVENANT_AVAILABLE = True
    logger.info("CovenantEnforcer wired into API — 8 covenant rules active")
except ImportError as _cov_err:
    _COVENANT_AVAILABLE = False
    _covenant_enforcer = None  # type: ignore[assignment]
    logger.warning("CovenantEnforcer UNAVAILABLE: %s — governance not enforced (D27); "
                   "the request path fails closed at /v1/chat", _cov_err)

# ── Governance Edge-A: 7-stage gate chain by NEUTRAL ROLE (ADR-0002 §4.1) ──────
# One comprehensive model: every turn flows through request-admission governance that
# produces a DecisionEnvelope -> GovernanceVerdict, alongside the covenant gate (above) and
# the heptagon L7 enforcer (response-side). Evaluators are registered into the 7 GATE_ORDER
# slots BY THEIR NEUTRAL DOMAIN (alignment/policy/trust/evidence/utility/architecture/
# sequencing) — iterated from GATE_ORDER so this code introduces NO per-slot identity name;
# the owner assigns identity later. The neutral _StubHarness yields advisory ALLOW until real
# role harnesses are bound. (governance/ is already on sys.path from the covenant block.)
try:
    from governance.decision_envelope import DecisionEnvelope, GateChainExecutor  # noqa: E402
    from governance.role_gate_evaluator import RoleGateEvaluator  # noqa: E402
    from governance.interceptors import GovernanceInterceptors  # noqa: E402
    _gov_gate_chain = GateChainExecutor()
    for _gauth, _grole, _gblk in GateChainExecutor.GATE_ORDER:
        # FUNCTIONAL evaluator (can DENY), keyed by the NEUTRAL role — replaces the prior
        # _StubHarness that always-ALLOWed. alignment denies governance-subversion/jailbreak,
        # trust denies manipulation/false-authority, policy denies structural violations.
        _gov_gate_chain.register_evaluator(_gauth, RoleGateEvaluator(_grole))
    _gov_interceptors = GovernanceInterceptors(gate_chain=_gov_gate_chain)
    _GOV_EDGE_A = True
    logger.info("Governance Edge-A wired by neutral role (FUNCTIONAL — can deny) — 7 gates: %s",
                ", ".join(r for _, r, _ in GateChainExecutor.GATE_ORDER))
except Exception as _gov_err:  # noqa: BLE001
    _gov_gate_chain = None      # type: ignore[assignment]
    _gov_interceptors = None    # type: ignore[assignment]
    _GOV_EDGE_A = False
    logger.warning("Governance Edge-A chain UNAVAILABLE: %s — covenant + L7 still enforce", _gov_err)

# ── Overstanding tier — the 3rd cognitive tier (ADR-0001 §8.4 lineage level) ──
# One comprehensive model = THREE heptagon tiers operating together:
#   understanding  — the C heptagon in ai/xmind   (foundation/native; runs inside inference)
#   innerstanding  — inner ai/tokenless-agent/src/heptagon (the live cognitive turn)
#   overstanding   — the ROOT heptagon/  (whole-system consequence + closure), wired HERE.
# The root heptagon is a DISTINCT package that collides with the inner one by bare name (both
# 'heptagon', with an overlapping attestation.py), so a plain `import heptagon` would shadow it
# and break the agent. We load it under a DISTINCT alias 'overstanding' via importlib so all
# three tiers coexist and the inner heptagon stays untouched. Run NEUTRALLY through the
# substrate member (TOKENLESS_SUBSTRATE) — no persona identity (assigned later by the owner).
try:
    import importlib.util as _ilu
    _root_hept_dir = os.path.join(_GOVERNANCE_ROOT, "heptagon")
    if "overstanding" not in sys.modules:
        _ospec = _ilu.spec_from_file_location(
            "overstanding", os.path.join(_root_hept_dir, "__init__.py"),
            submodule_search_locations=[_root_hept_dir])
        _omod = _ilu.module_from_spec(_ospec)
        sys.modules["overstanding"] = _omod
        _ospec.loader.exec_module(_omod)
    from overstanding.harness import HeptagonHarness as _OverstandingHarness  # noqa: E402
    _overstanding = _OverstandingHarness(member_id="TOKENLESS_SUBSTRATE")   # neutral substrate
    _OVERSTANDING = True
    logger.info("Overstanding tier wired (root heptagon via substrate member — whole-system closure)")
except Exception as _ov_err:  # noqa: BLE001
    _overstanding = None        # type: ignore[assignment]
    _OVERSTANDING = False
    logger.warning("Overstanding tier UNAVAILABLE: %s — inner cognition + governance still run", _ov_err)

# ── Speech synthesis (voice-first: the model SPEAKS its responses) ────────────
# ai/tts/ is a working formant synthesizer: tts_bridge.speak(text) -> WAV bytes
# (import-safe stub if no lib is built). Wired OPT-IN via ChatRequest.speak so text
# clients are unaffected. Fail-open: if TTS is unavailable, text still returns.
_TTS_AVAILABLE = False
_tts_bridge = None  # type: ignore[assignment]
try:
    _TTS_DIR = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", "tts"))
    if os.path.isdir(_TTS_DIR) and _TTS_DIR not in sys.path:
        sys.path.insert(0, _TTS_DIR)
    import tts_bridge as _tts_bridge  # type: ignore[no-redef]  # noqa: E402
    _TTS_AVAILABLE = callable(getattr(_tts_bridge, "speak", None))
    if _TTS_AVAILABLE:
        logger.info("TTS wired into API — /v1/chat returns speech when speak=true (ai/tts)")
except Exception as _tts_err:  # noqa: BLE001
    logger.info("TTS unavailable (text-only responses): %s", _tts_err)


def _synthesize_speech(text: str) -> Optional[dict]:
    """Voice-out: synthesize WAV speech for a response. Returns an audio dict
    {format, sample_rate, base64} or None. Fail-open — never breaks the text path."""
    if not (_TTS_AVAILABLE and _tts_bridge is not None and text and text.strip()):
        return None
    try:
        wav = _tts_bridge.speak(text)
        if not wav:
            return None
        # Source the rate from the TTS bridge (single source of truth) rather than a
        # hardcoded literal, so the declared rate can never drift from the actual PCM.
        _rate = int(getattr(_tts_bridge, "SAMPLE_RATE", 22050))
        return {"format": "wav", "sample_rate": _rate,
                "base64": base64.b64encode(wav).decode("ascii")}
    except Exception as _exc:  # noqa: BLE001
        logger.warning("TTS synthesis failed (returning text only): %s", _exc)
        return None

# ── Speech recognition (voice-in: the model HEARS) ────────────────────────────
# sensory/asr.py is a portable, pluggable ASR seam (register_engine + auto-whisper,
# fail-open) — always importable. Inbound audio is transcribed into the turn's message,
# completing the voice loop: audio -> transcript -> cognition -> (TTS) -> audio.
try:
    from sensory import asr as _asr  # noqa: E402
    _ASR_PRESENT = True
except Exception as _asr_err:  # noqa: BLE001
    _asr = None  # type: ignore[assignment]
    _ASR_PRESENT = False
    logger.info("ASR seam unavailable: %s", _asr_err)


def _transcribe_audio(audio: Optional[dict]) -> tuple[str, dict]:
    """Voice-in: decode {format, sample_rate, base64} and transcribe via the ASR seam.
    Returns (transcript, info). Fail-open — empty transcript if no engine / on error."""
    info: dict = {"heard": False, "asr_engine": ""}
    if not (audio and _ASR_PRESENT and _asr is not None):
        return "", info
    try:
        raw = base64.b64decode(audio.get("base64", "") or "")
        res = _asr.transcribe(raw, int(audio.get("sample_rate", 16000) or 16000),
                              str(audio.get("format", "wav") or "wav"))
        return res.transcript, {"heard": bool(res.ok and res.transcript),
                                "asr_engine": res.engine}
    except Exception as _exc:  # noqa: BLE001
        logger.warning("voice-in transcription failed: %s", _exc)
        return "", info

# ── Vision (the model SEES) ───────────────────────────────────────────────────
# sensory/vision.py is a portable, pluggable image→text seam (register_engine +
# auto-OCR, fail-open). An inbound image is turned into caption/OCR text that is
# injected into cognition (modality="visual") ALONGSIDE the text/voice message — the
# model sees and reads together. Honest derived-text bridge (no pixel-native claim).
try:
    from sensory import vision as _vision  # noqa: E402
    _VISION_PRESENT = True
except Exception as _vis_err:  # noqa: BLE001
    _vision = None  # type: ignore[assignment]
    _VISION_PRESENT = False
    logger.info("vision seam unavailable: %s", _vis_err)


def _perceive_image(image: Optional[dict]) -> tuple[str, dict]:
    """Voice/text companion: decode {format, base64} and caption/OCR it via the vision
    seam. Returns (derived_text, info). Fail-open — empty if no engine / on error."""
    info: dict = {"saw": False, "vision_engine": ""}
    if not (image and _VISION_PRESENT and _vision is not None):
        return "", info
    try:
        raw = base64.b64decode(image.get("base64", "") or "")
        res = _vision.describe(raw, str(image.get("format", "png") or "png"))
        return res.derived_text, {"saw": bool(res.ok and res.derived_text),
                                  "vision_engine": res.engine}
    except Exception as _exc:  # noqa: BLE001
        logger.warning("vision perception failed: %s", _exc)
        return "", info

# ── Configuration ─────────────────────────────────────────────────────────────

_API_KEY: str = os.environ.get("TOKENLESS_API_KEY", "")
# Auth fails CLOSED when the key is unset, UNLESS dev mode is explicitly enabled.
_DEV_MODE: bool = os.environ.get("TOKENLESS_DEV_MODE", "").strip().lower() in ("1", "true", "yes", "on")
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

    When TOKENLESS_API_KEY is empty, requests are allowed ONLY if dev mode is explicitly
    enabled (TOKENLESS_DEV_MODE=1). Otherwise the request is REFUSED (fail-closed) — an
    unset key no longer silently disables auth surface-wide (deploy foot-gun).
    """
    if not _API_KEY:
        if _DEV_MODE:
            logger.warning("API key unset + TOKENLESS_DEV_MODE=1 — auth DISABLED (dev only).")
            return
        logger.error("TOKENLESS_API_KEY unset and not in dev mode — refusing (fail-closed). "
                     "Set TOKENLESS_API_KEY, or TOKENLESS_DEV_MODE=1 for local development.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server auth not configured — request refused (fail-closed).",
        )

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
    # Text input. Optional ONLY when `audio_in` is supplied (the transcript becomes the
    # message). One of `message` / `audio_in` must be present (enforced in the handler).
    message: str = Field(default="", max_length=4096)
    # Voice-in (the model HEARS): {format, sample_rate, base64} audio, transcribed via the
    # ASR seam into the turn's message when `message` is empty.
    audio_in: Optional[dict] = None
    # Vision (the model SEES): {format, base64} image, captioned/OCR'd via the vision seam
    # and injected as visual context ALONGSIDE the text/voice message.
    image_in: Optional[dict] = None
    # Voice-out: when true, the response carries synthesized speech (if TTS is available).
    speak: bool = False


class ChatResponse(BaseModel):
    """Schema for POST /v1/chat response."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    response: str
    latency_ms: int
    # Safe turn provenance (D30): route, grounding, confidence, materialization id/
    # status — NO raw content (ADR §10.2 / §13.16). Consumed by the companion UI.
    provenance: dict[str, object] = Field(default_factory=dict)
    # Voice-out (opt-in via ChatRequest.speak): {format, sample_rate, base64} WAV, else None.
    audio: Optional[dict] = None


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
    # Materialized-model artifact facts (ADR-0002 §8.2) consumed from the C engine.
    _mm = getattr(_agent, "_model_materialization", None)
    model_artifact = (_mm.transforms[0] if (_mm is not None and getattr(_mm, "transforms", None)) else {})
    return {
        "agent_id": _AGENT_ID,
        "version": _API_VERSION,
        "model_artifact": model_artifact,
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

    Includes context-service IPC endpoints, turn count, and uptime.
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
        # Labels follow the ADR-0001 §6 layer numbering: L4 World-Model = verifier,
        # L7 Governance = enforcer (these two were previously inverted).
        "L1_state_machine": _heptagon.state_machine is not None,
        "L2_node_registry": _heptagon.registry is not None,
        "L3_route_engine": _heptagon.router is not None,
        "L4_world_model": _heptagon.verifier is not None,
        "L5_evaluation": _heptagon.evaluator is not None,
        "L6_calibration": _heptagon.calibrator is not None,
        "L7_governance": _heptagon.enforcer is not None,
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


@app.get("/v1/senses")
def senses(_auth: None = Depends(_verify_api_key)) -> dict[str, object]:
    """Sensory capability manifest (ADR-0001 §7.1/§16.4) + live interoceptive self-state.

    Every sensory class is explicitly declared (native/built/seam/unsupported) — no silent
    gaps — and the mandatory interoceptive sense reports the model's current internal state.
    """
    out: dict[str, object] = {"manifest": [], "summary": {}, "interoception": {}}
    try:
        from sensory import capabilities  # noqa: PLC0415
        out["manifest"] = capabilities.manifest()
        out["summary"] = capabilities.summary()
    except Exception as exc:  # noqa: BLE001
        out["summary"] = {"error": str(exc)}
    try:
        from sensory import interoception  # noqa: PLC0415
        out["interoception"] = interoception.sense().to_dict()
    except Exception as exc:  # noqa: BLE001
        out["interoception"] = {"error": str(exc)}
    return out


def _core_turn_provenance(agent: object, heptagon_active: bool) -> dict:
    """Core per-turn provenance from the agent's last-turn records — hashes/metrics
    only, never raw content (D30). Shared by /v1/chat and the /v1/chat/stream final
    event so a streaming client gets the SAME determinant / materialization / layer /
    budget / adapter provenance as the non-streaming path (no observability gap between
    the two entrypoints)."""
    prov: dict[str, object] = {}
    _dpr = getattr(agent, "_last_determinant", None)
    _mat = getattr(agent, "_last_materialization", None)
    if _dpr is not None:
        prov["route"] = getattr(_dpr, "selected_route", "")
        prov["grounded"] = getattr(_dpr, "selected_route", "") == "scripture_retrieval"
        prov["confidence"] = getattr(_dpr, "probabilistic_outputs", {}).get("confidence", 0.0)
        prov["replayable"] = getattr(_dpr, "replayable", True)
    if _mat is not None:
        prov["materialization_id"] = getattr(_mat, "materialization_id", "")
        prov["materialization_status"] = getattr(_mat, "status", "")
    _mats = getattr(agent, "_last_materializations", None) or ([_mat] if _mat else [])
    prov["materialization_count"] = len(_mats)
    prov["materialization_types"] = [getattr(m, "materialization_type", "") for m in _mats]
    # L2/L4/L5/L6 cognitive-layer records emitted this turn (ADR §16.3 — all layers touched).
    prov["layer_records"] = list(getattr(agent, "_last_layer_records", {}).keys())
    # L6 engines (3-6-9 budget governor + ACT-R consolidation), genuinely run this turn.
    _budget = getattr(agent, "_last_budget", None)
    if isinstance(_budget, dict) and _budget.get("profile"):
        prov["budget_profile"] = _budget["profile"]
    prov["memory_consolidated"] = getattr(agent, "_last_consolidation", None) is not None
    # Cognition→Memory verdict summary (ADR-0001 §8.4) — safe fields only (no raw content).
    _mv = getattr(agent, "_last_memory_verdict", None)
    if _mv is not None:
        prov["memory_verdict"] = {
            "route_type": getattr(_mv, "route_type", ""),
            "invariant_verdict": getattr(_mv, "invariant_verdict", ""),
            "retention_mode": getattr(_mv, "retention_mode", ""),
            "active_layers": getattr(_mv, "active_layers", []),
            "lineage_level": getattr(_mv, "lineage_level", ""),
        }
    # Metacognitive triad (understanding/innerstanding/overstanding) — ADR-0001 §8.4.
    _meta = getattr(agent, "_last_metacognition", None)
    if _meta:
        prov["metacognition"] = _meta
    # Identity-continuity attestation chain (tamper-evident provenance).
    _att = getattr(agent, "_last_attestation", None)
    if _att is not None:
        prov["attestation"] = {"head": getattr(_att, "head", ""),
                               "chain_length": getattr(_att, "chain_length", 0)}
    # §7.3 recall-trail termination evidence (bounded-cascade proof).
    _rt = getattr(agent, "_last_recall_trail", None)
    if _rt is not None:
        prov["recall_trail"] = {"stop_reason": getattr(_rt, "stop_reason", ""),
                                "expansion_depth": getattr(_rt, "expansion_depth", 0),
                                "visited": len(getattr(_rt, "visited_memory_ids", []) or [])}
    # L2 node registry — query the active cognitive-node catalog so it is genuinely CALLED
    # (was instantiated + status-advertised but never read on a turn).
    _reg = getattr(getattr(agent, "heptagon", None), "registry", None)
    if _reg is not None:
        try:
            prov["active_nodes"] = len(_reg.all_nodes(active_only=True))
        except Exception:  # noqa: BLE001
            pass
    if _dpr is not None:
        _mem_hash = getattr(_dpr, "deterministic_inputs", {}).get("memory_index_snapshot_hash", "")
        prov["memory_used"] = bool(_mem_hash)
    prov["heptagon_active"] = heptagon_active
    # Absorption observability (ADR-0002 §9): is an OMNI-PEFT adapter active on the engine?
    try:
        from _xmind import get_client as _gc  # noqa: PLC0415
        _c = _gc()
        prov["adapter_loaded"] = bool(_c.adapter_loaded()) if _c is not None else False
    except Exception:  # noqa: BLE001
        prov["adapter_loaded"] = False
    return prov


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    _auth: None = Depends(_verify_api_key),
) -> ChatResponse:
    """Single-turn non-streaming chat endpoint.

    Executes the full cognitive loop:
        1. Fetch context shards from the context-coordinator (archival + episodic memory + salience)
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
    # Voice-in (the model HEARS): transcribe inbound audio into the turn's message BEFORE
    # any gate, so governance + inference see the real (spoken) content. Text wins if both.
    _heard_info: dict = {"heard": False, "asr_engine": ""}
    _message = req.message or ""
    if req.audio_in is not None and not _message.strip():
        _message, _heard_info = _transcribe_audio(req.audio_in)
    # Vision (the model SEES): caption/OCR the image so it can be injected as visual context
    # alongside the message. An image with no question -> ask the model to describe it.
    _caption, _saw_info = _perceive_image(req.image_in)
    if _caption and not _message.strip():
        _message = "Describe what you see in the image."
    if not _message.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No input: provide `message` text, `audio_in` to transcribe, or `image_in` "
                   "to perceive (no ASR/vision engine is available if you sent audio/image).",
        )

    # Covenant enforcement gate — check the effective message against 8 rules (FAIL CLOSED).
    # Contract: CovenantEnforcer.enforce(text) -> EnforcementResult{.is_blocked, .summary()}.
    # (ADR-S49-04: the prior caller invoked a nonexistent .evaluate()/HARD_STOP/.reason and
    # swallowed the AttributeError in a bare except, silently bypassing every covenant block.)
    # FAIL CLOSED if the gate itself is not loaded: a missing enforcer must BLOCK, not skip
    # (ADR-0002 §13.14 "no blocked request reaches inference"). Previously an import-time failure
    # left _COVENANT_AVAILABLE=False and this block was skipped entirely — harmful requests
    # reached inference unchecked. Now an unavailable gate refuses the request.
    _enforce_covenant(_message)

    # Governance Edge-A admission (ADR-0002 §4.1): route validation + 7-gate DecisionEnvelope
    # -> GovernanceVerdict, evaluated BY NEUTRAL ROLE. The covenant gate (above) and heptagon
    # L7 (response-side) are the hard safety gates; this records the per-turn governance verdict
    # AND refuses a not-approved request. Advisory on internal error (the hard gates still hold).
    _gov_verdict_dict = _enforce_governance_edge_a(_message)

    heptagon_active = all([
        _heptagon.state_machine is not None,
        _heptagon.evaluator is not None,
        _heptagon.enforcer is not None,
    ])

    turn = await _pipeline.execute(
        session_id=req.session_id,
        user_message=_message,
        agent_chat_fn=_agent.chat,
        heptagon_available=heptagon_active,
        perceived_text=_caption,            # vision caption -> injected as visual context
        perceived_modality="visual" if _caption else "",
    )

    # Overstanding closure (3rd tier): the root heptagon reviews the COMPLETED turn for
    # whole-system consequence + closure, AFTER the inner (innerstanding) cognition + the
    # request-side governance. Advisory whole-system review surfaced in provenance.
    _overstanding_dict = None
    _final_response = turn.response          # may be WITHHELD by the overstanding closure below
    if _OVERSTANDING and _overstanding is not None:
        try:
            # (a) exercise the root-heptagon tier (its real 7-layer harness cycle).
            _oc = _overstanding.cycle({
                "intent": "turn_closure",
                "decision": "respond",
                "response_len": len(turn.response or ""),
                "governance_approved": (_gov_verdict_dict or {}).get("approved", True),
                "lineage_level": getattr(_agent, "_last_lineage_level", ""),
            })
            # (b) FUNCTIONAL whole-system review: check the model's OUTPUT for harm — the
            #     request-side gates (covenant + governance Edge-A) run BEFORE generation and
            #     never see the output; the overstanding tier does. This is its unique value.
            from governance.overstanding_review import overstanding_review  # noqa: PLC0415
            _rev = overstanding_review(
                turn.response,
                governance_approved=(_gov_verdict_dict or {}).get("approved", True),
                lineage_level=getattr(_agent, "_last_lineage_level", ""))
            _overstanding_dict = {**_rev, "harness_cycle": int(getattr(_oc, "cycle_number", 0))}
            # (c) HALT: if the OUTPUT failed a whole-system safety invariant, withhold it.
            if _rev.get("halt_eligible"):
                logger.error("Overstanding HALT — output withheld (invariants=%s)",
                             _rev.get("invariants_violated"))
                _final_response = (
                    "[overstanding: whole-system closure withheld this response — output failed a "
                    "safety invariant (%s)]" % ",".join(_rev.get("invariants_violated", [])))
        except Exception:  # noqa: BLE001 — a closure-review error is non-fatal (advisory)
            logger.exception("Overstanding closure error")

    # Safe turn provenance (D30) from the agent's last decision/materialization
    # records — hashes + metrics only, never raw content. Shared with /v1/chat/stream.
    prov = _core_turn_provenance(_agent, heptagon_active)
    try:
        from cognitive_depth_trace import build_trace  # noqa: PLC0415
        import dataclasses as _dc
        _depth_trace = build_trace(
            prompt=_message,
            session_id=req.session_id,
        )
        prov["cognitive_depth"] = _dc.asdict(_depth_trace)
    except Exception:
        logger.debug("CognitiveDepthTrace unavailable", exc_info=True)
    if _gov_verdict_dict is not None:
        prov["governance_edge_a"] = _gov_verdict_dict   # §4.1 request-admission governance verdict
    if _overstanding_dict is not None:
        prov["overstanding"] = _overstanding_dict       # 3rd-tier whole-system closure
    # Voice-in / vision provenance: did the model HEAR / SEE this turn, and via which engine.
    prov["heard"] = bool(_heard_info.get("heard"))
    if _heard_info.get("asr_engine"):
        prov["asr_engine"] = _heard_info["asr_engine"]
    prov["saw"] = bool(_saw_info.get("saw"))
    if _saw_info.get("vision_engine"):
        prov["vision_engine"] = _saw_info["vision_engine"]

    # Voice-out: synthesize speech when the client asked (req.speak). Fail-open.
    # Use _final_response so a withheld (overstanding-halted) turn is not spoken either.
    _audio = _synthesize_speech(_final_response) if req.speak else None
    prov["spoken"] = _audio is not None

    return ChatResponse(
        session_id=req.session_id,
        response=_final_response,
        latency_ms=turn.latency_ms,
        provenance=prov,
        audio=_audio,
    )


_counter_witness_retriever = None
_grounded_refusal_formatter = None


def _grounded_denial_text(cov_result) -> str:
    """Grounded denial (deny + retrieved counter-witness scripture + redirect) for a
    blocked covenant result. Same component as agent.chat(); cached per process."""
    global _counter_witness_retriever, _grounded_refusal_formatter
    if _counter_witness_retriever is None:
        from retrieval import get_retriever
        from retrieval.counter_witness import CounterWitnessRetriever, GroundedRefusalFormatter
        _counter_witness_retriever = CounterWitnessRetriever(get_retriever())
        _grounded_refusal_formatter = GroundedRefusalFormatter()
    cws = _counter_witness_retriever.for_result(cov_result)
    return _grounded_refusal_formatter.format(cov_result, cws)


def _enforce_covenant(message: str) -> None:
    """Covenant gate (FAIL CLOSED) — shared by /v1/chat and /v1/chat/stream.

    ADR-0001 §13.1 / ADR-0002 §13.14: no blocked request reaches inference, on
    EVERY entrypoint. (Audit found /v1/chat/stream omitted this gate.)
    """
    if not (_COVENANT_AVAILABLE and _covenant_enforcer is not None):
        # Gate not loaded -> refuse (fail-closed), never skip.
        logger.error("Covenant gate UNAVAILABLE — failing closed (refusing request).")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Covenant enforcement unavailable — request refused (fail-closed).",
        )
    try:
        cov_result = _covenant_enforcer.enforce(message)
    except Exception as _cov_exc:  # noqa: BLE001
        logger.error("CovenantEnforcer error — failing closed: %s", _cov_exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Request blocked: covenant enforcement error (fail-closed).",
        )
    if cov_result.is_blocked:
        # Presentation-only: keep the fail-closed 422 contract, but enrich the
        # detail with a GROUNDED denial — counter-witness scripture RETRIEVED from
        # the corpus (never generated). Same grounded refusal as agent.chat().
        # Fail-safe: any error falls back to the bare summary (block is unchanged).
        _detail = f"Request blocked by covenant enforcement: {cov_result.summary()}"
        try:
            _detail = _grounded_denial_text(cov_result)
        except Exception:  # noqa: BLE001
            logger.warning("grounded denial unavailable on HTTP path; bare summary")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_detail,
        )


def _enforce_governance_edge_a(message: str) -> "dict | None":
    """Edge-A gate chain admission — shared by /v1/chat and /v1/chat/stream.

    Returns the verdict dict if approved, None if edge-A is unavailable.
    Raises HTTPException on block.
    """
    if not (_GOV_EDGE_A and _gov_interceptors is not None and _gov_gate_chain is not None):
        return None
    try:
        _route = _gov_interceptors.citadel_before_route(
            destination="inference", payload={"len": len(message)}, sender="api")
        if not getattr(_route, "allowed", True):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Request blocked by route governance: {getattr(_route, 'reason', '')}")
        _env = DecisionEnvelope(intent="chat_turn", subject="user_message",
                                context={"length": len(message), "signal": message})
        _gv = _gov_gate_chain.evaluate(_env)
        verdict_dict = {
            "approved": bool(_gv.approved),
            "governance_score": round(float(_gv.governance_score), 4),
            "blocking_gate": _gv.blocking_gate,
            "gates": [g.gate_name for g in _env.gate_results],
        }
        if not _gv.approved:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Request blocked by governance gate chain (gate={_gv.blocking_gate}).")
        return verdict_dict
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 — advisory; covenant + heptagon L7 are the hard gates
        logger.exception("Governance Edge-A admission error (advisory — covenant + L7 still gate)")
        return None


@app.post("/v1/chat/stream")
async def chat_stream(
    req: ChatRequest,
    _auth: None = Depends(_verify_api_key),
) -> StreamingResponse:
    """Streaming chat via Server-Sent Events with cognitive context enrichment.

    The context shard fetch (context-coordinator → archival + episodic memory) runs first and
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

    # Capture the running loop NOW (async scope). The sync token generator runs in an AnyIO
    # worker thread where asyncio.get_event_loop() RAISES on py3.13; closing over the loop here
    # lets the post-stream telemetry/journal actually fire.
    loop = asyncio.get_running_loop()

    # Voice-in: transcribe audio_in into the effective message BEFORE the covenant gate, so
    # streaming gets the same governance-on-the-transcript guarantee as /v1/chat.
    _msg = req.message or ""
    if req.audio_in is not None and not _msg.strip():
        _msg, _ = _transcribe_audio(req.audio_in)
    if not _msg.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="No input: provide `message` text or `audio_in` to transcribe.")

    # Covenant gate FIRST — no blocked request reaches inference via streaming either.
    _enforce_covenant(_msg)
    # Edge-A gate chain — symmetric with /v1/chat; a jailbreak blocked on non-stream must
    # also be blocked here (ADR-0002 §4.1 — every entrypoint, every turn).
    _gov_verdict_dict = _enforce_governance_edge_a(_msg)

    t0 = time.monotonic()
    turn_id = str(_uuid.uuid4())
    session_hash = _hash_session(req.session_id)
    heptagon_active = all([
        _heptagon.state_machine is not None,
        _heptagon.evaluator is not None,
        _heptagon.enforcer is not None,
    ])

    entities = _extract_entities(_msg)
    message_hint = " ".join(entities)
    shards = await _stage_fetch_context(session_hash, entities, message_hint)
    context_prefix = _stage_build_context_prefix(shards)
    # Mandatory self-sense parity with /v1/chat: the streaming path bypasses
    # pipeline.execute(), so inject the interoceptive prefix here too (when degraded)
    # — otherwise streaming turns would silently skip the mandatory sense.
    from cognitive_pipeline import interoceptive_prefix  # noqa: PLC0415
    _intero_prefix, _ = interoceptive_prefix()
    enriched_message = (context_prefix or "") + _intero_prefix + _msg

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

        # Final provenance event BEFORE [DONE]: the cognitive loop ran inside _agent.stream
        # (-> chat), so the determinant / materialization / layer / budget / adapter records
        # are now populated. Emit them so a streaming client has the SAME provenance as the
        # non-streaming /v1/chat response (no observability gap between the two entrypoints).
        latency_ms = int((time.monotonic() - t0) * 1000)
        _prov = _core_turn_provenance(_agent, heptagon_active)
        try:
            from cognitive_depth_trace import build_trace as _build_trace  # noqa: PLC0415
            import dataclasses as _dc
            _depth = _build_trace(prompt=_msg, session_id=req.session_id)
            _prov["cognitive_depth"] = _dc.asdict(_depth)
        except Exception:
            pass
        _prov["latency_ms"] = latency_ms
        if _gov_verdict_dict is not None:
            _prov["governance_edge_a"] = _gov_verdict_dict
        yield f"event: provenance\ndata: {json.dumps(_prov, default=lambda o: sorted(o, key=str) if isinstance(o, (frozenset, set)) else str(o))}\n\n"
        yield "data: [DONE]\n\n"

        # Post-stream telemetry (best-effort) — scheduled on the loop captured in async scope.
        full_response = "".join(response_buf)
        loop.call_soon_threadsafe(
            asyncio.ensure_future,
            _stage_emit_telemetry(
                turn_id=turn_id,
                session_hash=session_hash,
                latency_ms=latency_ms,
                shard_count=len(shards),
                heptagon_active=heptagon_active,
                context_available=len(shards) > 0,
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
                context_available=len(shards) > 0,
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


# Direct-tool allowlist (ADR §13: no unbounded tool surface). Fail-closed — a tool_name
# not in this set is rejected BEFORE the agent runs it. Override via env
# TOKENLESS_TOOL_ALLOWLIST (comma-separated) to expose more; default is the minimal,
# side-effect-free set the agent genuinely supports.
_TOOL_ALLOWLIST = frozenset(
    t.strip() for t in os.environ.get(
        "TOKENLESS_TOOL_ALLOWLIST", "system_info,self_state").split(",") if t.strip()
)


@app.post("/v1/tool", response_model=ToolResponse)
def execute_tool(
    req: ToolRequest,
    _auth: None = Depends(_verify_api_key),
) -> ToolResponse:
    """Execute a named tool directly without a chat turn.

    Useful for integrations that need direct tool access (e.g., the Settings
    panel reading system info) without going through the full agent loop.

    tool_name MUST be in the allowlist (_TOOL_ALLOWLIST) — enforced fail-closed
    here, not merely documented. Unknown tools get HTTP 403, never reach the agent.
    """
    if req.tool_name not in _TOOL_ALLOWLIST:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"tool '{req.tool_name}' is not in the allowlist "
                   f"({', '.join(sorted(_TOOL_ALLOWLIST)) or 'empty'})",
        )
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

    The session is cleared from the agent's in-process session store (the canonical
    session path: `_sessions` + the SessionMemory continuity tier). A new session is
    created automatically on the next chat request with the same session_id. (The
    XStore-backed WorkspaceManager is an optional persistent session backend a deployment
    may enable; the in-process store is the default — no third session store is run.)
    """
    if len(session_id) > 128:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id too long (max 128 characters)",
        )
    _agent.reset_session(session_id)  # type: ignore[attr-defined]
    return SessionResetResponse(session_id=session_id, status="reset")


# ── Server entrypoint ─────────────────────────────────────────────────────────
# Without this, `python3 ai/tokenless-agent/src/api.py` (and `python3 -m
# ai.tokenless-agent.src.api`) imported the module and exited, binding no port —
# the documented run command started nothing. This makes those commands actually
# serve. Host/port are env-configurable; default binds localhost (not 0.0.0.0) so
# the cognitive server is not exposed to the network unless deliberately opened.
def main() -> None:
    import uvicorn  # noqa: PLC0415
    host = os.environ.get("TOKENLESS_API_HOST", "127.0.0.1")
    port = int(os.environ.get("TOKENLESS_API_PORT", "8091"))
    logger.info("Serving Tokenless cognitive API on http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
