#!/usr/bin/env python3
"""Promoted runtime smoke for daemon persistence and HTTP surfaces."""
from __future__ import annotations

import json
import os
import socketserver
import struct
import sys
import threading
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PORTS = {
    "soulmgrd": 18610,
    "archivesd": 18611,
    "eventjournald": 18612,
}


@dataclass
class Recorder:
    messages: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: {name: [] for name in PORTS}
    )

    def record(self, daemon: str, message: dict[str, Any]) -> None:
        self.messages[daemon].append(message)


class _FramedHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server = self.server
        recorder: Recorder = server.recorder  # type: ignore[attr-defined]
        daemon_name: str = server.daemon_name  # type: ignore[attr-defined]
        raw_len = self._recvexactly(4)
        if raw_len is None:
            return
        body_len = struct.unpack(">I", raw_len)[0]
        if body_len <= 0 or body_len > 262144:
            return
        body = self._recvexactly(body_len)
        if body is None:
            return
        message = json.loads(body.decode("utf-8"))
        recorder.record(daemon_name, message)

        payload = message.get("payload", {})
        response_payload: dict[str, Any] = {"ok": True, "accepted": True}
        if daemon_name == "soulmgrd" and payload.get("action") == "get":
            response_payload["value"] = None
        response = {
            "status": "ok",
            "accepted": True,
            "payload": response_payload,
        }
        encoded = json.dumps(response).encode("utf-8")
        self.request.sendall(struct.pack(">I", len(encoded)) + encoded)

    def _recvexactly(self, n: int) -> bytes | None:
        buf = bytearray()
        while len(buf) < n:
            chunk = self.request.recv(n - len(buf))
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)


class _ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _start_server(name: str, port: int, recorder: Recorder) -> _ThreadedTCPServer:
    server = _ThreadedTCPServer(("127.0.0.1", port), _FramedHandler)
    server.daemon_name = name  # type: ignore[attr-defined]
    server.recorder = recorder  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    recorder = Recorder()
    with ExitStack() as stack:
        servers = {
            name: _start_server(name, port, recorder)
            for name, port in PORTS.items()
        }
        for server in servers.values():
            stack.callback(server.server_close)
            stack.callback(server.shutdown)

        os.environ["SOULMGR_HOST"] = "127.0.0.1"
        os.environ["SOULMGR_PORT"] = str(PORTS["soulmgrd"])
        os.environ["ARCHIVES_HOST"] = "127.0.0.1"
        os.environ["ARCHIVES_PORT"] = str(PORTS["archivesd"])
        os.environ["EVENTJOURNAL_HOST"] = "127.0.0.1"
        os.environ["EVENTJOURNAL_PORT"] = str(PORTS["eventjournald"])

        here = Path(__file__).resolve()
        src_dir = here.parents[1] / "src"
        workspace_root = here.parents[4]
        sys.path.insert(0, str(src_dir))
        sys.path.append(str(workspace_root))

        import api  # noqa: PLC0415
        from fastapi.testclient import TestClient  # noqa: PLC0415
        from heptagon.mastery import MasteryLevel  # noqa: PLC0415
        from heptagon.writeback import WriteBackEngine, WriteBackRequest  # noqa: PLC0415

        client = TestClient(api.app)

        chat = client.post(
            "/v1/chat",
            json={
                "session_id": "promoted-smoke-chat",
                "message": "Explain how continuity preserves system identity.",
            },
        )
        _assert(chat.status_code == 200, f"/v1/chat failed: {chat.status_code} {chat.text}")

        stream = client.post(
            "/v1/chat/stream",
            json={
                "session_id": "promoted-smoke-stream",
                "message": "Explain how continuity preserves system identity.",
            },
        )
        _assert(stream.status_code == 200, f"/v1/chat/stream failed: {stream.status_code} {stream.text}")
        _assert(
            stream.headers.get("content-type", "").startswith("text/event-stream"),
            f"/v1/chat/stream wrong content-type: {stream.headers.get('content-type')}",
        )
        _assert("[DONE]" in stream.text, "/v1/chat/stream missing [DONE] marker")

        tool = client.post(
            "/v1/tool",
            json={"tool_name": "status_probe", "params": {"scope": "runtime"}},
        )
        _assert(tool.status_code == 200, f"/v1/tool failed: {tool.status_code} {tool.text}")

        writeback = WriteBackEngine("smoke-entity")
        result = writeback.consolidate(
            WriteBackRequest(
                session_id="promoted-smoke-writeback",
                entity_id="smoke-entity",
                domain_id="runtime-governance",
                target="both",
                improvement_score=0.72,
                mastery_reached=MasteryLevel.INNERSTANDING,
                input_hash="0123456789abcdef",
                evidence_count=3,
                delta_data=b"runtime-delta",
            )
        )
        _assert(result.soul_written, "writeback did not reach soulmgrd")
        _assert(result.journal_written, "writeback did not reach eventjournald")
        _assert(result.archive_written, "writeback did not reach archivesd")

        time.sleep(0.2)

        soul_messages = recorder.messages["soulmgrd"]
        archive_messages = recorder.messages["archivesd"]
        journal_messages = recorder.messages["eventjournald"]

        _assert(any(msg.get("payload", {}).get("action") == "put" for msg in soul_messages), "no soul put recorded")
        _assert(
            any(msg.get("payload", {}).get("event_type") == "mastery_archive" for msg in archive_messages),
            "no mastery archive append recorded",
        )
        _assert(
            any(msg.get("payload", {}).get("event_type") == "mastery_writeback" for msg in journal_messages),
            "no mastery writeback journal append recorded",
        )
        _assert(
            any(msg.get("payload", {}).get("event_type") == "tokenless.chat.turn_complete" for msg in journal_messages),
            "no cognitive pipeline journal append recorded",
        )

        mastery_journal = next(
            msg
            for msg in journal_messages
            if msg.get("payload", {}).get("event_type") == "mastery_writeback"
        )
        mastery_payload = mastery_journal["payload"]["payload"]
        for required in (
            "session_id",
            "entity_id",
            "domain_id",
            "mastery_reached",
            "mastery_label",
            "improvement_score",
            "evidence_count",
            "input_hash",
            "event_id",
            "generation_index",
        ):
            _assert(required in mastery_payload, f"missing writeback payload field: {required}")

        print("promoted_runtime_smoke_ok")
        print(f"soul_messages={len(soul_messages)}")
        print(f"archive_messages={len(archive_messages)}")
        print(f"journal_messages={len(journal_messages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
