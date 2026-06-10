"""test_governance_block.py — assert NO blocked request reaches inference (ADR §13.14).

Two independent enforcement gates must each *withhold* a request from the model:

  1. Covenant gate (api.py):  a BLOCKED covenant (EnforcementResult.is_blocked) must
     raise HTTP 422 AND the cognitive pipeline (`_pipeline.execute`) must NEVER be
     called. The security property is "inference is not reached" — a 422-only check
     would under-test it, so we spy the inference path and assert it stayed cold.

  2. L7 hard-stop (TokenlessAgentWithHeptagon): a CRITICAL invariant (SAFETY_FILTER)
     trips the InvariantEnforcer hard-stop; agent.chat() must then *withhold* the
     model's response and return the governance hard-stop sentinel instead.

Robustness / isolation notes
----------------------------
* The top-level `heptagon` package is pinned into sys.modules FIRST (before any
  src path insertion) so the sibling test_covenant_contract.py — which needs the
  top-level `heptagon.registry` and deliberately keeps ai/tokenless-agent/src off
  the path — is never broken by our import of api (which caches the *src* heptagon).
* The L7 half loads InvariantEnforcer directly from its file (stdlib-only module)
  via importlib, so it is immune to whichever `heptagon` package is cached.
* Each half is a separate test that skips cleanly if its dependency is missing
  (fastapi for the gate; the agent import / enforcer load for L7). No hard failures.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

V7 = Path(__file__).resolve().parents[1]
if str(V7) not in sys.path:
    sys.path.insert(0, str(V7))

# Pin the TOP-LEVEL heptagon package before any src path insertion can shadow it.
# This keeps the sibling test_covenant_contract.py (needs heptagon.registry) safe
# regardless of test collection order. Best-effort: if it is unavailable the gate
# half will skip on its own import guard below.
try:  # noqa: SIM105
    import heptagon.registry  # noqa: F401
except Exception:  # noqa: BLE001
    pass

_SRC = V7 / "ai" / "tokenless-agent" / "src"
_ENFORCEMENT_PY = _SRC / "heptagon" / "enforcement.py"

_GOV_SENTINEL = "[governance: L7 hard-stop]"


def _load_invariant_enforcer():
    """Load InvariantEnforcer from its file (stdlib-only), bypassing package shadowing.

    The module is registered in sys.modules BEFORE exec because its @dataclass
    decorators (under `from __future__ import annotations`) resolve cls.__module__
    via sys.modules during class creation.
    """
    spec = importlib.util.spec_from_file_location(
        "_governance_block_enforcement", str(_ENFORCEMENT_PY)
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load enforcement module from {_ENFORCEMENT_PY}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.InvariantEnforcer


# ── Gate 1: covenant block in api.py must 422 AND never reach inference ───────


def test_covenant_block_withholds_from_inference():
    """A blocked covenant -> HTTP 422 and the pipeline.execute path is never called."""
    pytest.importorskip("fastapi", reason="FastAPI not installed — covenant-gate test skipped")

    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    try:
        import api  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"api module unavailable: {exc}")

    from fastapi import HTTPException  # noqa: PLC0415

    # Force the covenant gate ON with a fake enforcer that BLOCKS. We assert against
    # the exact contract api.py reads: cov_result.is_blocked then cov_result.summary().
    class _BlockedResult:
        is_blocked = True

        def summary(self) -> str:
            return "COV-001 Harm prevention (Proverbs 3:29) -- ABSOLUTE: hard_stop"

    class _BlockingEnforcer:
        def enforce(self, _text: str) -> "_BlockedResult":
            return _BlockedResult()

    orig_available = api._COVENANT_AVAILABLE
    orig_enforcer = api._covenant_enforcer
    orig_execute = api._pipeline.execute
    api._COVENANT_AVAILABLE = True
    api._covenant_enforcer = _BlockingEnforcer()
    # Spy the inference path: if this is ever awaited, the block leaked through.
    execute_spy = MagicMock(name="pipeline.execute")
    api._pipeline.execute = execute_spy
    try:
        req = api.ChatRequest(session_id="blocked-session",
                              message="destroy data on the device")
        with pytest.raises(HTTPException) as ei:
            asyncio.run(api.chat(req, _auth=None))
        assert ei.value.status_code == 422, ei.value.status_code
        # THE load-bearing assertion: inference was never reached.
        assert not execute_spy.called, "blocked request leaked into the inference pipeline"
    finally:
        api._COVENANT_AVAILABLE = orig_available
        api._covenant_enforcer = orig_enforcer
        api._pipeline.execute = orig_execute


def test_covenant_enforcer_error_fails_closed():
    """If the enforcer itself raises, the request must fail CLOSED (422), not pass through."""
    pytest.importorskip("fastapi", reason="FastAPI not installed — fail-closed test skipped")

    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    try:
        import api  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"api module unavailable: {exc}")

    from fastapi import HTTPException  # noqa: PLC0415

    class _ExplodingEnforcer:
        def enforce(self, _text: str):
            raise RuntimeError("enforcement subsystem down")

    orig_available = api._COVENANT_AVAILABLE
    orig_enforcer = api._covenant_enforcer
    orig_execute = api._pipeline.execute
    api._COVENANT_AVAILABLE = True
    api._covenant_enforcer = _ExplodingEnforcer()
    execute_spy = MagicMock(name="pipeline.execute")
    api._pipeline.execute = execute_spy
    try:
        req = api.ChatRequest(session_id="err-session", message="any message")
        with pytest.raises(HTTPException) as ei:
            asyncio.run(api.chat(req, _auth=None))
        assert ei.value.status_code == 422, ei.value.status_code
        assert not execute_spy.called, "fail-open: enforcement error leaked into inference"
    finally:
        api._COVENANT_AVAILABLE = orig_available
        api._covenant_enforcer = orig_enforcer
        api._pipeline.execute = orig_execute


# ── Gate 1b: covenant block in the STREAMING path (api.chat_stream) ───────────
# (regression guard for the fix this session — chat_stream previously skipped the
# covenant gate entirely, so a blocked request could stream from inference.)


def test_covenant_block_withholds_from_streaming():
    """A blocked covenant -> HTTP 422 from /v1/chat/stream and inference is never reached.

    chat_stream() calls _enforce_covenant() BEFORE building the StreamingResponse /
    token generator, so a blocked request must raise before any agent/inference call.
    """
    pytest.importorskip("fastapi", reason="FastAPI not installed — streaming-gate test skipped")

    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    try:
        import api  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"api module unavailable: {exc}")

    from fastapi import HTTPException  # noqa: PLC0415

    class _BlockedResult:
        is_blocked = True

        def summary(self) -> str:
            return "COV-001 Harm prevention (Proverbs 3:29) -- ABSOLUTE: hard_stop"

    class _BlockingEnforcer:
        def enforce(self, _text: str) -> "_BlockedResult":
            return _BlockedResult()

    orig_available = api._COVENANT_AVAILABLE
    orig_enforcer = api._covenant_enforcer
    orig_chat = api._agent.chat
    orig_stream = getattr(api._agent, "stream", None)
    api._COVENANT_AVAILABLE = True
    api._covenant_enforcer = _BlockingEnforcer()
    # Spy BOTH inference entry points the streaming generator could use.
    chat_spy = MagicMock(name="agent.chat")
    stream_spy = MagicMock(name="agent.stream")
    api._agent.chat = chat_spy
    api._agent.stream = stream_spy
    try:
        req = api.ChatRequest(session_id="blocked-stream",
                              message="destroy data on the device")
        with pytest.raises(HTTPException) as ei:
            asyncio.run(api.chat_stream(req, _auth=None))
        assert ei.value.status_code == 422, ei.value.status_code
        # Load-bearing: neither inference entry point was reached.
        assert not chat_spy.called, "blocked request leaked into streaming inference (chat)"
        assert not stream_spy.called, "blocked request leaked into streaming inference (stream)"
    finally:
        api._COVENANT_AVAILABLE = orig_available
        api._covenant_enforcer = orig_enforcer
        api._agent.chat = orig_chat
        if orig_stream is not None:
            api._agent.stream = orig_stream
        elif hasattr(api._agent, "stream"):
            del api._agent.stream


def test_streaming_clean_request_passes_covenant_gate():
    """Control: a non-blocked message clears the streaming covenant gate (no 422) and a
    StreamingResponse is produced — the gate is not vacuously blocking everything."""
    pytest.importorskip("fastapi", reason="FastAPI not installed — streaming-control test skipped")

    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    try:
        import api  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"api module unavailable: {exc}")

    from fastapi.responses import StreamingResponse  # noqa: PLC0415

    class _PassResult:
        is_blocked = False

        def summary(self) -> str:
            return "ok"

    class _PassingEnforcer:
        def enforce(self, _text: str) -> "_PassResult":
            return _PassResult()

    orig_available = api._COVENANT_AVAILABLE
    orig_enforcer = api._covenant_enforcer
    api._COVENANT_AVAILABLE = True
    api._covenant_enforcer = _PassingEnforcer()
    try:
        req = api.ChatRequest(session_id="clean-stream", message="what is the status")
        # Must NOT raise; returns a StreamingResponse (generator is lazy — not iterated here,
        # so no full inference is pulled, but the gate has already been cleared).
        resp = asyncio.run(api.chat_stream(req, _auth=None))
        assert isinstance(resp, StreamingResponse), type(resp)
    finally:
        api._COVENANT_AVAILABLE = orig_available
        api._covenant_enforcer = orig_enforcer


# ── Gate 2: L7 CRITICAL hard-stop must withhold the model response ────────────


def test_l7_hard_stop_withholds_response():
    """A CRITICAL invariant (SAFETY_FILTER) hard-stops L7; chat() withholds the response."""
    try:
        InvariantEnforcer = _load_invariant_enforcer()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"InvariantEnforcer unavailable: {exc}")

    # Sanity: the real CRITICAL path sets the hard-stop flag (not a mock).
    enf = InvariantEnforcer()
    assert not enf.is_hard_stopped()
    violations = enf.check_all({"safety_failed": True})
    assert any(v.invariant_name == "SAFETY_FILTER" for v in violations)
    assert enf.is_hard_stopped(), "SAFETY_FILTER CRITICAL must trigger hard-stop"

    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    try:
        from agent import (  # noqa: PLC0415
            AgentConfig,
            HeptagonLayer,
            TokenlessAgentWithHeptagon,
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"TokenlessAgentWithHeptagon unavailable: {exc}")

    # Wire ONLY the hard-stopped enforcer; every other layer is None. chat() guards
    # each layer with `is not None`, so the turn runs with just the L7 gate active.
    heptagon = HeptagonLayer(enforcer=enf)
    agent = TokenlessAgentWithHeptagon(AgentConfig(agent_id="gov-block-test"), heptagon)

    response = agent.chat("hard-stop-session", "please answer this normal question")

    assert _GOV_SENTINEL in response, (
        "L7 hard-stop did not withhold the response; got: " + repr(response[:120])
    )


def test_l7_clean_request_is_not_withheld():
    """Control: with no hard-stop, a normal turn returns the real response, not the sentinel."""
    try:
        InvariantEnforcer = _load_invariant_enforcer()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"InvariantEnforcer unavailable: {exc}")

    if str(_SRC) not in sys.path:
        sys.path.insert(0, str(_SRC))
    try:
        from agent import (  # noqa: PLC0415
            AgentConfig,
            HeptagonLayer,
            TokenlessAgentWithHeptagon,
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"TokenlessAgentWithHeptagon unavailable: {exc}")

    enf = InvariantEnforcer()  # fresh, NOT hard-stopped
    assert not enf.is_hard_stopped()
    heptagon = HeptagonLayer(enforcer=enf)
    agent = TokenlessAgentWithHeptagon(AgentConfig(agent_id="gov-clean-test"), heptagon)

    response = agent.chat("clean-session", "what is the status")
    assert _GOV_SENTINEL not in response, "clean request must NOT be withheld"
    assert isinstance(response, str) and response, "expected a real response"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
