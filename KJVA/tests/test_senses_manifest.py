"""test_senses_manifest.py — the mandatory interoceptive sense + explicit sense manifest.

ADR-0001 §16.4: Interoceptive (self/system-health) is MANDATORY (no opt-out) and must always
produce evidence; every other sense must be EXPLICITLY declared supported/unsupported (no
silent gaps). Covers sensory/interoception.py, sensory/capabilities.py, and GET /v1/senses.

Run:  PYTHONPATH=ai/tokenless-agent/src python3 -m pytest tests/test_senses_manifest.py -q
"""
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "ai" / "tokenless-agent" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

intero = pytest.importorskip("sensory.interoception")
caps = pytest.importorskip("sensory.capabilities")


def test_interoception_always_senses_stdlib_baseline():
    st = intero.sense()
    assert st.cpu_count >= 1, "cpu_count must be read"
    assert st.uptime_s is not None and st.uptime_s >= 0
    # disk OR load must be readable on any normal host (pure-stdlib, no install).
    assert (st.disk_percent is not None) or (st.load_avg_1m is not None)


def test_interoception_evidence_envelope_is_mandatory_and_safe():
    env = intero.as_evidence(session_id="s")
    assert env.modality == "interoceptive"
    assert env.derived_text and env.derived_text.startswith("self-state"), "must carry self-state"
    # telemetry-safe: derived_text excluded from to_dict (perception seam contract).
    d = env.to_dict()
    assert "derived_text" not in d
    assert env.sensory_anchors == ["self:system_health"]


def test_degradation_flag_reflects_thresholds():
    # Synthesize a degraded state and confirm the summary marks it.
    st = intero.InteroState(cpu_count=4, load_per_core=2.0, mem_percent=95.0, disk_percent=99.0)
    intero._assess_degradation(st)
    assert st.degraded is True and st.notes, "high load/mem/disk must flag degraded"
    assert "DEGRADED" in intero.summary(st)


def test_manifest_declares_all_13_senses_no_silent_gaps():
    m = caps.manifest()
    assert len(m) == 14, "13 ADR classes + the native text channel are all declared"
    names = {r["sense"] for r in m}
    for required in ("Visual", "Auditory/Speech-in", "Interoceptive"):
        assert required in names, f"{required} must be explicitly declared"
    # every row has a concrete status (none silently omitted)
    assert all(r["status"] in ("native", "built", "seam", "unsupported") for r in m)
    # unsupported senses are EXPLICITLY declared (the §16.4 requirement), not absent
    assert any(r["status"] == "unsupported" for r in m)


def test_mandatory_interoceptive_is_satisfied():
    s = caps.summary()
    assert s["mandatory_satisfied"] is True, "interoceptive (mandatory) must be available"
    assert s["unsupported_explicitly_declared"] is True
    intero_row = next(r for r in caps.manifest() if r["sense"] == "Interoceptive")
    assert intero_row["mandatory"] is True and intero_row["available"] is True


def test_senses_endpoint():
    pytest.importorskip("fastapi")
    api = pytest.importorskip("api")
    out = api.senses(_auth=None)
    assert out["summary"]["mandatory_satisfied"] is True
    assert isinstance(out["manifest"], list) and len(out["manifest"]) == 14
    assert out["interoception"].get("cpu_count", 0) >= 1
