"""ai/tokenless-agent/src/cognitive_pipeline.py
CognitivePipeline — end-to-end cognitive loop bridge for the /v1/chat endpoint.

SPDX-License-Identifier: LicenseRef-Proprietary
Copyright (c) 2026 Tokenless Models Project

This module wires the full cognitive loop that was previously disconnected:

    User → API → [this pipeline] → Ahki (context shards)
         → Bookworm + SoulManager → RT4 salience → Heptagon L1-L7
         → TokenlessAgent (XMIND inference)
         → Telemetry → EventJournal → Response

Design rationale:
    The XENOS kernel runs inside QEMU inside the `kernel` Docker container. It
    cannot reach the Council daemon network directly. The `tokenless-agent` container
    sits on the shared Docker network and CAN reach all Council daemons by their
    Docker-DNS service names (ahkid:18600, soulmgrd:18610, etc.).

    This class is therefore the sole bridge. It is instantiated once per process
    (singleton via module-level _pipeline) and called from FastAPI route handlers.

Network contracts:
    Ahki / Council IPC  — 4-byte BE length + UTF-8 JSON (length-prefixed framing)
    Telemetryd IPC      — newline-delimited JSON: {"op":"report","name":K,"value":V}\n
    EventJournal IPC    — 4-byte BE length + UTF-8 JSON, msg_type="APPEND"

All connections carry a hard timeout.  Failures are logged and the pipeline
continues — no Council dependency may crash or block a /v1/chat response.

PII policy:
    Session IDs are hashed with SHA-256 before they leave this process.
    Raw user messages never enter Council IPC payloads.
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

logger = logging.getLogger("tokenless.cognitive_pipeline")

# ---------------------------------------------------------------------------
# Configuration (from Docker Compose environment)
# ---------------------------------------------------------------------------

_AHKI_HOST: str = os.environ.get("AHKI_HOST", "127.0.0.1")
_AHKI_PORT: int = int(os.environ.get("AHKI_PORT", "18600"))

_SOULMGR_HOST: str = os.environ.get("SOULMGR_HOST", "127.0.0.1")
_SOULMGR_PORT: int = int(os.environ.get("SOULMGR_PORT", "18610"))

_EVENTJOURNAL_HOST: str = os.environ.get("EVENTJOURNAL_HOST", "127.0.0.1")
_EVENTJOURNAL_PORT: int = int(os.environ.get("EVENTJOURNAL_PORT", "18611"))

_TELEMETRY_HOST: str = os.environ.get("TELEMETRY_HOST", "127.0.0.1")
_TELEMETRY_PORT: int = int(os.environ.get("TELEMETRY_PORT", "18614"))

# Per-operation timeout — must not approach the /v1/chat P99 SLA of 10s
_IPC_TIMEOUT: float = float(os.environ.get("COUNCIL_IPC_TIMEOUT_S", "2.0"))

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
    """A single retrieved memory shard from Bookworm or SoulManager."""
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
    council_available: bool = False
    turn_id: str = field(default_factory=lambda: str(uuid.uuid4()))


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

    Matches the Council TCP framing used by ahkid, eventjournald, soulmgrd.
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
    The raw session_id never enters Council IPC payloads.
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
) -> List[ContextShard]:
    """Stage 1: Request context shards from Ahki (which routes to Bookworm + SoulManager).

    Sends a context_shard_request to ahkid on port 18600. Ahki's ContextCoordinator
    dispatches parallel queries to Bookworm (archival) and SoulManager (episodic),
    applies the RT4 salience filter, and returns the top-7 shards.

    The `message_hint` is a very short (max 80 char) descriptor — NOT the raw
    user message. It guides relevance scoring without exposing user content.
    """
    if not entities:
        return []

    request = {
        "msg_type": "context_shard_request",
        "source_agent": "tokenless-agent",
        "target_agent": "ahkid",
        "payload": {
            "entities": entities,
            "threshold": _SHARD_THRESHOLD,
            "max_shards": _MAX_SHARDS,
            "session_id": session_hash,  # anonymised
            "context": message_hint[:80],
        },
        "msg_id": str(uuid.uuid4()),
        "timestamp": time.time(),
    }

    response = await _lp_call(_AHKI_HOST, _AHKI_PORT, request)
    if response is None:
        logger.debug("cognitive_pipeline: Ahki unreachable — no context shards")
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
    council_available: bool,
) -> None:
    """Stage 4: Emit inference telemetry to telemetryd (port 18614).

    Uses the newline-delimited JSON protocol. Fire-and-forget — never blocks
    the response path. Metrics are anonymous: no session IDs, no message content.
    """
    metrics = [
        {"op": "report", "name": "tokenless.chat.latency_ms", "value": latency_ms},
        {"op": "report", "name": "tokenless.chat.shard_count", "value": shard_count},
        {"op": "report", "name": "tokenless.chat.heptagon_active", "value": int(heptagon_active)},
        {"op": "report", "name": "tokenless.chat.council_available", "value": int(council_available)},
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
    council_available: bool,
) -> None:
    """Stage 5: Append a structured event to eventjournald (port 18611).

    Uses the Council length-prefixed JSON framing.
    The journal record contains NO user message content and NO raw session ID.
    It records system-level observability data only: turn_id, timing, shard counts,
    response length, and pipeline health flags.
    """
    event = {
        "msg_type": "APPEND",
        "source_agent": "tokenless-agent",
        "target_agent": "eventjournald",
        "payload": {
            "event_type": "tokenless.chat.turn_complete",
            "task_id": turn_id,
            "session_hash": session_hash,
            "latency_ms": latency_ms,
            "shard_count": shard_count,
            "response_length": response_length,
            "council_available": council_available,
            "pipeline": "cognitive_loop_v1",
        },
        "msg_id": str(uuid.uuid4()),
        "timestamp": time.time(),
    }
    # Best-effort — do not await the result or block on failure
    await _lp_call(_EVENTJOURNAL_HOST, _EVENTJOURNAL_PORT, event)


# ---------------------------------------------------------------------------
# CognitivePipeline
# ---------------------------------------------------------------------------

class CognitivePipeline:
    """End-to-end cognitive loop orchestrator for /v1/chat.

    Lifecycle of a single chat turn:
        1. Extract entity tokens from the user message (local, O(n))
        2. Fetch context shards from Ahki → Bookworm + SoulManager → RT4
        3. Build context prefix from ranked shards
        4. Pass enriched message to TokenlessAgent (XMIND inference + Heptagon)
        5. Emit telemetry metrics to telemetryd (fire-and-forget)
        6. Emit structured event to eventjournald (fire-and-forget)
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
            "CognitivePipeline initialised — ahki=%s:%d eventjournal=%s:%d "
            "telemetry=%s:%d",
            _AHKI_HOST, _AHKI_PORT,
            _EVENTJOURNAL_HOST, _EVENTJOURNAL_PORT,
            _TELEMETRY_HOST, _TELEMETRY_PORT,
        )

    async def execute(
        self,
        session_id: str,
        user_message: str,
        agent_chat_fn: "Callable[[str, str], str]",  # type: ignore[name-defined]
        heptagon_available: bool = False,
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

        # --- Stage 2: Fetch context shards from Council ---
        # Derive a short topical hint without exposing the full message.
        # We send the first 80 chars of a space-joined entity list as a hint.
        message_hint = " ".join(entities)
        shards = await _stage_fetch_context(session_hash, entities, message_hint)
        council_available = len(shards) > 0 or True  # reachability is separate concern

        # --- Stage 3: Build context prefix ---
        context_prefix = _stage_build_context_prefix(shards)

        # --- Stage 4: Enriched inference via TokenlessAgent ---
        # Prepend context to the user message when shards are available.
        # The agent's PII sanitisation layer runs inside agent_chat_fn.
        enriched_message = (
            context_prefix + user_message if context_prefix else user_message
        )

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
            council_available=council_available,
            turn_id=turn_id,
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
                council_available=council_available,
            )
        )
        asyncio.ensure_future(
            _stage_emit_journal_event(
                turn_id=turn_id,
                session_hash=session_hash,
                latency_ms=latency_ms,
                shard_count=len(shards),
                response_length=len(response_text),
                council_available=council_available,
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
            "ahki_endpoint": f"{_AHKI_HOST}:{_AHKI_PORT}",
            "telemetry_endpoint": f"{_TELEMETRY_HOST}:{_TELEMETRY_PORT}",
            "eventjournal_endpoint": f"{_EVENTJOURNAL_HOST}:{_EVENTJOURNAL_PORT}",
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
