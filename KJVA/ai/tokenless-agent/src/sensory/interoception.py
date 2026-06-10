"""sensory/interoception.py — Interoceptive sense: the model's awareness of its OWN state.

ADR-0001 §7.1 Interoceptive (internal body state): system health, battery, CPU/GPU temp,
memory, network — for self-monitoring and degradation awareness. Per ADR-0001 §16.4 this is
the ONE sensory class that is MANDATORY with **no opt-out** — so it must always exist and
always produce evidence.

Therefore this sense has a PURE-STDLIB baseline that works on any platform with no install
(load average, CPU count, disk usage, this process's memory + uptime). If ``psutil`` is
present (or self-provisioned), it is enriched with system memory %, battery %, and a richer
CPU read — but the baseline alone satisfies the mandatory contract.

Produces an EvidenceEnvelope(modality="interoceptive") via the §7.3 perception boundary, plus
a short human/LM-readable summary (derived_text) and a degraded flag for L6 degradation
awareness.
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from .evidence import EvidenceEnvelope, hash_session

logger = logging.getLogger("tokenless.sensory.interoception")

_START = None  # set lazily (no Date.now at import); first sense() call stamps it.


@dataclass
class InteroState:
    """The model's self-sensed internal state. Counts/ratios only — no user content."""
    cpu_count: int = 0
    load_avg_1m: Optional[float] = None
    load_per_core: Optional[float] = None      # load_avg_1m / cpu_count
    mem_percent: Optional[float] = None         # system memory used % (psutil)
    proc_rss_mb: Optional[float] = None         # this process resident set size
    disk_percent: Optional[float] = None        # root filesystem used %
    battery_percent: Optional[float] = None     # psutil, if a battery exists
    on_ac_power: Optional[bool] = None
    uptime_s: Optional[float] = None            # process uptime
    source: str = "stdlib"                      # "stdlib" or "psutil-enriched"
    degraded: bool = False                      # True if a resource is in a worrying band
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _stdlib_state(now: float) -> InteroState:
    st = InteroState(source="stdlib")
    st.cpu_count = os.cpu_count() or 1
    try:
        la1, _la5, _la15 = os.getloadavg()       # unix
        st.load_avg_1m = round(la1, 3)
        st.load_per_core = round(la1 / max(st.cpu_count, 1), 3)
    except (OSError, AttributeError):
        pass
    try:
        import resource  # unix-only
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # ru_maxrss is bytes on macOS, kilobytes on Linux.
        st.proc_rss_mb = round((rss / (1024 * 1024)) if rss > 10_000_000 else (rss / 1024), 1)
    except Exception:  # noqa: BLE001
        pass
    try:
        du = shutil.disk_usage(os.path.abspath(os.sep))
        st.disk_percent = round(100.0 * du.used / du.total, 1)
    except Exception:  # noqa: BLE001
        pass
    global _START
    if _START is None:
        _START = now
    st.uptime_s = round(now - _START, 1)
    return st


def _enrich_psutil(st: InteroState) -> InteroState:
    """Best-effort enrichment; self-provisions psutil if auto-provision is enabled."""
    try:
        from . import provision
        if not provision.ensure("psutil", "psutil"):
            return st
        import psutil  # type: ignore
        st.mem_percent = round(float(psutil.virtual_memory().percent), 1)
        try:
            bat = psutil.sensors_battery()
            if bat is not None:
                st.battery_percent = round(float(bat.percent), 1)
                st.on_ac_power = bool(bat.power_plugged)
        except Exception:  # noqa: BLE001
            pass
        st.source = "psutil-enriched"
    except Exception:  # noqa: BLE001
        pass
    return st


def _assess_degradation(st: InteroState) -> None:
    notes: list = []
    if st.load_per_core is not None and st.load_per_core > 1.5:
        notes.append(f"high CPU load ({st.load_per_core}/core)")
    if st.mem_percent is not None and st.mem_percent > 90:
        notes.append(f"memory pressure ({st.mem_percent}%)")
    if st.disk_percent is not None and st.disk_percent > 95:
        notes.append(f"disk almost full ({st.disk_percent}%)")
    if st.battery_percent is not None and st.battery_percent < 15 and st.on_ac_power is False:
        notes.append(f"battery low ({st.battery_percent}%) on battery")
    st.notes = notes
    st.degraded = bool(notes)


def sense(now: Optional[float] = None) -> InteroState:
    """Read the model's current internal state. Always succeeds (stdlib baseline)."""
    st = _stdlib_state(time.time() if now is None else now)
    st = _enrich_psutil(st)
    _assess_degradation(st)
    return st


def summary(st: Optional[InteroState] = None) -> str:
    """A short LM/human-readable self-state line (derived_text for the envelope)."""
    st = st or sense()
    bits = [f"cpu_load/core={st.load_per_core}"]
    if st.mem_percent is not None:
        bits.append(f"mem={st.mem_percent}%")
    if st.disk_percent is not None:
        bits.append(f"disk={st.disk_percent}%")
    if st.battery_percent is not None:
        bits.append(f"battery={st.battery_percent}%{'(AC)' if st.on_ac_power else ''}")
    status = "DEGRADED: " + "; ".join(st.notes) if st.degraded else "nominal"
    return f"self-state [{status}] " + " ".join(bits)


def as_evidence(session_id: str = "", now: Optional[float] = None) -> EvidenceEnvelope:
    """The mandatory interoceptive evidence path: a §7.3 EvidenceEnvelope of self-state.

    Content-free w.r.t. the user (only the model's own resource metrics). derived_text is the
    self-state summary so degradation can reach cognition when relevant."""
    st = sense(now=now)
    text = summary(st)
    import hashlib
    payload_hash = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    return EvidenceEnvelope(
        session_hash=hash_session(session_id) if session_id else "",
        modality="interoceptive",
        entities=[], sensory_anchors=["self:system_health"],
        byte_profile={}, salience=1.0 if st.degraded else 0.2,
        length=len(text), metadata={"degraded": st.degraded, "source": st.source},
        evidence_id="ev:intero:" + payload_hash[7:19], payload_hash=payload_hash,
        risk_class="elevated" if st.degraded else "standard",
        privacy_class="internal", materialization_state="envelope",
        derived_text=text,
    )
