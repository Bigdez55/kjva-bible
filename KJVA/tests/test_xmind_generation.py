"""test_xmind_generation.py — general prompts generate through the XMIND C ENGINE (M3).

The sovereign inference path (ADR-0002 §3): generation runs through the deployed,
parity-verified XMIND C engine (ai/xmind, libxmind-core) via _xmind/client.py -> _xmind_glue,
NOT through any torch/Python shortcut. This proves it end to end in a clean subprocess:

  1. The XMindClient binds libxmind-core and generates real model output.
  2. A general prompt through the agent yields XMIND-generated text (not a template),
     generation_invoked=True; scripture still uses exact retrieval.

Skips only if the engine genuinely cannot load (libxmind-core not built) — which is a real
gap to fix (build ai/xmind), never silently passed.

Run:  python3 -m pytest tests/test_xmind_generation.py -q
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "ai" / "tokenless-agent" / "src"

_DRIVER = r"""
import json, sys
sys.path.insert(0, ".")
out = {}
from _xmind import get_client
c = get_client()
out["engine_loaded"] = c is not None
if c is None:
    print(json.dumps(out)); sys.exit(0)
out["version"] = c.version()
out["direct_gen"] = c.generate("The LORD is my shepherd;", max_new=40)[:160]

from agent import TokenlessAgent, AgentConfig
a = TokenlessAgent(AgentConfig())
gen = a.chat("s", "Blessed are the meek for")
out["general_response"] = gen[:160]
out["generation_invoked"] = bool(getattr(a, "_last_generated", False))
out["is_template"] = gen.startswith("[Tokenless")
out["scripture_ok"] = "shepherd" in a.chat("s", "Psalm 23:1").lower()
print(json.dumps(out))
"""


@pytest.fixture(scope="module")
def result():
    proc = subprocess.run([sys.executable, "-c", _DRIVER], cwd=str(SRC),
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, f"driver failed:\n{proc.stderr[-2000:]}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_xmind_engine_loads_and_generates(result):
    if not result.get("engine_loaded"):
        pytest.skip("XMIND C engine not built (run `make` in ai/xmind) — real gap, not a pass")
    assert "xmind" in result["version"].lower()
    assert isinstance(result["direct_gen"], str) and result["direct_gen"].strip()


def test_agent_general_prompt_uses_xmind(result):
    if not result.get("engine_loaded"):
        pytest.skip("XMIND C engine not built")
    assert result["generation_invoked"] is True, "the XMIND engine was not invoked"
    assert result["is_template"] is False, "general response is still a template, not XMIND output"
    assert len(result["general_response"]) > 0


def test_scripture_still_uses_retrieval(result):
    if not result.get("engine_loaded"):
        pytest.skip("XMIND C engine not built")
    assert result["scripture_ok"] is True, "scripture must still resolve via exact retrieval"
