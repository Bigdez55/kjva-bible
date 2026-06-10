"""test_streaming_provenance.py — /v1/chat/stream emits a final provenance SSE event.

The streaming path previously ended at `data: [DONE]` with NO provenance, so a streaming
client got the model tokens but none of the determinant / materialization / layer / budget /
adapter records the non-streaming /v1/chat response carries. That was an observability gap
between the two entrypoints. This test pins the fix:

  * a `event: provenance` SSE frame is emitted BEFORE `[DONE]`,
  * its JSON payload carries the shared core-provenance keys (the same shape /v1/chat
    returns), proving the cognitive loop ran and its records reached the stream.

Run:  python3 -m pytest tests/test_streaming_provenance.py -q
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "ai" / "tokenless-agent" / "src"

# ── module-level SRC pin + root-heptagon eviction ─────────────────────────────
# Root heptagon/ has MEMBER_REGISTRY with persona keys. governance/interceptors.py
# does `from heptagon.registry import MEMBER_REGISTRY` at import time. If root
# heptagon is cached first (by an earlier test file or import chain),
# interceptors.py binds persona keys and citadel_before_route() rejects
# "inference" destination → HTTP 422 in streaming tests.
# Pinning src/ at position 0 and evicting root-origin entries prevents that.
_SRC_STR = str(_SRC)
if _SRC_STR in sys.path:
    sys.path.remove(_SRC_STR)
sys.path.insert(0, _SRC_STR)

for _key in list(sys.modules):
    if _key == "heptagon" or _key.startswith("heptagon."):
        _mod_file = getattr(sys.modules[_key], "__file__", "") or ""
        if "tokenless-agent" not in _mod_file:
            del sys.modules[_key]


def _run_stream(api) -> list[str]:
    """Open the stream AND drain it in ONE event loop. The streaming generator captures
    the running loop (for post-stream telemetry) via get_running_loop(); using a second
    asyncio.run() to drain would reference an already-closed loop. So both happen here."""
    async def _go() -> list[str]:
        req = api.ChatRequest(session_id="prov-stream", message="what is the status")
        resp = await api.chat_stream(req, _auth=None)
        chunks: list[str] = []
        async for piece in resp.body_iterator:
            chunks.append(piece if isinstance(piece, str) else piece.decode("utf-8"))
        return chunks

    return asyncio.run(_go())


@pytest.fixture(scope="module")
def stream_chunks():
    pytest.importorskip("fastapi", reason="FastAPI not installed — streaming-provenance test skipped")
    # Re-pin src/ and do a deep eviction: governance.interceptors + api may already
    # be cached from an earlier test file with root heptagon's persona MEMBER_REGISTRY.
    # Evicting them forces a fresh import that binds the correct empty-dict fallback.
    if _SRC_STR in sys.path:
        sys.path.remove(_SRC_STR)
    sys.path.insert(0, _SRC_STR)
    for _evict in list(sys.modules):
        if _evict == "heptagon" or _evict.startswith("heptagon."):
            _mf = getattr(sys.modules[_evict], "__file__", "") or ""
            if "tokenless-agent" not in _mf:
                del sys.modules[_evict]
        elif (
            _evict == "governance" or _evict.startswith("governance.")
            or _evict in ("api", "agent")
        ):
            del sys.modules[_evict]
    try:
        import api  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"api module unavailable: {exc}")
    # Confirm heptagon resolved to src/heptagon (no MEMBER_REGISTRY persona keys).
    import heptagon as _hept  # noqa: PLC0415
    assert "tokenless-agent" in (getattr(_hept, "__file__", "") or ""), (
        f"heptagon resolved to wrong package: {_hept.__file__!r}; "
        "expected ai/tokenless-agent/src/heptagon — root heptagon still cached"
    )

    class _PassResult:
        is_blocked = False

        def summary(self) -> str:
            return "ok"

    class _PassingEnforcer:
        def enforce(self, _text: str):
            return _PassResult()

    orig_available = api._COVENANT_AVAILABLE
    orig_enforcer = api._covenant_enforcer
    api._COVENANT_AVAILABLE = True
    api._covenant_enforcer = _PassingEnforcer()
    try:
        return _run_stream(api)
    finally:
        api._COVENANT_AVAILABLE = orig_available
        api._covenant_enforcer = orig_enforcer


def test_stream_emits_provenance_before_done(stream_chunks):
    joined = "".join(stream_chunks)
    assert "event: provenance" in joined, "stream did not emit a provenance SSE event"
    assert "[DONE]" in joined, "stream did not terminate with [DONE]"
    assert joined.index("event: provenance") < joined.index("[DONE]"), \
        "provenance event must come BEFORE [DONE]"


def test_streaming_injects_interoception_when_degraded():
    """Parity with /v1/chat: the streaming path bypasses pipeline.execute(), so it must
    still inject the MANDATORY interoceptive self-sense when degraded. Spy on what
    _agent.stream receives and assert the [perception:interoception] prefix is present."""
    pytest.importorskip("fastapi")
    if _SRC_STR in sys.path:
        sys.path.remove(_SRC_STR)
    sys.path.insert(0, _SRC_STR)
    for _evict in list(sys.modules):
        if _evict == "heptagon" or _evict.startswith("heptagon."):
            _mf = getattr(sys.modules[_evict], "__file__", "") or ""
            if "tokenless-agent" not in _mf:
                del sys.modules[_evict]
        elif (
            _evict == "governance" or _evict.startswith("governance.")
            or _evict in ("api", "agent")
        ):
            del sys.modules[_evict]
    try:
        import api  # noqa: PLC0415
        from sensory import interoception as _io  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"api/interoception unavailable: {exc}")

    class _PassResult:
        is_blocked = False

        def summary(self) -> str:
            return "ok"

    class _PassingEnforcer:
        def enforce(self, _text: str):
            return _PassResult()

    seen = {}

    def _spy_stream(session_id, enriched):
        seen["enriched"] = enriched
        yield "ok"

    st = _io.sense()
    st.degraded = True  # force degraded so the injection branch must fire
    orig_sense, orig_av, orig_enf = _io.sense, api._COVENANT_AVAILABLE, api._covenant_enforcer
    orig_stream = api._agent.stream
    _io.sense = lambda now=None: st
    api._COVENANT_AVAILABLE = True
    api._covenant_enforcer = _PassingEnforcer()
    api._agent.stream = _spy_stream
    try:
        async def _go():
            req = api.ChatRequest(session_id="intero-stream", message="status?")
            resp = await api.chat_stream(req, _auth=None)
            async for _ in resp.body_iterator:
                pass
        asyncio.run(_go())
    finally:
        _io.sense, api._COVENANT_AVAILABLE, api._covenant_enforcer = orig_sense, orig_av, orig_enf
        api._agent.stream = orig_stream

    assert "[perception:interoception]" in seen.get("enriched", ""), \
        "streaming path did not inject the mandatory self-sense when degraded"


def test_provenance_payload_has_core_keys(stream_chunks):
    # Find the provenance frame and parse its JSON data line.
    prov = None
    for chunk in stream_chunks:
        if "event: provenance" in chunk:
            for line in chunk.splitlines():
                if line.startswith("data: "):
                    prov = json.loads(line[len("data: "):])
            break
    assert prov is not None, "no parseable provenance data line found"
    # The shared core-provenance keys (same shape as /v1/chat).
    for key in ("layer_records", "heptagon_active", "materialization_count",
                "memory_consolidated", "adapter_loaded", "latency_ms"):
        assert key in prov, f"provenance missing core key: {key}"
    assert isinstance(prov["layer_records"], list)
