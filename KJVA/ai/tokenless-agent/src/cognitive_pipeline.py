"""ai/tokenless-agent/src/cognitive_pipeline.py
CognitivePipeline — end-to-end cognitive loop bridge for the /v1/chat endpoint.

SPDX-License-Identifier: LicenseRef-Proprietary
Copyright (c) 2026 Tokenless Models Project

This module wires the full cognitive loop that was previously disconnected:

    User → API → [this pipeline] → context-coordinator (context shards)
         → archival + episodic memory → RT4 salience → Heptagon L1-L7
         → TokenlessAgent (XMIND inference)
         → Telemetry → EventJournal → Response

Design rationale:
    The XENOS kernel runs inside QEMU inside the `kernel` Docker container. It
    cannot reach the context-service network directly. The `tokenless-agent` container
    sits on the shared Docker network and CAN reach all context-service daemons by their
    Docker-DNS service names (the context-coordinator (:18600), SoulManager (:18610), etc.).

    This class is therefore the sole bridge. It is instantiated once per process
    (singleton via module-level _pipeline) and called from FastAPI route handlers.

Network contracts:
    context-coordinator IPC  — 4-byte BE length + UTF-8 JSON (length-prefixed framing)
    Telemetryd IPC      — newline-delimited JSON: {"op":"report","name":K,"value":V}\n
    EventJournal IPC    — 4-byte BE length + UTF-8 JSON, msg_type="APPEND"

All connections carry a hard timeout.  Failures are logged and the pipeline
continues — no context-service dependency may crash or block a /v1/chat response.

PII policy:
    Session IDs are hashed with SHA-256 before they leave this process.
    Raw user messages never enter context-service IPC payloads.
    Only anonymised system descriptors and token counts reach the network.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import struct
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

# §12 Level-1 perception (Phase 4): sensory evidence envelope + router. Guarded so the
# pipeline degrades gracefully if the sensory package is unavailable (never breaks chat).
try:
    from sensory.evidence import build_evidence_envelope as _build_evidence
    from sensory.router import SensoryRouter as _SensoryRouter
    _SENSORY_AVAILABLE = True
    _sensory_router = _SensoryRouter()
except Exception:  # pragma: no cover
    _SENSORY_AVAILABLE = False
    _build_evidence = None
    _sensory_router = None

logger = logging.getLogger("tokenless.cognitive_pipeline")

# ---------------------------------------------------------------------------
# Configuration (from Docker Compose environment)
# ---------------------------------------------------------------------------

# Context-coordinator service (neutral; specific service name is deployment config).
_CTX_HOST: str = os.environ.get("CONTEXT_COORD_HOST", "127.0.0.1")
_CTX_PORT: int = int(os.environ.get("CONTEXT_COORD_PORT", "18600"))
_CTX_AGENT: str = os.environ.get("CONTEXT_COORD_AGENT", "context-coordinator")

# SoulManager (:18610) — the Memory Continuity System component (ADR-0002 §3). This is the
# real component name, NOT an alias to neutralize (ADR-0002 §0.2 STOP rule: do not rename the
# active taxonomy; §14: do not rename the architecture).
_SOULMGR_HOST: str = os.environ.get("SOULMGR_HOST", "127.0.0.1")
_SOULMGR_PORT: int = int(os.environ.get("SOULMGR_PORT", "18610"))

_JOURNAL_HOST: str = os.environ.get("JOURNAL_HOST", os.environ.get("EVENTJOURNAL_HOST", "127.0.0.1"))
_JOURNAL_PORT: int = int(os.environ.get("JOURNAL_PORT", os.environ.get("EVENTJOURNAL_PORT", "18611")))
_JOURNAL_AGENT: str = os.environ.get("JOURNAL_AGENT", "journal")

_TELEMETRY_HOST: str = os.environ.get("TELEMETRY_HOST", "127.0.0.1")
_TELEMETRY_PORT: int = int(os.environ.get("TELEMETRY_PORT", "18614"))

# Per-operation timeout — must not approach the /v1/chat P99 SLA of 10s
_IPC_TIMEOUT: float = float(os.environ.get("COGNITIVE_IPC_TIMEOUT_S", os.environ.get("COUNCIL_IPC_TIMEOUT_S", "2.0")))

# Maximum context shards to request (law of seven)
_MAX_SHARDS: int = 7
# Minimum RT4 salience to include a shard in the prompt prefix
_SHARD_THRESHOLD: float = 0.3

# Maximum characters from context shards injected into the prompt prefix.
# Keeps token budget under 512 tokens (≈2048 chars) for the XMIND context window.
_MAX_CONTEXT_CHARS: int = 1800


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass
class ContextShard:
    """A single retrieved memory shard from archival or episodic memory."""
    id: str
    content: str
    salience: float
    source: str  # "archival" | "episodic"


@dataclass
class CognitiveTurn:
    """Full pipeline result for one /v1/chat turn."""
    session_hash: str          # SHA-256 of session_id — never the raw ID
    shards: List[ContextShard] = field(default_factory=list)
    context_prefix: str = ""   # Injected before user message
    response: str = ""
    latency_ms: int = 0
    heptagon_available: bool = False
    context_available: bool = False
    turn_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # §12 Level-1 perception (Phase 4): sensory evidence-envelope provenance (optional).
    evidence_salience: Optional[float] = None
    sensory_scope: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# IPC primitives
# ---------------------------------------------------------------------------

async def _lp_call(
    host: str,
    port: int,
    message: dict,
    timeout: float = _IPC_TIMEOUT,
) -> Optional[dict]:
    """Length-prefixed JSON IPC call (4-byte BE length + UTF-8 JSON).

    Matches the context-service TCP framing used by the context services.
    Returns None on any failure — callers must treat None as a silent skip.
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        payload_bytes = json.dumps(message).encode("utf-8")
        writer.write(struct.pack(">I", len(payload_bytes)) + payload_bytes)
        await writer.drain()

        hdr = await asyncio.wait_for(reader.readexactly(4), timeout=timeout)
        resp_len = struct.unpack(">I", hdr)[0]
        if resp_len == 0 or resp_len > 131072:
            logger.warning(
                "cognitive_pipeline: invalid response length %d from %s:%d",
                resp_len, host, port,
            )
            writer.close()
            await writer.wait_closed()
            return None

        body = await asyncio.wait_for(reader.readexactly(resp_len), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return json.loads(body.decode("utf-8"))

    except (OSError, asyncio.TimeoutError, json.JSONDecodeError, struct.error) as exc:
        logger.debug(
            "cognitive_pipeline: IPC %s:%d failed: %s",
            host, port, exc,
        )
        return None


async def _nl_send(
    host: str,
    port: int,
    message: dict,
    timeout: float = _IPC_TIMEOUT,
) -> None:
    """Newline-delimited JSON fire-and-forget send (telemetryd protocol).

    Does not wait for a response. Failures are silently swallowed.
    """
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        writer.write((json.dumps(message) + "\n").encode("utf-8"))
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    except (OSError, asyncio.TimeoutError) as exc:
        logger.debug(
            "cognitive_pipeline: telemetry send to %s:%d failed: %s",
            host, port, exc,
        )


# ---------------------------------------------------------------------------
# PII helpers
# ---------------------------------------------------------------------------

def _hash_session(session_id: str) -> str:
    """Return the first 16 hex chars of SHA-256(session_id).

    This is the only form in which session identity leaves this process.
    The raw session_id never enters context-service IPC payloads.
    """
    return hashlib.sha256(session_id.encode()).hexdigest()[:16]


def _extract_entities(message: str, max_entities: int = 5) -> List[str]:
    """Derive entity tokens from a user message for context retrieval.

    Heuristic: split on whitespace, keep tokens longer than 4 characters,
    strip punctuation, deduplicate, take first N. This avoids sending the
    full user message over IPC while still anchoring context retrieval to
    the topical content of the query.

    Complexity: O(n) where n = word count. Acceptable for chat inputs.
    """
    import re
    tokens: List[str] = []
    seen: set[str] = set()
    for word in re.split(r"\s+", message):
        token = re.sub(r"[^a-zA-Z0-9]", "", word).lower()
        if len(token) > 4 and token not in seen:
            tokens.append(token)
            seen.add(token)
        if len(tokens) >= max_entities:
            break
    return tokens


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

async def _stage_fetch_context(
    session_hash: str,
    entities: List[str],
    message_hint: str,
    memory_scope: Optional[List[str]] = None,   # D18: route-derived recall scope
) -> List[ContextShard]:
    """Stage 1: Request context shards from the context-coordinator (which routes to archival + episodic memory).

    Sends a context_shard_request to the context-coordinator (default :18600). the context-coordinator
    dispatches parallel queries to archival memory and SoulManager (episodic memory),
    applies the RT4 salience filter, and returns the top-7 shards.

    The `message_hint` is a very short (max 80 char) descriptor — NOT the raw
    user message. It guides relevance scoring without exposing user content.
    """
    if not entities:
        return []

    request = {
        "msg_type": "context_shard_request",
        "source_agent": "tokenless-agent",
        "target_agent": _CTX_AGENT,
        "payload": {
            "entities": entities,
            "threshold": _SHARD_THRESHOLD,
            "max_shards": _MAX_SHARDS,
            "session_id": session_hash,  # anonymised
            "context": message_hint[:80],
            "memory_scope": list(memory_scope or []),   # D18: scope the recall
        },
        "msg_id": str(uuid.uuid4()),
        "timestamp": time.time(),
    }

    response = await _lp_call(_CTX_HOST, _CTX_PORT, request)
    if response is None:
        logger.debug("cognitive_pipeline: context-coordinator unreachable — no context shards")
        return []

    payload = response.get("payload", {})
    raw_shards = payload.get("shards", [])

    shards: List[ContextShard] = []
    for s in raw_shards:
        content = str(s.get("content", "")).strip()
        if not content:
            continue
        shards.append(ContextShard(
            id=str(s.get("id", str(uuid.uuid4()))),
            content=content,
            salience=float(s.get("salience", 0.0)),
            source=str(s.get("source", "unknown")),
        ))

    logger.debug(
        "cognitive_pipeline: fetched %d context shards (session_hash=%s)",
        len(shards), session_hash,
    )
    return shards


def interoceptive_prefix() -> "tuple[str, bool]":
    """The MANDATORY self-sense (ADR-0001 §12), as an injectable prefix.

    Senses the model's own internal state and returns ``(prefix, degraded)``:
    a ``[perception:interoception] ...`` prefix ONLY when the state is degraded
    (CPU/memory pressure, low battery, thermal), else ``("", False)``. Sensing runs
    every call (the mandatory sense is genuinely CALLED per turn); the prefix is
    injected only when salient, so nominal turns stay clean. Shared by the pipeline
    (non-streaming) and the streaming entrypoint so both inject the same self-state —
    no asymmetry. Never raises (self-sensing must not break inference)."""
    try:
        from sensory import interoception  # noqa: PLC0415
        st = interoception.sense()
        degraded = bool(getattr(st, "degraded", False))
        if degraded:
            return f"[perception:interoception] {interoception.summary(st)}\n\n", True
        return "", False
    except Exception:  # noqa: BLE001
        return "", False


def _stage_build_context_prefix(shards: List[ContextShard]) -> str:
    """Stage 2: Build the context prefix injected before the user message.

    Concatenates shard content ordered by salience (highest first).
    Hard-clamps to _MAX_CONTEXT_CHARS to stay within the XMIND token budget.
    Returns an empty string when no shards are available.
    """
    if not shards:
        return ""

    sorted_shards = sorted(shards, key=lambda s: s.salience, reverse=True)
    lines: List[str] = ["[Context from memory]"]
    total_chars = len(lines[0])

    for shard in sorted_shards:
        line = f"- [{shard.source}] {shard.content}"
        if total_chars + len(line) + 1 > _MAX_CONTEXT_CHARS:
            break
        lines.append(line)
        total_chars += len(line) + 1

    if len(lines) == 1:
        # Only the header — no shards fit
        return ""

    lines.append("")  # blank separator before the user message
    return "\n".join(lines)


async def _stage_emit_telemetry(
    turn_id: str,
    session_hash: str,
    latency_ms: int,
    shard_count: int,
    heptagon_active: bool,
    context_available: bool,
) -> None:
    """Stage 4: Emit inference telemetry to telemetryd (port 18614).

    Uses the newline-delimited JSON protocol. Fire-and-forget — never blocks
    the response path. Metrics are anonymous: no session IDs, no message content.
    """
    metrics = [
        {"op": "report", "name": "tokenless.chat.latency_ms", "value": latency_ms},
        {"op": "report", "name": "tokenless.chat.shard_count", "value": shard_count},
        {"op": "report", "name": "tokenless.chat.heptagon_active", "value": int(heptagon_active)},
        {"op": "report", "name": "tokenless.chat.context_available", "value": int(context_available)},
        {"op": "report", "name": "tokenless.chat.request_count", "value": 1},
    ]
    tasks = [_nl_send(_TELEMETRY_HOST, _TELEMETRY_PORT, m) for m in metrics]
    await asyncio.gather(*tasks, return_exceptions=True)


async def _stage_emit_journal_event(
    turn_id: str,
    session_hash: str,
    latency_ms: int,
    shard_count: int,
    response_length: int,
    context_available: bool,
) -> None:
    """Stage 5: Append a structured event to the journal service (port 18611).

    Uses the context-service network length-prefixed JSON framing.
    The journal record contains NO user message content and NO raw session ID.
    It records system-level observability data only: turn_id, timing, shard counts,
    response length, and pipeline health flags.
    """
    event = {
        "msg_type": "APPEND",
        "source_agent": "tokenless-agent",
        "target_agent": _JOURNAL_AGENT,
        "payload": {
            "event_type": "tokenless.chat.turn_complete",
            "task_id": turn_id,
            "session_hash": session_hash,
            "latency_ms": latency_ms,
            "shard_count": shard_count,
            "response_length": response_length,
            "context_available": context_available,
            "pipeline": "cognitive_loop_v1",
        },
        "msg_id": str(uuid.uuid4()),
        "timestamp": time.time(),
    }
    # Best-effort — do not await the result or block on failure
    await _lp_call(_JOURNAL_HOST, _JOURNAL_PORT, event)


# ---------------------------------------------------------------------------
# CognitivePipeline
# ---------------------------------------------------------------------------

class CognitivePipeline:
    """End-to-end cognitive loop orchestrator for /v1/chat.

    Lifecycle of a single chat turn:
        1. Extract entity tokens from the user message (local, O(n))
        2. Fetch context shards from context-coordinator → archival + episodic memory → RT4
        3. Build context prefix from ranked shards
        4. Pass enriched message to TokenlessAgent (XMIND inference + Heptagon)
        5. Emit telemetry metrics to telemetryd (fire-and-forget)
        6. Emit structured event to the journal service (fire-and-forget)
        7. Return the CognitiveTurn result

    This class is a singleton. Instantiate once at module load time and pass
    the execute() coroutine result into the API response builder.

    Thread/async safety:
        execute() is a coroutine and must be awaited. FastAPI's async endpoint
        support handles this correctly. The underlying _lp_call helpers each
        open and close their own TCP connections — no shared state, no locks
        required at this layer.
    """

    def __init__(self) -> None:
        self._turn_count: int = 0
        self._start_time: float = time.time()
        logger.info(
            "CognitivePipeline initialised — context-coord=%s:%d eventjournal=%s:%d "
            "telemetry=%s:%d",
            _CTX_HOST, _CTX_PORT,
            _JOURNAL_HOST, _JOURNAL_PORT,
            _TELEMETRY_HOST, _TELEMETRY_PORT,
        )

    async def execute(
        self,
        session_id: str,
        user_message: str,
        agent_chat_fn: "Callable[[str, str], str]",  # type: ignore[name-defined]
        heptagon_available: bool = False,
        perceived_text: str = "",
        perceived_modality: str = "",
    ) -> CognitiveTurn:
        """Execute the full cognitive pipeline for one chat turn.

        Parameters
        ----------
        session_id : str
            Raw session ID from the API request. Hashed before use in IPC.
        user_message : str
            The user's message. Used locally for entity extraction only.
            Never transmitted over IPC payloads.
        agent_chat_fn : callable
            The TokenlessAgent.chat(session_id, enriched_message) callable.
            Called synchronously in a thread pool executor to avoid blocking
            the asyncio event loop.
        heptagon_available : bool
            Whether the Heptagon layer is active in the current agent instance.

        Returns
        -------
        CognitiveTurn
            Contains the response, all pipeline metrics, and the context shards
            that were injected.
        """
        t0 = time.monotonic()
        self._turn_count += 1
        turn_id = str(uuid.uuid4())
        session_hash = _hash_session(session_id)

        # --- Stage 1: Entity extraction (local, no I/O) ---
        entities = _extract_entities(user_message)

        # --- §12 Level-1: sensory evidence envelope (Phase 4, additive provenance) ---
        # Computes salience + sensory scope for telemetry/routing; never breaks the response path.
        evidence_salience: Optional[float] = None
        sensory_scope: List[str] = []
        memory_scope: List[str] = []
        perception_prefix: str = ""     # non-text sense -> LM-readable context (injection seam)
        if _SENSORY_AVAILABLE:
            try:
                _env = _build_evidence(user_message, session_id=session_id)
                evidence_salience = _env.salience
                _route = _sensory_router.route(_env)
                sensory_scope = _route.sensory_scope
                memory_scope = list(getattr(_route, "memory_scope", []) or [])  # D18
                # Perception -> cognition: a non-text sense (image caption/OCR, audio
                # transcript, sensor summary) carries its content in derived_text. Fold it
                # into what the model reads so perception is no longer thrown away. A
                # modality adapter (e.g. vision) may pass perceived_text directly; otherwise
                # the envelope's own derived_text is used. Plain text => "" => no-op.
                _dt = (perceived_text or getattr(_env, "derived_text", "") or "").strip()
                _mod = perceived_modality or _env.modality
                if _dt:
                    perception_prefix = f"[perception:{_mod}] {_dt}\n\n"
                # D20 evidence gate: a high-risk envelope is logged before context/inference
                # (covenant hard-block runs earlier at api.py; this is the evidence-integrity tap).
                if getattr(_env, "risk_class", "standard") not in ("standard", "low"):
                    logger.warning("L1 evidence gate: elevated risk_class=%s (evidence_id=%s)",
                                   _env.risk_class, getattr(_env, "evidence_id", ""))
            except Exception:  # noqa: BLE001 — perception must never break inference
                pass

        # A modality adapter's perception (e.g. a vision caption) must reach the model even
        # if the sensory evidence/router path is unavailable or errored above.
        if perceived_text and perceived_text.strip() and not perception_prefix:
            perception_prefix = f"[perception:{perceived_modality or 'visual'}] {perceived_text.strip()}\n\n"

        # Interoception (the MANDATORY self-sense, ADR-0001 §12 perception boundary): sense the
        # model's OWN internal state every turn, and fold it into cognition ONLY when degraded.
        # Shared with /v1/chat/stream via interoceptive_prefix() so BOTH entrypoints inject the
        # mandatory sense (no streaming/non-streaming asymmetry). Self-state precedes external
        # perception. Self-sensing never breaks inference.
        _intero_prefix, self._last_intero_degraded = interoceptive_prefix()
        if _intero_prefix:
            perception_prefix = _intero_prefix + perception_prefix

        # --- Stage 2: Fetch context shards from context-service (scoped by memory_scope, D18) ---
        # Derive a short topical hint without exposing the full message.
        message_hint = " ".join(entities)
        shards = await _stage_fetch_context(session_hash, entities, message_hint,
                                            memory_scope=memory_scope)
        context_available = len(shards) > 0   # was '... or True' (constant-True bug) — now real,
                                              # matching the streaming path's len(shards)>0

        # --- Stage 3: Build context prefix ---
        context_prefix = _stage_build_context_prefix(shards)

        # --- Stage 4: Enriched inference via TokenlessAgent ---
        # Prepend retrieved context + any non-text perception to the user message.
        # The agent's PII sanitisation layer runs inside agent_chat_fn. Order:
        # context shards, then perceived (non-text) evidence, then the user's words.
        enriched_message = (context_prefix or "") + perception_prefix + user_message

        # Run the synchronous agent call in the default thread pool executor
        # so we do not block the event loop during XMIND inference.
        loop = asyncio.get_event_loop()
        response_text = await loop.run_in_executor(
            None, agent_chat_fn, session_id, enriched_message
        )

        latency_ms = int((time.monotonic() - t0) * 1000)

        turn = CognitiveTurn(
            session_hash=session_hash,
            shards=shards,
            context_prefix=context_prefix,
            response=response_text,
            latency_ms=latency_ms,
            heptagon_available=heptagon_available,
            context_available=context_available,
            turn_id=turn_id,
            evidence_salience=evidence_salience,
            sensory_scope=sensory_scope,
        )

        # --- Stages 5 & 6: Telemetry + Journal (fire-and-forget, parallel) ---
        # These must never block or raise into the response path.
        asyncio.ensure_future(
            _stage_emit_telemetry(
                turn_id=turn_id,
                session_hash=session_hash,
                latency_ms=latency_ms,
                shard_count=len(shards),
                heptagon_active=heptagon_available,
                context_available=context_available,
            )
        )
        asyncio.ensure_future(
            _stage_emit_journal_event(
                turn_id=turn_id,
                session_hash=session_hash,
                latency_ms=latency_ms,
                shard_count=len(shards),
                response_length=len(response_text),
                context_available=context_available,
            )
        )

        logger.info(
            "cognitive_pipeline: turn=%s session=%s shards=%d latency=%dms",
            turn_id, session_hash, len(shards), latency_ms,
        )
        return turn

    def get_stats(self) -> dict:
        """Return pipeline health metrics for the /v1/health or /v1/info endpoint."""
        return {
            "turn_count": self._turn_count,
            "uptime_s": time.time() - self._start_time,
            "context_coord_endpoint": f"{_CTX_HOST}:{_CTX_PORT}",
            "telemetry_endpoint": f"{_TELEMETRY_HOST}:{_TELEMETRY_PORT}",
            "journal_endpoint": f"{_JOURNAL_HOST}:{_JOURNAL_PORT}",
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_pipeline_instance: Optional[CognitivePipeline] = None


def get_pipeline() -> CognitivePipeline:
    """Return or create the module-level CognitivePipeline singleton.

    Thread-safe for read access after first initialisation. The first call
    constructs the instance (no I/O at construction time).
    """
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = CognitivePipeline()
    return _pipeline_instance
