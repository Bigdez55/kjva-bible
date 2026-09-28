"""Durable, scoped lifecycle for the shipped MCP stdio worker adapter.

The adapter observes its own messages. It does not pretend to intercept a
provider's native shell or see its private context. A delivery acknowledgment
proves possession of the supplied bytes, not model comprehension.
"""
from __future__ import annotations

from importlib.resources import files
import re
from .codec import canonical, digest, ident, integer, number, object_digest, text
from .errors import RelayError, require

ADAPTER_ID = "mcp-stdio-v1"
CAPABILITIES = {
    "identity_entry": "owner-registered Agent.md source",
    "hydration": "scoped durable context plus explicit client hash acknowledgment",
    "tool_interception": "all tools exposed by this adapter pass the Relay gateway",
    "context_reset": "explicit reset invalidates prior context acknowledgments",
    "native_provider_compaction": "NOT_OBSERVED_NOT_CLAIMED",
    "native_provider_tools": "NOT_INTERCEPTED",
    "api_enforcement": "ENFORCED_AT_RELAY",
    "host_enforcement": "COOPERATIVE_TRUSTED_OS_ACCOUNT",
}

ADAPTER_FIELDS = {
    "adapter.register": ({"id", "workflow", "identity_source", "implementation"}, set()),
    "adapter.disable": ({"id", "reason"}, set()),
    "adapter.open": ({"id", "adapter", "client_name", "client_version"}, set()),
    "adapter.invoke": ({"session", "epoch", "op", "payload"}, set()),
    "adapter.acknowledge": ({"session", "epoch", "context", "body_hash"}, set()),
    "adapter.reset": ({"session", "epoch", "reason"}, set()),
    "adapter.close": ({"session", "epoch", "reason"}, set()),
    "peer.register": ({"fingerprint", "grant"}, {"ttl"}),
    "peer.revoke": ({"fingerprint", "reason"}, set()),
}
INVOKABLE = frozenset({
    "task.claim", "work.next", "attempt.heartbeat", "attempt.release",
    "context.hydrate", "action.prepare", "memory.add",
})


def implementation_identity() -> dict:
    """Pin the shipped adapter, not an unverified provider name/version claim."""
    from . import __version__
    paths = ("adapters.py", "mcp.py", "controller.py", "service.py", "network.py")
    hashes = {p: digest(files("agent_relay").joinpath(p).read_bytes()) for p in paths}
    return {"id": ADAPTER_ID, "version": __version__, "files": hashes,
            "sha256": object_digest(hashes), "capabilities": CAPABILITIES}


def fingerprint(value: object) -> str:
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            "INVALID_FINGERPRINT", "expected lowercase SHA-256 of DER certificate")
    return value


class AdapterCommands:
    """Controller mixin. All mutations share the original single transaction."""

    def adapter_session(self, tx, actor, session_id, epoch=None, active=True):
        from .controller import scope
        session = tx.get("adapter_session", ident(session_id))
        scope(actor, session["workflow"])
        require(actor["role"] == "owner" or session["holder"] == actor["id"],
                "FORBIDDEN", "adapter session belongs to another worker")
        spec = tx.get("adapter", session["adapter"])
        if active:
            require(spec["enabled"] and session["state"] == "OPEN", "ADAPTER_HELD", "session or adapter is disabled")
            require(spec["implementation_sha256"] == implementation_identity()["sha256"],
                    "ADAPTER_VERSION", "adapter changed; register and open a new adapter version")
        if epoch is not None:
            require(session["epoch"] == integer(epoch, "epoch", 1, 2**31),
                    "STALE_SESSION", "session reset; read its current epoch and hydrate again")
        return session, spec

    def do_adapter_register(self, tx, actor, now, p):
        from .controller import owner
        owner(actor)
        workflow = self.workflow(tx, actor, p["workflow"])
        require(p["implementation"] == ADAPTER_ID, "UNSUPPORTED_ADAPTER", "only the shipped MCP stdio adapter may be enabled")
        source = tx.get("source", ident(p["identity_source"]))
        require(source["workflow"] == workflow["id"] and source["source_kind"] == "Agent.md",
                "IDENTITY_SOURCE", "select an owner-approved Agent.md source in this workflow")
        identity = implementation_identity()
        spec = tx.put("adapter", ident(p["id"]), workflow["id"], {
            "implementation": ADAPTER_ID, "implementation_sha256": identity["sha256"],
            "version": identity["version"], "identity_source": source["id"],
            "enabled": True, "capabilities": CAPABILITIES, "registered_at": now,
        }, 0)
        return {"adapter": spec}

    def do_adapter_disable(self, tx, actor, now, p):
        from .controller import owner
        owner(actor)
        spec = tx.get("adapter", ident(p["id"]))
        return {"adapter": tx.put("adapter", spec["id"], spec["workflow"], {
            **spec, "enabled": False, "disabled_reason": text(p["reason"], "reason"), "disabled_at": now,
        })}

    def do_adapter_open(self, tx, actor, now, p):
        from .controller import scope
        # Owner credentials never enter provider processes.
        require(actor["role"] == "worker", "WORKER_CREDENTIAL_REQUIRED", "use a scoped worker token, never owner.key")
        spec = tx.get("adapter", ident(p["adapter"]))
        scope(actor, spec["workflow"])
        self.workflow(tx, actor, spec["workflow"])
        require(spec["enabled"], "ADAPTER_HELD", "adapter disabled")
        require(spec["implementation_sha256"] == implementation_identity()["sha256"], "ADAPTER_VERSION", "register this installed adapter version")
        source = tx.get("source", spec["identity_source"])
        body = tx.read_blob(source["blob"]).decode("utf-8")
        session = tx.put("adapter_session", ident(p["id"]), spec["workflow"], {
            "adapter": spec["id"], "holder": actor["id"], "epoch": 1, "state": "OPEN",
            "client_name": text(p["client_name"], "client_name", 128),
            "client_version": text(p["client_version"], "client_version", 128),
            "client_identity_assurance": "CLIENT_REPORTED_NOT_NATIVE_BINARY_ATTESTATION",
            "identity_source": source["id"], "identity_revision": source["rev"],
            "identity_hash": source["blob"], "opened_at": now,
        }, 0)
        return {"session": session, "identity": body, "capabilities": spec["capabilities"]}

    def do_adapter_invoke(self, tx, actor, now, p):
        from .controller import fields
        session, _ = self.adapter_session(tx, actor, p["session"], p["epoch"])
        require(p["op"] in INVOKABLE, "ADAPTER_TOOL_DENIED", "this operation is not a worker adapter tool")
        args = p["payload"]
        fields(p["op"], args)
        if p["op"] in {"task.claim", "work.next"}:
            # Provider labels are observations, not transferable authority.
            args = {**args, "provider": "mcp:" + session["client_name"][:100]}
        elif p["op"] in {"context.hydrate", "action.prepare", "attempt.heartbeat", "attempt.release"}:
            aid = args.get("attempt") if p["op"] in {"context.hydrate", "action.prepare"} else args.get("id")
            attempt = tx.get("attempt", ident(aid))
            require(attempt.get("adapter_session") == session["id"], "SESSION_ATTEMPT", "attempt is not attached to this adapter session")
        result = getattr(self, "do_" + p["op"].replace(".", "_"))(tx, actor, now, args)
        if p["op"] in {"task.claim", "work.next"}:
            attempt = result["attempt"]
            require(attempt["workflow"] == session["workflow"], "FORBIDDEN", "workflow differs from adapter session")
            result["attempt"] = tx.put("attempt", attempt["id"], attempt["workflow"], {**attempt, "adapter_session": session["id"]})
        # Record what was invoked in the same event, never an external tool's success.
        tx.put("adapter_session", session["id"], session["workflow"], {
            **tx.get("adapter_session", session["id"]), "last_tool": p["op"], "last_tool_at": now,
        })
        return result

    def do_adapter_acknowledge(self, tx, actor, now, p):
        session, _ = self.adapter_session(tx, actor, p["session"], p["epoch"])
        context = tx.get("context", ident(p["context"]))
        attempt, task = self.attempt(tx, actor, context["attempt"], now)
        require(attempt.get("adapter_session") == session["id"]
                and context.get("session_epoch") == session["epoch"]
                and context["stamp"] == self.stamp(tx, task),
                "STALE_CONTEXT", "hydrate this current session/attempt again")
        require(p["body_hash"] == context["body_hash"], "DELIVERY_HASH", "acknowledgment does not identify delivered context bytes")
        return {"context": tx.put("context", context["id"], context["workflow"], {
            **context, "acknowledged_epoch": session["epoch"], "acknowledged_at": now,
            "delivery": "CLIENT_HASH_ACKNOWLEDGED_NOT_COMPREHENSION",
        })}

    def do_adapter_reset(self, tx, actor, now, p):
        session, _ = self.adapter_session(tx, actor, p["session"], p["epoch"])
        return {"session": tx.put("adapter_session", session["id"], session["workflow"], {
            **session, "epoch": session["epoch"] + 1, "reset_reason": text(p["reason"], "reason"), "reset_at": now,
        }), "requires_rehydration": True, "authority_compacted": False}

    def do_adapter_close(self, tx, actor, now, p):
        session, _ = self.adapter_session(tx, actor, p["session"], p["epoch"], active=False)
        for attempt in tx.scan("attempt", session["workflow"]):
            if attempt.get("adapter_session") == session["id"] and attempt["status"] == "ACTIVE":
                self.do_attempt_release(tx, actor, now, {"id": attempt["id"], "reason": "adapter closed; unresolved effects remain held"})
        return {"session": tx.put("adapter_session", session["id"], session["workflow"], {
            **session, "state": "CLOSED", "epoch": session["epoch"] + 1,
            "close_reason": text(p["reason"], "reason"), "closed_at": now,
        })}

    def do_peer_register(self, tx, actor, now, p):
        from .controller import owner
        owner(actor)
        grant = tx.get("grant", ident(p["grant"]))
        require(not grant["revoked"] and grant["expires"] > now, "AUTH", "grant is not active")
        fp = fingerprint(p["fingerprint"])
        expires = min(grant["expires"], now + number(p.get("ttl", 86400), "ttl", 1, 86400 * 30))
        return {"peer": tx.put("peer", fp, grant["workflow"], {"grant": grant["id"], "expires": expires, "revoked": False}, 0)}

    def do_peer_revoke(self, tx, actor, now, p):
        from .controller import owner
        owner(actor)
        peer = tx.get("peer", fingerprint(p["fingerprint"]))
        return {"peer": tx.put("peer", peer["id"], peer["workflow"], {
            **peer, "revoked": True, "reason": text(p["reason"], "reason"), "revoked_at": now,
        })}
