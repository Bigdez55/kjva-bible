"""test_adapter_runtime_absorption.py — the RUNTIME absorption path is wired (ADR-0002 §9).

tests/test_adapter_apply.py already proves the XMIND C engine *applies* a loaded adapter
(apply_count>0, logit MAE>0). This test proves the next link: the agent's XMindClient
genuinely CALLS xmind_easy_load_adapter at init when an adapter is configured
(TOKENLESS_ADAPTER) — i.e. the absorption consumer is live in the runtime, not just in a
C unit test — and that absorbing the adapter observably changes generation vs the base.

The discriminating assertion is "output differs", NOT "load returned rc=0": a
mis-canonicalized adapter loads rc=0 yet binds to nothing and applies a zero delta. Only
a changed continuation proves the delta actually reached the hot path.

Skips only if the engine genuinely cannot load (libxmind-core not built / no weights) or
the repo's proof adapter is absent — real gaps, never silently passed.

Run:  python3 -m pytest tests/test_adapter_runtime_absorption.py -q
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

V7 = Path(__file__).resolve().parent.parent
SRC = V7 / "ai" / "tokenless-agent" / "src"
PROOF_ADAPTER = V7 / "training" / "adapters" / "staging" / "lora_proof" / "adapter.safetensors"

_DRIVER = r"""
import json, os, sys
sys.path.insert(0, ".")
out = {}
import _xmind.client as C
# Base run (no adapter configured)
base = C.XMindClient()
out["engine_loaded"] = True
out["base_adapter_loaded"] = base.adapter_loaded()
out["base"] = base.generate("And God said", max_new=40)[:96]
base._lib.xmind_easy_shutdown()
print(json.dumps(out))
"""

_DRIVER_ADAPTER = r"""
import json, os, sys
sys.path.insert(0, ".")
out = {}
import _xmind.client as C
c = C.XMindClient()                       # __init__ reads TOKENLESS_ADAPTER and absorbs it
out["adapter_loaded"] = c.adapter_loaded()
out["adapter_path_set"] = c.adapter_path is not None
out["adapted"] = c.generate("And God said", max_new=40)[:96]
print(json.dumps(out))
"""


def _run(driver: str, env_extra=None):
    import os
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run([sys.executable, "-c", driver], cwd=str(SRC),
                          capture_output=True, text=True, timeout=300, env=env)
    if proc.returncode != 0:
        return None, proc.stderr[-1500:]
    return json.loads(proc.stdout.strip().splitlines()[-1]), None


@pytest.fixture(scope="module")
def runs():
    if not PROOF_ADAPTER.exists():
        pytest.skip(f"proof adapter not present at {PROOF_ADAPTER} — real gap, not a pass")
    base, err = _run(_DRIVER)
    if base is None:
        pytest.skip(f"XMIND engine not built (run `make` in ai/xmind): {err}")
    adapted, err2 = _run(_DRIVER_ADAPTER, {"TOKENLESS_ADAPTER": str(PROOF_ADAPTER)})
    assert adapted is not None, f"adapter driver failed:\n{err2}"
    return base, adapted


def test_base_runs_without_adapter(runs):
    base, _ = runs
    assert base["base_adapter_loaded"] is False, "base run must NOT have an adapter loaded"
    assert base["base"].strip(), "base must generate"


def test_runtime_absorbs_configured_adapter(runs):
    _, adapted = runs
    assert adapted["adapter_loaded"] is True, "XMindClient did not load the configured adapter"
    assert adapted["adapter_path_set"] is True, "adapter_path not recorded on the client"


def test_absorption_changes_generation(runs):
    base, adapted = runs
    assert adapted["adapted"] != base["base"], (
        "absorbing the adapter did not change generation — the delta bound to nothing "
        "(mis-canonicalized name?). rc=0 is not enough; the output must differ."
    )
