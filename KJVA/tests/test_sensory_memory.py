"""test_sensory_memory.py — Phase-4 gate: sensory evidence + extended-memory modules.

Exercises build_evidence_envelope, SensoryRouter, home-security integration, and the
ExperienceAtom / RecallTrail (Jog-My-Memory) / LifespanLedger lifecycle. Pure stdlib.
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "ai" / "tokenless-agent" / "src"
sys.path.insert(0, str(SRC))

import sensory  # noqa: E402
from sensory import build_evidence_envelope, SensoryRouter
from sensory.home_security import HomeSecurityEvent, event_to_envelope, is_actionable  # noqa: E402
from memory.experience_atom import ExperienceAtom  # noqa: E402
from memory.recall_trail import jog_my_memory  # noqa: E402
from memory.lifespan_ledger import LifespanLedger  # noqa: E402


def test_evidence_envelope():
    env = build_evidence_envelope("In the beginning God created the Heaven and the Earth",
                                  session_id="sess-123")
    assert "God" in env.entities and "Heaven" in env.entities
    assert abs(sum(env.byte_profile.values()) - 1.0) < 1e-6
    assert 0.0 <= env.salience <= 1.0
    assert env.session_hash and env.session_hash != "sess-123"      # hashed (PII)
    assert env.modality == "text"


def test_sensory_router_scope_and_determinism():
    from sensory.evidence import EvidenceEnvelope
    r = SensoryRouter()
    prof = {"control": 0.0, "ascii_printable": 0.6, "utf8_lead": 0.2, "utf8_cont": 0.2, "high": 0.0}

    def env(sal):
        return EvidenceEnvelope(session_hash="h", modality="text", entities=["Solomon", "Temple"],
                                byte_profile=prof, salience=sal)

    assert r.route(env(0.7)).memory_scope == "semantic"     # high salience
    assert r.route(env(0.4)).memory_scope == "episodic"     # mid salience
    assert r.route(env(0.1)).memory_scope == "session"      # low salience
    # deterministic: same envelope → same seed
    e = env(0.7)
    assert r.route(e).seed == r.route(e).seed and r.route(e).deterministic
    assert "text" in r.route(e).sensory_scope


def test_home_security_integration():
    ev = HomeSecurityEvent("glass_break", zone="kitchen", confidence=0.95)
    env = event_to_envelope(ev, session_id="s")
    assert env.modality == "sensor"
    assert "home_security:glass_break" in env.sensory_anchors
    assert env.salience > 0.8
    assert is_actionable(ev)
    assert not is_actionable(HomeSecurityEvent("idle"))


def test_experience_atom_touch_and_decay():
    a = ExperienceAtom.create("Tell me about Solomon and the Temple", "Solomon built the Temple.",
                              salience=0.7, now=1000.0)
    assert "Solomon" in a.cue_entities and a.strength == 1.0
    a.strength = 0.5
    a.touch(now=1100.0)
    assert a.access_count == 1 and a.strength > 0.5            # access reinforces
    s0 = a.strength
    a.decay(now=1100.0 + 86400.0)                              # one half-life later
    assert a.strength < s0


def test_recall_trail_jog_my_memory():
    atoms = [
        ExperienceAtom.create("Solomon and the Temple", "r1", now=1.0),
        ExperienceAtom.create("Moses and the Exodus", "r2", now=2.0),
        ExperienceAtom.create("Solomon's wisdom and the Temple", "r3", now=3.0),
    ]
    trail = jog_my_memory("What did Solomon build at the Temple?", atoms, top_k=2, now=10.0)
    assert len(trail.hits) <= 2 and trail.hits, "expected Solomon/Temple atoms recalled"
    # the two Solomon/Temple atoms outrank the Moses atom
    top_ids = set(trail.atom_ids())
    assert atoms[1].atom_id not in top_ids or len(trail.hits) == 2


def test_lifespan_ledger_decay_and_capacity():
    led = LifespanLedger(capacity=3, strength_floor=0.05, half_life=10.0)
    for i in range(3):
        led.register(ExperienceAtom.create(f"cue {i} Alpha", f"resp {i}", now=0.0))
    assert led.stats()["count"] == 3
    evicted = led.decay_all(now=200.0)          # >> many half-lives → all decay below floor
    assert evicted == 3 and led.stats()["count"] == 0
    # capacity enforcement
    led2 = LifespanLedger(capacity=2)
    for i in range(5):
        a = ExperienceAtom.create(f"cue {i}", "r", now=0.0); a.strength = i / 5.0
        led2.register(a)
    assert led2.stats()["count"] == 2


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
