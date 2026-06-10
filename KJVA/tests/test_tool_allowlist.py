"""test_tool_allowlist.py — /v1/tool enforces its allowlist fail-closed (ADR §13).

The endpoint long DOCUMENTED "tool_name must be in the allowlist" but enforced nothing —
any tool_name reached the agent and got a canned success, an unbounded tool surface. This
pins the enforced gate: an unknown tool is refused with HTTP 403 BEFORE the agent runs it;
an allowlisted tool (system_info) executes and returns real interoceptive self-state.

Run:  python3 -m pytest tests/test_tool_allowlist.py -q
"""
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "ai" / "tokenless-agent" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(scope="module")
def api():
    pytest.importorskip("fastapi", reason="FastAPI not installed — tool-allowlist test skipped")
    try:
        import api as _api  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"api module unavailable: {exc}")
    return _api


def test_unknown_tool_is_refused_403(api):
    from fastapi import HTTPException  # noqa: PLC0415
    req = api.ToolRequest(tool_name="rm_rf_everything", params={})
    with pytest.raises(HTTPException) as ei:
        api.execute_tool(req, _auth=None)
    assert ei.value.status_code == 403, "unknown tool must be refused fail-closed"


def test_allowlisted_tool_executes(api):
    assert "system_info" in api._TOOL_ALLOWLIST, "system_info must be allowlisted by default"
    resp = api.execute_tool(api.ToolRequest(tool_name="system_info", params={}), _auth=None)
    assert resp.tool_name == "system_info"
    # The agent's system_info returns interoceptive self-state (counts/ratios, no user content).
    assert isinstance(resp.result, dict)
    assert resp.result.get("status") == "ok"
    assert "cpu_count" in resp.result.get("result", {}), "system_info must return self-state"
