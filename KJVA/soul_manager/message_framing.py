"""soul_manager/message_framing.py
Message envelope schema for cognitive bus IPC.
"""
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CognitiveBusMessage:
    msg_type: str  # e.g. "REGISTER", "HEARTBEAT", "EVENT", "DIRECTIVE"
    source_agent: str  # e.g. "utility_svc", "context_coord", "soul_mgr_broker"
    target_agent: str  # e.g. "soul_mgr", "context_coord", "*" (broadcast)
    payload: dict  # Message body
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    correlation_id: Optional[str] = None  # For request-response pairs

    def to_dict(self) -> dict:
        return {
            "msg_type": self.msg_type,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "payload": self.payload,
            "msg_id": self.msg_id,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CognitiveBusMessage":
        return cls(
            msg_type=d["msg_type"],
            source_agent=d["source_agent"],
            target_agent=d["target_agent"],
            payload=d.get("payload", {}),
            msg_id=d.get("msg_id", str(uuid.uuid4())),
            timestamp=d.get("timestamp", time.time()),
            correlation_id=d.get("correlation_id"),
        )


# Cognitive bus port assignments (neutral role-domain names — ADR-0001 §1 compliant)
COGNITIVE_BUS_PORTS = {
    "context_coord":    18600,  # context coordination
    "utility_svc":      18601,  # utility service
    "alignment_svc":    18602,  # alignment service
    "architecture_svc": 18603,  # architecture service
    "evidence_svc":     18604,  # evidence service
    "trust_svc":        18605,  # trust service
    "sequencing_svc":   18606,  # sequencing service
    "policy_svc":       18607,  # policy service
    "soul_mgr":         18610,
    "eventjournald":    18611,
    "gaterunnerd":      18612,
}

# Backwards-compat alias — prefer COGNITIVE_BUS_PORTS in new code
COUNCIL_PORTS = COGNITIVE_BUS_PORTS
