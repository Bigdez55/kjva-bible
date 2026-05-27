"""council/runtime/ipc/message_framing.py
Message envelope schema for Council IPC.
"""
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CouncilMessage:
    msg_type: str  # e.g. "REGISTER", "HEARTBEAT", "EVENT", "DIRECTIVE"
    source_agent: str  # e.g. "ruthd", "ahkid", "councild_broker"
    target_agent: str  # e.g. "soulmgrd", "ahkid", "*" (broadcast)
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
    def from_dict(cls, d: dict) -> "CouncilMessage":
        return cls(
            msg_type=d["msg_type"],
            source_agent=d["source_agent"],
            target_agent=d["target_agent"],
            payload=d.get("payload", {}),
            msg_id=d.get("msg_id", str(uuid.uuid4())),
            timestamp=d.get("timestamp", time.time()),
            correlation_id=d.get("correlation_id"),
        )


# Council port assignments.
# XMIND write-back is the canonical port source of truth:
#   soulmgrd      -> 18610
#   archivesd     -> 18611
#   eventjournald -> 18612
COUNCIL_PORTS = {
    "ahkid": 18600,
    "ruthd": 18601,
    "sarahd": 18602,
    "ezrid": 18603,
    "abigaild": 18604,
    "magend": 18605,
    "cherevd": 18606,
    "estherd": 18607,
    "soulmgrd": 18610,
    "archivesd": 18611,
    "eventjournald": 18612,
    "gaterunnerd": 18613,
}
