"""Opt-in mutually authenticated TLS workers talking to ONE Relay authority.

This is the existing length-prefixed Relay RPC over TLS, not MCP HTTP and not
database replication. Workers never receive a local writable store or offline
execution authority. Request authentication is rechecked inside each transaction.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import socket
import socketserver
import ssl
import stat
import threading
from .codec import MAX_REQUEST, canonical, digest, ident, strict_loads
from .errors import RelayError, require

REMOTE_READS = frozenset({"version", "status", "get", "work.ready"})
REMOTE_COMMANDS = frozenset({
    "task.claim", "work.next", "attempt.heartbeat", "attempt.release", "context.hydrate",
    "action.prepare", "memory.add", "adapter.open", "adapter.invoke", "adapter.acknowledge",
    "adapter.reset", "adapter.close", "candidate.capture",
})


def private_file(path: Path) -> Path:
    path = path.expanduser().absolute()
    st = path.lstat()
    require(stat.S_ISREG(st.st_mode) and not path.is_symlink() and st.st_uid == os.geteuid()
            and not (stat.S_IMODE(st.st_mode) & 0o077),
            "PRIVATE_FILE", "configuration, credentials and keys require an owner-only regular file")
    return path


def config_file(path: Path, fields: set[str]) -> dict:
    path = private_file(path)
    require(path.stat().st_size <= 65536, "CONFIG_SIZE", "configuration too large")
    value = strict_loads(path.read_bytes())
    require(type(value) is dict and set(value) == fields, "TLS_CONFIG", "unexpected or missing configuration fields")
    require(value["version"] == 1 and type(value["version"]) is int, "TLS_CONFIG", "configuration version 1 required")
    for key in fields & {"cert", "key", "ca", "token_file"}:
        require(type(value[key]) is str and Path(value[key]).is_absolute(), "TLS_CONFIG", f"{key} must be an absolute path")
        require(Path(value[key]).is_file(), "TLS_CONFIG", f"{key} file missing")
    for key in fields & {"host", "server_name"}:
        require(type(value[key]) is str and bool(value[key]) and len(value[key]) < 254 and "\x00" not in value[key], "TLS_CONFIG", "invalid hostname")
    require(type(value["port"]) is int and 0 <= value["port"] < 65536, "TLS_CONFIG", "invalid port")
    private_file(Path(value["key"]))
    return value


def server_context(config: dict) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cafile=config["ca"])
    ctx.load_cert_chain(config["cert"], config["key"])
    return ctx


def client_context(config: dict) -> ssl.SSLContext:
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=config["ca"])
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_cert_chain(config["cert"], config["key"])
    return ctx


class TLSHandler(socketserver.BaseRequestHandler):
    def handle(self):
        from .service import receive, send, route, MAX_RESPONSE
        self.request.settimeout(5)
        try:
            with self.server.tls_context.wrap_socket(self.request, server_side=True) as channel:
                channel.settimeout(30)
                fp = digest(channel.getpeercert(binary_form=True))
                try:
                    request = receive(channel, MAX_REQUEST)
                    require(request.get("op") in REMOTE_READS | REMOTE_COMMANDS,
                            "REMOTE_OPERATION_DENIED", "operation is only available to the local operator")
                    with self.server.controller.store.remote_peer(fp):
                        response = {"ok": True, "result": route(self.server.controller, request)}
                except RelayError as e:
                    response = {"ok": False, "error": {"code": e.code, "message": e.message}}
                except (ValueError, KeyError, TypeError):
                    response = {"ok": False, "error": {"code": "RPC_SCHEMA", "message": "invalid request"}}
                except Exception:
                    response = {"ok": False, "error": {"code": "INTERNAL", "message": "inspect local operator diagnostics"}}
                send(channel, response, MAX_RESPONSE)
        except (OSError, RelayError):
            # Missing/invalid certificate or disconnected caller cannot gain authority.
            # An absent reply must be treated as uncertain by the client, not retried.
            pass


class TLSServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = False
    block_on_close = True
    allow_reuse_address = True
    request_queue_size = 32

    def __init__(self, controller, config_path: Path):
        self.config = config_file(config_path, {"version", "host", "port", "cert", "key", "ca"})
        self.controller = controller
        self.capacity = threading.BoundedSemaphore(16)
        self.tls_context = server_context(self.config)
        super().__init__((self.config["host"], self.config["port"]), TLSHandler)

    def process_request(self, request, address):
        if not self.capacity.acquire(False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.capacity.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.capacity.release()


class RemoteClient:
    def __init__(self, config_path: Path, timeout: float = 30):
        self.config = config_file(config_path, {"version", "host", "port", "server_name", "cert", "key", "ca", "token_file"})
        self.token_path = private_file(Path(self.config["token_file"]))
        require(self.config["port"] > 0, "TLS_CONFIG", "connect to a concrete server port")
        require(0 < timeout <= 300, "INVALID_FIELD", "timeout must be in (0, 300]")
        self.context = client_context(self.config)
        self.timeout = timeout

    def call(self, op: str, payload: dict, command_id: str | None = None) -> dict:
        from .controller import fresh_id
        from .service import receive, send, MAX_RESPONSE
        require(op in REMOTE_READS | REMOTE_COMMANDS, "REMOTE_OPERATION_DENIED", "local operator operation")
        if op in REMOTE_COMMANDS:
            require(command_id is not None, "COMMAND_ID_REQUIRED", "supply a stable logical command ID across reconnects")
        cid = ident(command_id or fresh_id("query"))
        token = self.token_path.read_text().strip()
        require(token.startswith("rly1."), "WORKER_CREDENTIAL_REQUIRED", "remote clients never use the owner key")
        request = {"api_version": 1, "id": cid, "op": op, "payload": payload, "token": token}
        may_have_sent = False
        try:
            with socket.create_connection((self.config["host"], self.config["port"]), self.timeout) as raw:
                with self.context.wrap_socket(raw, server_hostname=self.config["server_name"]) as channel:
                    may_have_sent = True  # sendall itself may partially succeed
                    send(channel, request, MAX_REQUEST)
                    response = receive(channel, MAX_RESPONSE)
        except (OSError, RelayError) as exc:
            raise RelayError("REMOTE_OUTCOME_UNKNOWN" if may_have_sent else "REMOTE_UNAVAILABLE",
                             f"request {cid}: no definitive response; reconnect with the SAME command ID and payload; never replay effects offline") from exc
        if not response.get("ok"):
            err = response.get("error", {})
            raise RelayError(err.get("code", "RPC_ERROR"), err.get("message", "remote request rejected"))
        return response["result"]
