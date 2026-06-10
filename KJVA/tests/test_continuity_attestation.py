"""test_continuity_attestation.py — the neutral identity-continuity hash chain.

ContinuityAttestation is the generalizable core absorbed (neutralized) from the consuming-project
ROOT heptagon/attestation.py — a tamper-evident SHA-256 chain attesting identity continuity that
the agent-side previously lacked. No named-member/Council content.

Run:  python3 -m pytest tests/test_continuity_attestation.py -q

Import strategy — collision-proof, fail-loud
---------------------------------------------
The repo has a ROOT-level ``heptagon/`` package (Council/member content) that shadows
``ai/tokenless-agent/src/heptagon/`` when pytest adds the rootdir to sys.path.  Under the
collision, the old ``pytest.importorskip("heptagon.attestation")`` could silently succeed but
return the WRONG module (root's ``AttestationEngine``, not the agent's ``ContinuityAttestation``),
converting a genuine configuration error into an obscure AttributeError.

Fix in two parts:

1. **Ensure SRC is first in sys.path and sys.modules["heptagon"] points to SRC.**
   conftest.py inserts SRC at index 0, but only if not already present — it does not re-order.
   If the root ``heptagon`` package is already cached in ``sys.modules["heptagon"]`` from an
   earlier test, the import below would resolve to root's ``registry.py`` (populated
   ``MEMBER_REGISTRY``) and break the ``citadel_before_route`` no-op contract that all downstream
   API tests (vision, voice, streaming) depend on.  We evict any root-origin cache entries and
   re-pin SRC at position 0 before importing.

2. **Replace importorskip with a direct import that fails loud.**
   ``importorskip`` silently skips the entire file on ImportError, turning "module missing" into
   a false-green (0 tests run, no alert).  The direct import below raises on failure so a
   misconfigured environment produces a visible ERROR, not a silent skip.
"""
import sys
from pathlib import Path

# Pin SRC at position 0 — must happen before any heptagon import in this file.
_SRC = Path(__file__).resolve().parent.parent / "ai" / "tokenless-agent" / "src"
_SRC_STR = str(_SRC)
if _SRC_STR in sys.path:
    sys.path.remove(_SRC_STR)
sys.path.insert(0, _SRC_STR)

# Evict any root-origin heptagon entries from sys.modules.  Root heptagon exposes
# registry.py with a populated MEMBER_REGISTRY; if it is cached, the
# citadel_before_route() call in api.py blocks every downstream API test with
# "Unknown destination: inference".  Evicting forces a fresh resolve from SRC
# (which has no registry.py → empty set → routes allowed, as the neutral substrate intends).
for _key in list(sys.modules):
    if _key == "heptagon" or _key.startswith("heptagon."):
        _mod_file = getattr(sys.modules[_key], "__file__", "") or ""
        if "tokenless-agent" not in _mod_file:
            del sys.modules[_key]

# Direct import — fails loudly (ImportError / AttributeError) rather than silently
# skipping the file.  SRC is now first in sys.path and no root heptagon is cached,
# so this resolves to ai/tokenless-agent/src/heptagon/attestation.py.
import heptagon.attestation as _att  # noqa: E402

if not hasattr(_att, "ContinuityAttestation"):
    raise ImportError(
        f"heptagon.attestation loaded from {_att.__file__!r} does not export "
        "ContinuityAttestation — likely resolved to the ROOT heptagon package "
        "(Council/member content) instead of ai/tokenless-agent/src/heptagon/."
    )

ContinuityAttestation = _att.ContinuityAttestation


def test_chain_advances_and_links():
    c = ContinuityAttestation()
    a1 = c.attest("state-A")
    a2 = c.attest("state-B")
    assert a1.chain_length == 1 and a2.chain_length == 2
    assert a1.prev == "" and a2.prev == a1.head        # each link chains from the previous head
    assert a1.head != a2.head


def test_tamper_evident_verify():
    c = ContinuityAttestation()
    a1 = c.attest("state-A")
    a2 = c.attest("state-B")
    assert c.verify(a2.prev, a2.state_hash, a2.head) is True
    # a forged head or altered state fails verification
    assert c.verify(a2.prev, "tampered", a2.head) is False
    assert c.verify(a1.head, a2.state_hash, "sha256:deadbeef") is False


def test_deterministic_same_inputs_same_head():
    c1, c2 = ContinuityAttestation(), ContinuityAttestation()
    assert c1.attest("x").head == c2.attest("x").head   # replayable
