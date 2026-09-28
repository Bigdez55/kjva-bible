"""MCP 2025-06-18 stdio adapter for scoped Relay worker capabilities.

No models, vendor SDKs, provider credentials, telemetry exporters or dependencies.
Only protocol JSON is written to stdout. Native host tools and hidden compaction
are outside this adapter; explicit reset and cold-process recovery are supported.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from . import __version__
from .codec import MAX_REQUEST, canonical, strict_loads
from .controller import fresh_id
from .errors import RelayError, require
from .network import RemoteClient, private_file
from .service import call

PROTOCOL = "2025-06-18"


def schema(required: dict, optional: dict | None = None) -> dict:
    return {"type": "object", "properties": {**required, **(optional or {})},
            "required": list(required), "additionalProperties": False}


STR = {"type": "string", "minLength": 1}
ID = {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$"}
OBJ = {"type": "object"}
CID = {"command_id": ID}
TOOL_SPECS = {
    "relay_status": ("Read durable work and unresolved actions in your scope.", schema({}), None),
    "relay_ready": ("List eligible tasks and explicit blocking reasons.", schema({"workflow": ID}), None),
    "relay_get": ("Read a scoped durable object; this is not an arbitrary file/blob reader.", schema({"kind": STR, "id": ID}), None),
    "relay_claim": ("Claim an eligible task with fenced resources.", schema({**CID, "id": ID}, {"ttl": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600}}), "task.claim"),
    "relay_hydrate": ("Read exact task context; next acknowledge its body_hash before preparing an effect.", schema({**CID, "attempt": ID}, {"budget_bytes": {"type": "integer", "minimum": 1024, "maximum": 2097152}}), "context.hydrate"),
    "relay_acknowledge": ("Acknowledge the hash of context bytes you received. This never proves comprehension.", schema({**CID, "context": ID, "body_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}), "adapter.acknowledge"),
    "relay_prepare": ("Durably prepare an authorized effect; only the operator/dispatcher executes it.", schema({**CID, "id": ID, "attempt": ID, "context": ID, "type": {"type": "string", "enum": ["file.write", "command"]}, "args": OBJ}), "action.prepare"),
    "relay_heartbeat": ("Renew a current attempt. Expired/stale attempts are rejected.", schema({**CID, "id": ID}, {"ttl": {"type": "number", "exclusiveMinimum": 0, "maximum": 3600}}), "attempt.heartbeat"),
    "relay_release": ("Release an attempt without disposing of any uncertain effect.", schema({**CID, "id": ID, "reason": STR}), "attempt.release"),
    "relay_context_reset": ("Invalidate context acknowledgments after context loss or host compaction. Original authority remains intact.", schema({**CID, "reason": STR}), "adapter.reset"),
    "relay_close": ("Close this adapter session, releasing attempts while preserving unknown effects.", schema({**CID, "reason": STR}), "adapter.close"),
}


class LocalClient:
    def __init__(self, home: Path, token_file: Path):
        self.home = home.expanduser().absolute()
        self.token_file = private_file(token_file)
        require(self.token_file.read_text().strip().startswith("rly1."),
                "WORKER_CREDENTIAL_REQUIRED", "MCP must not receive owner.key")

    def call(self, op, payload, command_id=None):
        return call(self.home, self.token_file.read_text().strip(), op, payload, command_id, timeout=30)


class MCPAdapter:
    def __init__(self, client, adapter_id: str):
        self.client = client
        self.adapter_id = adapter_id
        self.session = None
        self.ready = False
        self.initialized = False
        self.identity = ""

    def initialize(self, p: dict) -> dict:
        require(not self.initialized, "MCP_LIFECYCLE", "initialize only once per process")
        require(type(p) is dict and type(p.get("protocolVersion")) is str
                and type(p.get("capabilities")) is dict and type(p.get("clientInfo")) is dict,
                "MCP_PARAMS", "protocolVersion, capabilities and clientInfo required")
        info = p["clientInfo"]
        require(type(info.get("name")) is str and type(info.get("version")) is str,
                "MCP_PARAMS", "clientInfo requires name/version")
        sid = fresh_id("mcp")
        opened = self.client.call("adapter.open", {"id": sid, "adapter": self.adapter_id,
            "client_name": info["name"], "client_version": info["version"]}, "open-" + sid)
        self.session = opened["session"]
        self.identity = opened["identity"]
        self.initialized = True
        return {"protocolVersion": PROTOCOL, "capabilities": {"tools": {"listChanged": False}, "resources": {"subscribe": False, "listChanged": False}},
                "serverInfo": {"name": "agent-relay", "version": __version__},
                "instructions": self.identity + "\n\nRelay: claim -> hydrate -> acknowledge body_hash -> prepare. "
                    "Use stable command_id values. After context loss call relay_context_reset and rehydrate. "
                    "Native host tools are not intercepted. Never retry an UNKNOWN external effect blindly."}

    def tool(self, name: str, arguments: dict) -> dict:
        require(name in TOOL_SPECS and type(arguments) is dict, "MCP_PARAMS", "unknown tool or invalid arguments")
        _, spec, op = TOOL_SPECS[name]
        require(set(spec["required"]) <= arguments.keys() <= spec["properties"].keys(),
                "MCP_PARAMS", "missing or extra tool arguments")
        for key, val in arguments.items():
            typ = spec["properties"][key]["type"]
            valid = (typ == "string" and type(val) is str) or (typ == "object" and type(val) is dict) or (typ == "integer" and type(val) is int) or (typ == "number" and type(val) in (int, float))
            require(valid, "MCP_PARAMS", "invalid tool argument type")
        args = dict(arguments)
        cid = args.pop("command_id", None)
        if name == "relay_status":
            return self.client.call("status", {})
        if name == "relay_ready":
            return self.client.call("work.ready", args)
        if name == "relay_get":
            return self.client.call("get", args)
        binding = {"session": self.session["id"], "epoch": self.session["epoch"]}
        if op.startswith("adapter."):
            result = self.client.call(op, {**binding, **args}, cid)
            if "session" in result:
                self.session = result["session"]
            return result
        if op == "task.claim":
            args["provider"] = "mcp-client"  # replaced by durable session metadata at the gateway
        return self.client.call("adapter.invoke", {**binding, "op": op, "payload": args}, cid)

    def process(self, msg: object) -> dict | None:
        if type(msg) is not dict or msg.get("jsonrpc") != "2.0" or type(msg.get("method")) is not str:
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid JSON-RPC request"}}
        method = msg["method"]
        notification = "id" not in msg
        rid = msg.get("id")
        if not notification and type(rid) not in (int, str):
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "request ID must be string or integer"}}
        params = msg.get("params", {})
        if notification:
            if method == "notifications/initialized" and self.initialized:
                self.ready = True
            # Cancellation of a protocol wait never asserts cancellation of an effect.
            return None
        try:
            require(type(params) is dict, "MCP_PARAMS", "params must be an object")
            if method == "initialize":
                result = self.initialize(params)
            elif method == "ping":
                result = {}
            else:
                require(self.ready, "MCP_LIFECYCLE", "initialize and notifications/initialized must precede operations")
                if method == "tools/list":
                    require(not params, "MCP_PARAMS", "this finite tool list has no pagination cursor")
                    result = {"tools": [{"name": k, "description": d, "inputSchema": s} for k, (d, s, _) in TOOL_SPECS.items()]}
                elif method == "tools/call":
                    require(type(params.get("name")) is str, "MCP_PARAMS", "tool name required")
                    try:
                        value = self.tool(params["name"], params.get("arguments", {}))
                        result = {"content": [{"type": "text", "text": canonical(value).decode()}], "structuredContent": value, "isError": False}
                    except RelayError as exc:
                        value = {"code": exc.code, "message": exc.message}
                        result = {"content": [{"type": "text", "text": canonical(value).decode()}], "isError": True}
                elif method == "resources/list":
                    result = {"resources": [{"uri": "relay://identity", "name": "Agent.md", "mimeType": "text/markdown"}]}
                elif method == "resources/read":
                    require(params.get("uri") == "relay://identity", "MCP_PARAMS", "unknown resource")
                    current = self.client.call("get", {"kind": "source", "id": self.session["identity_source"]})
                    result = {"contents": [{"uri": "relay://identity", "mimeType": "text/markdown", "text": current["text"]}]}
                else:
                    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not supported"}}
            return {"jsonrpc": "2.0", "id": rid, "result": result}
        except RelayError as exc:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32602 if exc.code == "MCP_PARAMS" else -32000,
                    "message": exc.message, "data": {"code": exc.code}}}

    def close(self):
        if self.session and self.session["state"] == "OPEN":
            try:
                self.client.call("adapter.close", {"session": self.session["id"], "epoch": self.session["epoch"],
                    "reason": "stdio EOF; preserve unknown effects"}, fresh_id("close"))
            except (RelayError, OSError):
                # A lost EOF receipt is observable as an open session, not fictitious closure.
                pass


def run(adapter: MCPAdapter, source, sink):
    try:
        while True:
            raw = source.readline(MAX_REQUEST + 1)
            if not raw:
                break
            if len(raw) > MAX_REQUEST:
                reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "message exceeds bounded input"}}
                sink.write(canonical(reply) + b"\n"); sink.flush()
                return 2  # do not parse the remaining tail as another command
            try:
                msg = strict_loads(raw)
                reply = adapter.process(msg)
            except (RelayError, UnicodeError, ValueError):
                reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "invalid JSON"}}
            if reply is not None:
                sink.write(canonical(reply) + b"\n")
                sink.flush()
        return 0
    finally:
        adapter.close()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--home", type=Path)
    group.add_argument("--remote-config", type=Path)
    p.add_argument("--token-file", type=Path)
    p.add_argument("--adapter", required=True, help="owner-registered adapter ID")
    args = p.parse_args(argv)
    if args.home and not args.token_file:
        p.error("--home requires --token-file (worker token only)")
    if args.remote_config and args.token_file:
        p.error("remote config already names the worker token file")
    try:
        client = RemoteClient(args.remote_config) if args.remote_config else LocalClient(args.home, args.token_file)
        return run(MCPAdapter(client, args.adapter), sys.stdin.buffer, sys.stdout.buffer)
    except (RelayError, OSError) as exc:
        print(json.dumps({"error": getattr(exc, "code", "OS_ERROR"), "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
