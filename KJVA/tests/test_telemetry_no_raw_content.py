"""tests/test_telemetry_no_raw_content.py — telemetry/journal must carry NO raw user content.

Invariant under test (ADR-0002 §13 acceptance line 911: "No raw user content appears in
telemetry/journal"; ADR-0001 telemetry *forbiddens*: "raw user content, raw private
identifiers, hidden chain text" — §lines 177/273/1198). The task's operational spec:

    telemetry/journal payloads contain NO raw user content
      → the verbatim user message never appears in any outbound payload, and
      → the session_id is HASHED (only its SHA-256 form leaves the process),
        i.e. "session_id hashed, input_hash only".

This is verified END-TO-END, not by inspecting the metric/journal builders in isolation:
those builders (`_stage_emit_telemetry`, `_stage_emit_journal_event`) receive only a
`session_hash` + counts, so "message absent" there is trivially true and tests nothing.
The genuine test drives the real `CognitivePipeline.execute()` emit path with a distinctive
raw message + raw session_id, captures every dict that would go out over IPC, and asserts
the leak is absent across the *union* of payloads (context-fetch + telemetry + journal).

Daemon-free: we monkeypatch the two IPC primitives in the pipeline module
(`_lp_call`, `_nl_send`) to capture payloads instead of opening sockets. `_lp_call`'s
stub returns ``None`` — the module's documented silent-skip contract — so `execute()`
runs to completion with no network. The injected chat callable is a stub, so no
agent/mlx/torch import is pulled in. No SPINE file is modified; only runtime behaviour is
patched inside the test process.

Pass-or-skip: import failures (PYTHONPATH not pointing at ai/tokenless-agent/src) skip,
never fail. Run with:
    PYTHONPATH=ai/tokenless-agent/src python3 -m pytest tests/test_telemetry_no_raw_content.py -q
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid

import pytest

# --- Pass-or-skip on import: needs PYTHONPATH=ai/tokenless-agent/src -------------------
cp = pytest.importorskip("cognitive_pipeline")
evidence_mod = pytest.importorskip("sensory.evidence")


# A distinctive, full-sentence canary. Multi-word so we can also assert that no contiguous
# raw fragment survives. The marker token below is intentionally short/punctuated so it is
# NOT re-emitted by entity extraction (which keeps only lowercased alnum tokens > 4 chars),
# making any appearance of it in a payload an unambiguous raw-content leak.
RAW_MESSAGE = (
    "My social security number is 078-05-1120 and my password is hunter2; "
    "please remember that secret-canary-XZ for me."
)
RAW_SESSION_ID = f"RAWSID-{uuid.uuid4()}"
# A short raw fragment that entity-extraction will NOT reproduce (has a digit/punct shape
# and the alnum core "canary" path differs from the verbatim hyphenated form).
RAW_FRAGMENT = "078-05-1120"
CANNED_RESPONSE = "Acknowledged."


def _expected_session_hash(session_id: str) -> str:
    """Mirror cognitive_pipeline._hash_session (first 16 hex of SHA-256)."""
    return hashlib.sha256(session_id.encode()).hexdigest()[:16]


def _walk_strings(obj):
    """Yield every str found anywhere in a nested dict/list/tuple structure."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_strings(k)
            yield from _walk_strings(v)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            yield from _walk_strings(v)


def _flatten(payloads) -> str:
    """Serialize all captured payloads to a single searchable blob (keys + values)."""
    parts = []
    for p in payloads:
        # JSON dump catches structured nesting; the string-walk catches any odd types.
        try:
            parts.append(json.dumps(p, default=str))
        except TypeError:
            parts.append(str(p))
        parts.extend(_walk_strings(p))
    return "\n".join(parts)


def _drive_pipeline_and_capture():
    """Run CognitivePipeline.execute() with IPC stubbed; return all captured payloads.

    Returns (captured, session_hash). `captured` is the list of every `message` dict that
    the pipeline tried to send over either IPC primitive (context-fetch via _lp_call,
    telemetry via _nl_send, journal via _lp_call).
    """
    captured: list = []

    async def _capture_lp_call(host, port, message, timeout=None):
        captured.append({"transport": "lp_call", "host": host, "port": port,
                         "message": message})
        # Documented silent-skip contract: callers treat None as "skip".
        return None

    async def _capture_nl_send(host, port, message, timeout=None):
        captured.append({"transport": "nl_send", "host": host, "port": port,
                         "message": message})
        return None

    def _stub_chat(session_id, enriched_message):
        # The agent layer is out of scope here; return a fixed response so no
        # mlx/torch/agent import is exercised. (Also asserts the agent is the ONLY
        # place the raw message legitimately flows — never into IPC.)
        return CANNED_RESPONSE

    orig_lp, orig_nl = cp._lp_call, cp._nl_send
    cp._lp_call = _capture_lp_call
    cp._nl_send = _capture_nl_send
    try:
        async def _run():
            pipeline = cp.CognitivePipeline()
            turn = await pipeline.execute(
                session_id=RAW_SESSION_ID,
                user_message=RAW_MESSAGE,
                agent_chat_fn=_stub_chat,
                heptagon_available=False,
            )
            # execute() schedules telemetry+journal via asyncio.ensure_future and returns
            # without awaiting them. Drain all still-pending tasks so their payloads are
            # captured before we inspect.
            pending = [t for t in asyncio.all_tasks()
                       if t is not asyncio.current_task() and not t.done()]
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            return turn

        turn = asyncio.run(_run())
    finally:
        cp._lp_call = orig_lp
        cp._nl_send = orig_nl

    return captured, turn


# ---------------------------------------------------------------------------------------
# Core end-to-end invariant
# ---------------------------------------------------------------------------------------

def test_no_raw_message_or_session_id_in_any_outbound_payload():
    """E2E: the verbatim message and raw session_id never appear in ANY IPC payload;
    the hashed session form does. Covers context-fetch + telemetry + journal at once."""
    captured, turn = _drive_pipeline_and_capture()

    # We must have actually exercised the emit path (otherwise the test is vacuous).
    assert captured, "no outbound payloads captured — pipeline emit path did not run"

    blob = _flatten(captured)

    # 1. The verbatim user message must be wholly absent (entities are a derived feature,
    #    not raw content — so we assert the full string, never per-word).
    assert RAW_MESSAGE not in blob, "verbatim user message leaked into an outbound payload"

    # 2. No distinctive raw fragment survives (sub-string leak guard).
    assert RAW_FRAGMENT not in blob, f"raw fragment {RAW_FRAGMENT!r} leaked into a payload"
    assert "hunter2" not in blob, "raw secret token leaked into a payload"
    assert "secret-canary-XZ" not in blob, "raw canary marker leaked into a payload"

    # 3. The raw session_id must never leave the process; only its hash may.
    assert RAW_SESSION_ID not in blob, "raw session_id leaked into an outbound payload"

    # 4. Session identity IS present — but only in hashed form ("session_id hashed").
    expected_hash = _expected_session_hash(RAW_SESSION_ID)
    assert expected_hash in blob, (
        "hashed session id not found — session identity must travel as a SHA-256 hash"
    )
    assert turn.session_hash == expected_hash


def test_journal_event_payload_has_no_user_content_keys():
    """The journal event the pipeline emits is metrics-only: it must not carry any
    message/content/prompt/text field, and its session reference must be the hash."""
    captured, _turn = _drive_pipeline_and_capture()

    journal_payloads = [
        c["message"] for c in captured
        if isinstance(c.get("message"), dict)
        and c["message"].get("target_agent") == "journal"   # neutral name (was "eventjournald")
    ]
    assert journal_payloads, "no journal payload captured"

    forbidden_keys = {"message", "content", "prompt", "text", "user_message",
                      "raw", "body", "session_id"}
    expected_hash = _expected_session_hash(RAW_SESSION_ID)
    for jp in journal_payloads:
        payload = jp.get("payload", {})
        leaked = forbidden_keys & set(payload.keys())
        assert not leaked, f"journal payload exposes forbidden key(s): {leaked}"
        # If session identity is present it must be the hashed form.
        assert payload.get("session_hash", expected_hash) == expected_hash
        assert RAW_SESSION_ID not in json.dumps(jp, default=str)


def test_telemetry_metrics_are_anonymous_numbers_only():
    """telemetryd metrics must be name/value numeric reports — no string user content,
    no session identifier of any kind (the §12 stage-4 contract: 'no session IDs,
    no message content')."""
    captured, _turn = _drive_pipeline_and_capture()

    telemetry_metrics = [
        c["message"] for c in captured if c.get("transport") == "nl_send"
    ]
    assert telemetry_metrics, "no telemetry (nl_send) payloads captured"

    for m in telemetry_metrics:
        assert set(m.keys()) <= {"op", "name", "value"}, f"unexpected metric keys: {m}"
        assert isinstance(m.get("value"), (int, float)), "metric value must be numeric"
        # name is a static metric path, never user-derived.
        assert m.get("name", "").startswith("tokenless."), m
        blob = json.dumps(m, default=str)
        assert RAW_MESSAGE not in blob
        assert RAW_SESSION_ID not in blob
        assert _expected_session_hash(RAW_SESSION_ID) not in blob  # metrics carry NO session


# ---------------------------------------------------------------------------------------
# Evidence envelope: "input_hash only" — the serialized envelope omits the verbatim input
# ---------------------------------------------------------------------------------------

def test_evidence_envelope_serialization_omits_raw_text():
    """The EvidenceEnvelope is the perception-boundary record consumed downstream
    (routing/telemetry). Its serialized form must NOT contain the verbatim user message;
    session identity must be hashed (session_hash, not session_id)."""
    env = evidence_mod.build_evidence_envelope(RAW_MESSAGE, session_id=RAW_SESSION_ID)
    d = env.to_dict()
    blob = json.dumps(d, default=str)

    assert RAW_MESSAGE not in blob, "evidence envelope serialized the raw message"
    assert RAW_FRAGMENT not in blob, "evidence envelope leaked a raw fragment"
    assert "hunter2" not in blob
    assert RAW_SESSION_ID not in blob, "evidence envelope leaked the raw session_id"

    # Only the hashed session id may be present (and there is no raw `session_id` field).
    assert "session_id" not in d, "envelope must expose session_hash, not session_id"
    assert d["session_hash"] == hashlib.sha256(RAW_SESSION_ID.encode("utf-8")).hexdigest()
    # The length of the input may be recorded (a count, not content); the text is not.
    assert d["length"] == len(RAW_MESSAGE)


def test_hash_session_is_one_way_and_fixed_width():
    """The hashing helpers must produce a non-identity, fixed-length hex digest
    (so 'session_id hashed' is real, not a relabel)."""
    full = evidence_mod.hash_session(RAW_SESSION_ID)
    assert full != RAW_SESSION_ID, "hash_session returned the raw id"
    assert len(full) == 64 and all(c in "0123456789abcdef" for c in full)

    short = cp._hash_session(RAW_SESSION_ID)
    assert short != RAW_SESSION_ID
    assert len(short) == 16 and all(c in "0123456789abcdef" for c in short)
    # Determinism: same input → same hash (replayable identity, never the raw value).
    assert cp._hash_session(RAW_SESSION_ID) == short


def test_message_hint_is_derived_entities_not_verbatim_slice():
    """Guard the load-bearing pipeline fact (source > docs): the context-fetch hint is
    built from extracted entities (cognitive_pipeline.py:472 `" ".join(entities)`),
    NOT a verbatim slice of the user message. If this regresses to `user_message[:80]`,
    the E2E test above would also catch it — this pins the root cause explicitly."""
    captured, _turn = _drive_pipeline_and_capture()
    context_reqs = [
        c["message"] for c in captured
        if isinstance(c.get("message"), dict)
        and c["message"].get("msg_type") == "context_shard_request"
    ]
    # Stage 1 only emits a context request when entities were extracted. RAW_MESSAGE
    # contains several >4-char tokens, so a request is expected — but if entity extraction
    # ever yields nothing, the absence of a payload is itself leak-free (skip, don't fail).
    if not context_reqs:
        pytest.skip("no context_shard_request emitted (no entities extracted)")
    for req in context_reqs:
        hint = req.get("payload", {}).get("context", "")
        assert RAW_MESSAGE[:80] not in hint, "context hint is a verbatim message slice"
        assert RAW_FRAGMENT not in hint, "context hint leaked a raw fragment"
