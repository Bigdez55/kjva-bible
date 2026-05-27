"""Daemon-backed client boundary for soul, archive, and journal services."""
from __future__ import annotations

import asyncio
import json
import os
import socket
import struct
import time
import uuid
from typing import Any, Dict, Optional

from .message_framing import COUNCIL_PORTS

_HOST_ENV = {
    "soulmgrd": "SOULMGR_HOST",
    "archivesd": "ARCHIVES_HOST",
    "eventjournald": "EVENTJOURNAL_HOST",
}

_PORT_ENV = {
    "soulmgrd": "SOULMGR_PORT",
    "archivesd": "ARCHIVES_PORT",
    "eventjournald": "EVENTJOURNAL_PORT",
}


def _host_for(agent: str) -> str:
    env_name = _HOST_ENV.get(agent, "")
    return os.environ.get(env_name, os.environ.get("COUNCIL_DAEMON_HOST", "127.0.0.1"))


def _port_for(agent: str) -> int:
    env_name = _PORT_ENV.get(agent, "")
    default = COUNCIL_PORTS.get(agent, 0)
    return int(os.environ.get(env_name, str(default)))


def _accepted(response: Optional[Dict[str, Any]]) -> bool:
    if not response:
        return False
    payload = response.get("payload")
    if isinstance(payload, dict):
        return bool(
            payload.get("ok")
            or payload.get("accepted")
            or payload.get("status") == "ok"
        )
    return bool(
        response.get("ok")
        or response.get("accepted")
        or response.get("status") == "ok"
    )


def _extract_value(response: Optional[Dict[str, Any]]) -> Any:
    if not response:
        return None
    payload = response.get("payload")
    if isinstance(payload, dict) and "value" in payload:
        return payload.get("value")
    return response.get("value")


class CouncilDaemonAsyncClient:
    """Async length-prefixed JSON client for Council daemons."""

    def __init__(
        self,
        *,
        source_agent: str = "tokenless-agent",
        namespace: Optional[str] = None,
        timeout: float = 0.5,
    ) -> None:
        self.source_agent = source_agent
        self.namespace = namespace
        self.timeout = timeout

    async def call(self, target_agent: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        message = {
            "msg_type": "REQUEST",
            "source_agent": self.source_agent,
            "target_agent": target_agent,
            "payload": payload,
            "msg_id": str(uuid.uuid4()),
            "timestamp": time.time(),
        }
        host = _host_for(target_agent)
        port = _port_for(target_agent)
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=self.timeout,
            )
            encoded = json.dumps(message).encode("utf-8")
            writer.write(struct.pack(">I", len(encoded)) + encoded)
            await writer.drain()

            header = await asyncio.wait_for(reader.readexactly(4), timeout=self.timeout)
            resp_len = struct.unpack(">I", header)[0]
            if resp_len <= 0 or resp_len > 262144:
                writer.close()
                await writer.wait_closed()
                return None

            body = await asyncio.wait_for(reader.readexactly(resp_len), timeout=self.timeout)
            writer.close()
            await writer.wait_closed()
            return json.loads(body.decode("utf-8"))
        except (OSError, asyncio.TimeoutError, json.JSONDecodeError, struct.error):
            return None

    async def get(self, bucket: str, key: str, namespace: Optional[str] = None) -> Any:
        response = await self.call(
            "soulmgrd",
            {
                "action": "get",
                "bucket": bucket,
                "key": key,
                "namespace": namespace or self.namespace,
            },
        )
        return _extract_value(response)

    async def put(
        self,
        bucket: str,
        key: str,
        value: Any,
        namespace: Optional[str] = None,
    ) -> bool:
        response = await self.call(
            "soulmgrd",
            {
                "action": "put",
                "bucket": bucket,
                "key": key,
                "namespace": namespace or self.namespace,
                "value": value,
            },
        )
        return _accepted(response)

    async def archive(self, payload: Dict[str, Any], event_type: str = "mastery_archive") -> bool:
        response = await self.call(
            "archivesd",
            {
                "action": "append",
                "event_type": event_type,
                "payload": payload,
            },
        )
        return _accepted(response)

    async def journal(self, payload: Dict[str, Any], event_type: str = "mastery_writeback") -> bool:
        response = await self.call(
            "eventjournald",
            {
                "action": "append",
                "event_type": event_type,
                "payload": payload,
            },
        )
        return _accepted(response)


class CouncilDaemonSyncClient:
    """Sync length-prefixed JSON client for calibration/write-back code."""

    def __init__(
        self,
        *,
        source_agent: str = "tokenless-agent",
        namespace: Optional[str] = None,
        timeout: float = 0.5,
    ) -> None:
        self.source_agent = source_agent
        self.namespace = namespace
        self.timeout = timeout

    def call(self, target_agent: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        message = {
            "msg_type": "REQUEST",
            "source_agent": self.source_agent,
            "target_agent": target_agent,
            "payload": payload,
            "msg_id": str(uuid.uuid4()),
            "timestamp": time.time(),
        }
        host = _host_for(target_agent)
        port = _port_for(target_agent)
        encoded = json.dumps(message).encode("utf-8")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect((host, port))
                sock.sendall(struct.pack(">I", len(encoded)) + encoded)
                header = self._recvexactly(sock, 4)
                if header is None:
                    return None
                resp_len = struct.unpack(">I", header)[0]
                if resp_len <= 0 or resp_len > 262144:
                    return None
                body = self._recvexactly(sock, resp_len)
                if body is None:
                    return None
                return json.loads(body.decode("utf-8"))
        except (OSError, json.JSONDecodeError, struct.error):
            return None

    def put(
        self,
        bucket: str,
        key: str,
        value: Any,
        namespace: Optional[str] = None,
    ) -> bool:
        response = self.call(
            "soulmgrd",
            {
                "action": "put",
                "bucket": bucket,
                "key": key,
                "namespace": namespace or self.namespace,
                "value": value,
            },
        )
        return _accepted(response)

    def archive(self, payload: Dict[str, Any], event_type: str = "mastery_archive") -> bool:
        response = self.call(
            "archivesd",
            {
                "action": "append",
                "event_type": event_type,
                "payload": payload,
            },
        )
        return _accepted(response)

    def journal(self, payload: Dict[str, Any], event_type: str = "mastery_writeback") -> bool:
        response = self.call(
            "eventjournald",
            {
                "action": "append",
                "event_type": event_type,
                "payload": payload,
            },
        )
        return _accepted(response)

    @staticmethod
    def _recvexactly(sock: socket.socket, n: int) -> Optional[bytes]:
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = sock.recv(n - len(buf))
            except OSError:
                return None
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)
