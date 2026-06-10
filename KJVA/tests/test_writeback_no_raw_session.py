"""test_writeback_no_raw_session.py — the WriteBackEngine emit paths must NEVER
put a raw session_id on the wire (ADR-0002 §13.16 / ADR-0001 telemetry forbiddens).

This guards the specific fix made this session: `heptagon/writeback.py` previously
emitted `request.session_id` verbatim into the SoulManager, EventJournal, and Archive
payloads. It now passes every session id through `_hashsid()` (SHA-256, 16 hex,
"sid:"-prefixed). The existing `test_telemetry_no_raw_content.py` covers the
`cognitive_pipeline` emit boundary — a DIFFERENT path — so this WriteBackEngine path
was unguarded until now.

Isolation: `heptagon/writeback.py` is the AGENT-SIDE heptagon package, which collides
by name with the ROOT `heptagon/` package under `python3 -m pytest` (repo root on
sys.path[0]). To assert production behavior faithfully we run in a clean subprocess
whose cwd is `src/` — the production resolution order — and stub the socket sender so
no daemon is needed.

Run:  python3 -m pytest tests/test_writeback_no_raw_session.py -q
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "ai" / "tokenless-agent" / "src"

_DRIVER = r"""
import json, sys, hashlib
sys.path.insert(0, ".")
from heptagon.writeback import WriteBackEngine, WriteBackRequest
from heptagon.mastery import MasteryLevel

RAW_SID = "RAWSID-secret-canary-12345"
EXPECT = "sid:" + hashlib.sha256(RAW_SID.encode()).hexdigest()[:16]

out = {"raw_sid": RAW_SID, "expect_hash": EXPECT}

# 1) Pure record contract: to_dict() must hash the session id.
req = WriteBackRequest(
    session_id=RAW_SID, entity_id="ent1", domain_id="dom1", target="both",
    improvement_score=0.9, mastery_reached=MasteryLevel.INNERSTANDING,
    input_hash="sha256:deadbeef", evidence_count=3,
)
d = req.to_dict()
out["to_dict_blob"] = json.dumps(d, default=str)

# 2) Emit path: capture every outbound socket message; raw id must be absent everywhere.
eng = WriteBackEngine(entity_id="ent1")
captured = []
def _capture(host, port, message, timeout=None, label=""):
    captured.append(message.decode("utf-8") if isinstance(message, (bytes, bytearray)) else str(message))
    return True
eng._send_to_daemon = _capture          # stub the wire — no daemon needed
res = eng.consolidate(req)               # target=both, score>0 ⇒ soul + journal emit
out["accepted"] = bool(getattr(res, "accepted", False))
out["wire_blob"] = "\n".join(captured)
out["n_payloads"] = len(captured)

print(json.dumps(out))
"""


@pytest.fixture(scope="module")
def result():
    proc = subprocess.run(
        [sys.executable, "-c", _DRIVER],
        cwd=str(SRC), capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"driver failed:\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_to_dict_hashes_session_id(result):
    blob = result["to_dict_blob"]
    assert result["raw_sid"] not in blob, "to_dict() leaked the raw session_id"
    assert result["expect_hash"] in blob, "to_dict() did not emit the hashed session id"


def test_emit_paths_carry_no_raw_session_id(result):
    assert result["n_payloads"] >= 1, "no outbound payloads captured — emit path did not run"
    wire = result["wire_blob"]
    assert result["raw_sid"] not in wire, "raw session_id leaked onto the wire"
    assert "secret-canary" not in wire, "raw session_id fragment leaked onto the wire"
    # The hashed form is what legitimately travels.
    assert result["expect_hash"] in wire, "hashed session id missing from outbound payloads"
