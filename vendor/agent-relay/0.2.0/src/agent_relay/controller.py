"""Deterministic command admission and provider-independent work continuity.

Workers can claim, hydrate, heartbeat, release and prepare approved work. Only
an operator/dispatcher can register authority, run effects, verify or accept it.
No worker-supplied PASS and no transcript is an acceptance decision.
"""
from __future__ import annotations
import base64
import json
from pathlib import Path
import secrets
from typing import Any
from .codec import (canonical, digest, ident, integer, number, object_digest, overlaps,
                    relpath, resource, string_list, text, unb64)
from .errors import RelayError, require
from .store import Store, Transaction
from .adapters import AdapterCommands, ADAPTER_FIELDS

SETTLED = {"APPLIED", "NOT_APPLIED", "PARTIAL"}
# Reject misspelled/extra fields rather than silently dropping an obligation.
FIELDS = {
    "workflow.create": ({"id", "directive"}, {"constraints"}),
    "workflow.revise": ({"id", "expected_rev", "directive", "reason"}, set()),
    "workflow.cancel": ({"id", "reason"}, set()),
    "workflow.settle_cancel": ({"id"}, set()),
    "requirement.add": ({"id", "workflow", "text"}, set()),
    "requirement.dispose": ({"id", "decision"}, set()),
    "decision.create": ({"id", "workflow", "target_kind", "target_id", "target_rev", "operation", "reason"}, {"ttl"}),
    "source.put": ({"id", "workflow", "text", "source_kind", "expected_rev"}, set()),
    "memory.add": ({"id", "workflow", "text", "origin"}, set()),
    "grant.create": ({"id", "workflow"}, {"ttl"}),
    "grant.revoke": ({"id"}, set()),
    "repo.register": ({"id", "workflow", "root"}, {"exclude"}),
    "repo.observe": ({"id", "revision"}, set()),
    "tool.register": ({"id", "workflow", "argv", "repo", "resources", "reason"}, {"timeout", "environment", "allow_stdin"}),
    "task.create": ({"id", "workflow", "title", "requirements", "resources"}, {"deps", "repos", "tools", "verifiers"}),
    "task.reopen": ({"id", "decision"}, set()),
    "task.claim": ({"id", "provider"}, {"ttl"}),
    "work.next": ({"workflow", "provider"}, {"ttl"}),
    "attempt.heartbeat": ({"id"}, {"ttl"}),
    "attempt.release": ({"id", "reason"}, set()),
    "context.hydrate": ({"attempt"}, {"budget_bytes"}),
    "action.prepare": ({"id", "attempt", "context", "type", "args"}, set()),
    "action.start": ({"id"}, set()),
    "action.receipt": ({"id", "receipt_id", "outcome", "details"}, set()),
    "action.resolve": ({"id", "decision", "outcome", "proof"}, set()),
    "task.accept": ({"id", "candidate", "evidence"}, set()),
    "workflow.accept": ({"id"}, set()),
    "snapshot.create": (set(), set()),
    "restore.resume": ({"original_authority_fenced", "reconciliation_report"}, set()),
}

FIELDS.update(ADAPTER_FIELDS)


def owner(actor: dict) -> None:
    require(actor["role"] == "owner", "FORBIDDEN", "operator authority required")


def scope(actor: dict, workflow: str) -> None:
    require(actor["role"] == "owner" or actor["workflow"] == workflow, "FORBIDDEN", "cross-workflow access denied")


def fields(op: str, payload: dict) -> None:
    require(op in FIELDS, "UNKNOWN_COMMAND", op)
    required, optional = FIELDS[op]
    require(type(payload) is dict and required <= payload.keys()
            and payload.keys() <= required | optional, "INVALID_FIELDS",
            f"{op}: required={sorted(required)} optional={sorted(optional)}")


def fresh_id(prefix: str) -> str:
    return prefix + "-" + secrets.token_hex(12)


class Controller(AdapterCommands):
    def __init__(self, store: Store):
        self.store = store

    def command(self, token: str, command_id: str, op: str, payload: dict) -> dict:
        fields(op, payload)
        return self.store.command(token, command_id, op, payload,
                                  lambda tx, a, now: getattr(self, "do_" + op.replace(".", "_"))(tx, a, now, payload))

    def query(self, token: str, op: str, payload: dict) -> dict:
        require(type(payload) is dict, "INVALID_FIELDS", "query payload must be an object")
        def read(tx, actor):
            if op == "status":
                permitted = payload.get("workflow")
                if actor["role"] != "owner":
                    permitted = permitted or actor["workflow"]
                    scope(actor, permitted)
                workflows = tx.scan("workflow", permitted)
                tasks = tx.scan("task", permitted)
                actions = tx.scan("action", permitted)
                attempts = tx.scan("attempt", permitted)
                now = self.store.clock()
                return {"workflows": workflows, "tasks": tasks,
                        "open_actions": [x for x in actions if self.unresolved(x)],
                        "active_attempts": [x for x in attempts if x["status"] == "ACTIVE" and x["expires"] > now],
                        "event_cursor": tx.conn.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0]}
            if op == "get":
                kind, id = ident(payload.get("kind")), ident(payload.get("id"))
                require(kind in {"task", "workflow", "source", "requirement", "memory", "action", "attempt", "context", "candidate", "evidence", "decision", "verifier", "receipt", "quarantine", "verification_run", "adapter", "adapter_session", "migration"},
                        "FORBIDDEN", "object type not exposed")
                obj = tx.get(kind, id)
                scope(actor, obj["workflow"])
                # Context bodies and evidence blobs are scoped; arbitrary blob reads are NOT an API.
                if kind == "context":
                    obj["body"] = json.loads(tx.read_blob(obj["body_hash"]))
                if kind == "source" or kind == "memory":
                    obj["text"] = tx.read_blob(obj["blob"]).decode("utf-8")
                if kind == "evidence":
                    obj["report"] = json.loads(tx.read_blob(obj["report_blob"]))
                if kind == "candidate" and actor["role"] != "owner":
                    obj = {k:v for k,v in obj.items() if k != "roots"}
                return obj
            if op == "work.ready":
                workflow = ident(payload.get("workflow"))
                scope(actor, workflow)
                now = self.store.clock()
                return {"tasks": [{"id": t["id"], "reason": self.block_reason(tx,t,now)} for t in tx.scan("task", workflow)]}
            raise RelayError("UNKNOWN_QUERY", op)
        return self.store.read(token, read)

    @staticmethod
    def unresolved(action: dict) -> bool:
        return action["dispatch"] != "CANCELED_BEFORE_SEND" and action["outcome"] not in SETTLED

    def workflow(self, tx, actor, id, active=True):
        w = tx.get("workflow", ident(id))
        scope(actor, w["id"])
        if active:
            require(w["status"] == "ACTIVE", "WORKFLOW_HELD", w["status"])
        return w

    def attempt(self, tx, actor, id, now, current=True):
        a = tx.get("attempt", ident(id))
        scope(actor, a["workflow"])
        require(actor["role"] == "owner" or a["holder"] == actor["id"], "FORBIDDEN", "attempt belongs to another worker")
        t = tx.get("task", a["task"])
        if current:
            if a.get("adapter_session"):
                self.adapter_session(tx, actor, a["adapter_session"])
            self.workflow(tx, actor, a["workflow"])
            if a["holder"] != "owner":
                grant = tx.get("grant", a["holder"])
                require(not grant["revoked"] and grant["expires"] > now, "AUTH", "attempt holder was revoked or expired")
            require(a["status"] == "ACTIVE" and a["expires"] > now
                    and t["active_attempt"] == a["id"] and t["fence"] == a["fence"],
                    "STALE_FENCE", "attempt no longer owns this task")
            for r, epoch in a["leases"].items():
                lease = tx.get("lease", digest(r.encode()))
                require(lease["holder"] == a["id"] and lease["epoch"] == epoch
                        and lease["expires"] > now, "STALE_FENCE", r)
        return a, t

    def stamp(self, tx: Transaction, task: dict) -> str:
        w = tx.get("workflow", task["workflow"])
        return object_digest({"intent_revision": w["intent_revision"], "workflow_status": w["status"],
                              "task": task["id"], "spec_revision": task["spec_revision"],
                              "requirements": [(i, tx.get("requirement",i)["text"], tx.get("requirement",i)["decision"]) for i in task["requirements"]],
                              "sources": [(x["id"],x["rev"]) for x in tx.scan("source",task["workflow"])],
                              "repos": [(r,tx.get("repo",r)["observed"]) for r in task["repos"]],
                              "tools": [(r,tx.get("tool",r)["rev"]) for r in task["tools"]],
                              "verifiers": [(r,tx.get("verifier",r)["rev"]) for r in task["verifiers"]],
                              "deps": [(d,tx.get("task",d)["spec_revision"],tx.get("task",d).get("accepted_candidate")) for d in task["deps"]]})

    def block_reason(self, tx, task, now):
        if tx.get("workflow",task["workflow"])["status"] != "ACTIVE":
            return "WORKFLOW_HELD"
        if task["status"] == "ACCEPTED":
            return "ACCEPTED" if task.get("accepted_stamp") == self.stamp(tx,task) else "ACCEPTED_STALE"
        if task["status"] == "CANCELED":
            return "CANCELED"
        for d in task["deps"]:
            dep = tx.get("task",d)
            if dep["status"] != "ACCEPTED" or dep.get("accepted_stamp") != self.stamp(tx,dep):
                return "DEPENDENCY"
        if task["active_attempt"]:
            a = tx.get("attempt",task["active_attempt"])
            if a["status"] == "ACTIVE" and a["expires"] > now:
                return "LEASED"
        # These scans are over active domain records, never historical blobs or events.
        for lease in tx.active_leases(now):
            if lease["expires"] > now and any(overlaps(lease["resource"],r) for r in task["resources"]):
                return "RESOURCE_BUSY"
        for action in tx.unresolved_actions():
            if self.unresolved(action) and any(overlaps(x,y) for x in action["resources"] for y in task["resources"]):
                return "UNKNOWN_OR_PREPARED_EFFECT"
        return None

    def decision(self, tx, actor, id, kind, target, operation, now):
        owner(actor)
        d = tx.get("decision",ident(id))
        require(d["workflow"] == target["workflow"] and d["target_kind"] == kind
                and d["target_id"] == target["id"] and d["target_rev"] == target["rev"]
                and d["operation"] == operation and not d["used"] and d["expires"] > now,
                "INVALID_DECISION", "decision must be unused, current, unexpired and scoped to this exact operation/revision")
        tx.put("decision", d["id"], d["workflow"], {**d,"used": True})
        return d

    def do_workflow_create(self, tx, a, now, p):
        owner(a)
        id = ident(p["id"])
        w = tx.put("workflow", id, id, {"directive": text(p["directive"],"directive"),
                   "constraints": string_list(p.get("constraints",[]),"constraints"),
                   "intent_revision": 1, "status": "ACTIVE", "created_at": now}, expected=0)
        return {"workflow": w}

    def do_workflow_revise(self, tx, a, now, p):
        owner(a)
        w = self.workflow(tx,a,p["id"])
        require(w["rev"] == integer(p["expected_rev"],"expected_rev",1,2**31), "STALE_REVISION", w["id"])
        reason = text(p["reason"],"reason")
        d = tx.put("decision",fresh_id("decision"),w["id"],{"target_kind":"workflow","target_id":w["id"],
                   "target_rev":w["rev"],"operation":"revise","reason":reason,"expires":now,"used":True},0)
        return {"workflow":tx.put("workflow",w["id"],w["id"],{**w,"directive":text(p["directive"],"directive"),
                    "intent_revision":w["intent_revision"]+1,"revision_decision":d["id"]})}

    def do_workflow_cancel(self, tx, a, now, p):
        owner(a)
        w = self.workflow(tx,a,p["id"])
        reason = text(p["reason"],"reason")
        for action in tx.scan("action",w["id"]):
            if action["dispatch"] == "PREPARED":
                tx.put("action",action["id"],w["id"],{**action,"dispatch":"CANCELED_BEFORE_SEND","outcome":"NOT_APPLIED"})
                out = tx.get("outbox",action["id"])
                tx.put("outbox",action["id"],w["id"],{**out,"status":"CANCELED"})
        return {"workflow":tx.put("workflow",w["id"],w["id"],{**w,"status":"CANCEL_REQUESTED","cancel_reason":reason})}

    def do_workflow_settle_cancel(self, tx, a, now, p):
        owner(a)
        w = self.workflow(tx,a,p["id"],False)
        require(w["status"] == "CANCEL_REQUESTED","STATE", "cancellation was not requested")
        require(not any(self.unresolved(x) for x in tx.scan("action",w["id"])),"UNKNOWN_EFFECT","unresolved effects remain")
        require(not any(x["status"] == "ACTIVE" and x["expires"] > now for x in tx.scan("attempt",w["id"])),
                "ACTIVE_EXECUTORS","release/expire attempts after observing process termination")
        for t in tx.scan("task",w["id"]):
            if t["status"] != "ACCEPTED":
                tx.put("task",t["id"],w["id"],{**t,"status":"CANCELED","active_attempt":None})
        return {"workflow":tx.put("workflow",w["id"],w["id"],{**w,"status":"CANCELED"})}

    def do_requirement_add(self, tx, a, now, p):
        owner(a)
        w=self.workflow(tx,a,p["workflow"])
        return {"requirement":tx.put("requirement",ident(p["id"]),w["id"],
                                    {"text":text(p["text"],"requirement"),"status":"OPEN","decision":None},0)}

    def do_requirement_dispose(self, tx, a, now, p):
        owner(a)
        r=tx.get("requirement",ident(p["id"]))
        d=self.decision(tx,a,p["decision"],"requirement",r,"cancel",now)
        return {"requirement":tx.put("requirement",r["id"],r["workflow"],{**r,"status":"CANCELED","decision":d["id"]})}

    def do_decision_create(self, tx, a, now, p):
        owner(a)
        w=self.workflow(tx,a,p["workflow"],False)
        kind=text(p["target_kind"],"target_kind",64)
        require(kind in {"task","requirement","action"},"INVALID_FIELD","unsupported decision target")
        target=tx.get(kind,ident(p["target_id"]))
        require(target["workflow"]==w["id"] and target["rev"]==integer(p["target_rev"],"target_rev",1,2**31),"STALE_REVISION","decision target")
        op=text(p["operation"],"operation",64)
        require((kind,op) in {("task","reopen"),("requirement","cancel"),("action","resolve")},"INVALID_FIELD","unsupported decision operation")
        return {"decision":tx.put("decision",ident(p["id"]),w["id"],{"target_kind":kind,"target_id":target["id"],
                      "target_rev":target["rev"],"operation":op,"reason":text(p["reason"],"reason"),
                      "expires":now+number(p.get("ttl",3600),"ttl",0.01,86400),"used":False},0)}

    def do_source_put(self, tx, a, now, p):
        owner(a)
        w=self.workflow(tx,a,p["workflow"])
        kind=text(p["source_kind"],"source_kind",64)
        require(kind in {"Agent.md","ADR","layout","contract","policy","reference"},"INVALID_FIELD","source kind")
        id=ident(p["id"])
        old=tx.get("source",id,True)
        require(old is None or old["workflow"]==w["id"],"FORBIDDEN","cross-workflow replacement")
        blob=tx.blob(text(p["text"],"source",262144).encode())
        return {"source":tx.put("source",id,w["id"],{"blob":blob,"source_kind":kind,"authority":"OWNER_APPROVED","at":now},
                                 integer(p["expected_rev"],"expected_rev",0,2**31))}

    def do_memory_add(self, tx, a, now, p):
        w=self.workflow(tx,a,p["workflow"])
        return {"memory":tx.put("memory",ident(p["id"]),w["id"],{"blob":tx.blob(text(p["text"],"memory").encode()),
                   "origin":text(p["origin"],"origin",1024),"authority":"UNTRUSTED_DATA","at":now},0)}

    def do_grant_create(self, tx, a, now, p):
        owner(a)
        w=self.workflow(tx,a,p["workflow"])
        id=ident(p["id"])
        require("." not in id,"INVALID_ID","grant ID cannot contain dot")
        g=tx.put("grant",id,w["id"],{"expires":now+number(p.get("ttl",86400),"ttl",1,86400*30),"revoked":False},0)
        # The raw worker token is derived after this command; never persisted in events.
        return {"grant":g}

    def issue_token(self, owner_token: str, grant_id: str) -> str:
        def read(tx,a):
            owner(a)
            g=tx.get("grant",ident(grant_id))
            require(not g["revoked"] and g["expires"]>self.store.clock(),"AUTH","grant expired/revoked")
            gen=tx.conn.execute("SELECT value FROM meta WHERE key='generation'").fetchone()[0]
            return self.store.worker_token(g,gen)
        return self.store.read(owner_token,read)

    def do_grant_revoke(self, tx, a, now, p):
        owner(a)
        g=tx.get("grant",ident(p["id"]))
        return {"grant":tx.put("grant",g["id"],g["workflow"],{**g,"revoked":True})}

    def do_repo_register(self, tx, a, now, p):
        owner(a)
        w=self.workflow(tx,a,p["workflow"])
        root=Path(text(p["root"],"root",4096)).expanduser().absolute()
        require(root.is_dir() and not root.is_symlink(),"REPO_PATH","repository root must be an existing real directory")
        root=root.resolve()
        require(not root.is_relative_to(self.store.home) and not self.store.home.is_relative_to(root),
                "REPO_PATH","control store must be outside every registered working tree")
        for registered in tx.scan("repo"):
            other=Path(registered["root"])
            left=str(root).casefold().rstrip("/");right=str(other).casefold().rstrip("/")
            require(not (left==right or left.startswith(right+"/") or right.startswith(left+"/")), "REPO_OVERLAP", "register one authority scope per working tree; use separate worktrees for distinct workflows")
        excludes=[relpath(x) for x in string_list(p.get("exclude",[]),"exclude")]
        return {"repo":tx.put("repo",ident(p["id"]),w["id"],{"root":str(root),"exclude":excludes,"observed":None},0)}

    def do_repo_observe(self, tx, a, now, p):
        owner(a)
        r=tx.get("repo",ident(p["id"]))
        self.workflow(tx,a,r["workflow"])
        return {"repo":tx.put("repo",r["id"],r["workflow"],{**r,"observed":text(p["revision"],"revision",4096)})}

    def do_tool_register(self, tx, a, now, p):
        owner(a)
        from .execution import pin_command, clean_environment
        w=self.workflow(tx,a,p["workflow"])
        repo=tx.get("repo",ident(p["repo"]))
        require(repo["workflow"]==w["id"],"FORBIDDEN","tool repository")
        argv=p["argv"]
        require(type(argv) is list and 0 < len(argv) <= 128 and all(type(x) is str and "\x00" not in x and len(x) <= 8192 for x in argv), "INVALID_FIELD", "argv must be a bounded list of strings")
        pins=pin_command(argv,Path(repo["root"]))
        env=clean_environment(p.get("environment",{}))
        resources=[resource(x) for x in string_list(p["resources"],"resources")]
        require(bool(resources),"INVALID_FIELD","declare command resources")
        allow=p.get("allow_stdin",False)
        require(type(allow) is bool,"INVALID_FIELD","allow_stdin")
        return {"tool":tx.put("tool",ident(p["id"]),w["id"],{"argv":pins["argv"],"pins":pins,"repo":repo["id"],
                   "resources":resources,"environment":env,"timeout":number(p.get("timeout",60),"timeout",0.1,3600),
                   "allow_stdin":allow,"reason":text(p["reason"],"reason"),"enforcement":"COOPERATIVE_EXEC_PROCESS"},0)}

    def do_task_create(self, tx, a, now, p):
        owner(a)
        w=self.workflow(tx,a,p["workflow"])
        data={"title":text(p["title"],"title",8192),"status":"OPEN","spec_revision":1,"fence":0,
              "active_attempt":None,"dispatch_count":0,"created_at":now}
        for key,kind in (("requirements","requirement"),("deps","task"),("repos","repo"),("tools","tool"),("verifiers","verifier")):
            vals=[ident(x,key) for x in string_list(p.get(key,[]),key)]
            for v in vals:
                require(tx.get(kind,v)["workflow"]==w["id"],"INVALID_REFERENCE",f"{key}:{v}")
            data[key]=vals
        require(bool(data["requirements"]),"INVALID_FIELD","task must preserve at least one requirement")
        data["resources"]=[resource(x) for x in string_list(p["resources"],"resources")]
        require(bool(data["resources"]),"INVALID_FIELD","task needs scoped resources")
        return {"task":tx.put("task",ident(p["id"]),w["id"],data,0)}

    def do_task_reopen(self, tx, a, now, p):
        owner(a)
        t=tx.get("task",ident(p["id"]))
        require(t["status"]=="ACCEPTED","STATE","only accepted work is reopened")
        d=self.decision(tx,a,p["decision"],"task",t,"reopen",now)
        for id in t["requirements"]:
            r=tx.get("requirement",id)
            if r["status"]=="SATISFIED":
                tx.put("requirement",id,r["workflow"],{**r,"status":"OPEN"})
        w=tx.get("workflow",t["workflow"])
        require(w["status"] in {"ACTIVE","ACCEPTED"},"STATE","workflow is canceled")
        if w["status"]=="ACCEPTED":
            tx.put("workflow",w["id"],w["id"],{**w,"status":"ACTIVE"})
        return {"task":tx.put("task",t["id"],t["workflow"],{**t,"status":"OPEN","spec_revision":t["spec_revision"]+1,
                  "accepted_candidate":None,"accepted_stamp":None,"active_attempt":None,"reopen_decision":d["id"]})}

    def do_task_claim(self, tx, a, now, p):
        t=tx.get("task",ident(p["id"]))
        scope(a,t["workflow"])
        reason=self.block_reason(tx,t,now)
        require(reason is None,"NOT_READY",reason or "")
        provider=text(p["provider"],"provider",128)
        expires=now+number(p.get("ttl",300),"ttl",0.01,3600)
        if t["active_attempt"]:
            old=tx.get("attempt",t["active_attempt"])
            tx.put("attempt",old["id"],old["workflow"],{**old,"status":"EXPIRED"})
        id=fresh_id("attempt")
        fences={}
        for r in sorted(t["resources"]):
            key=digest(r.encode())
            old=tx.get("lease",key,True)
            epoch=old["epoch"]+1 if old else 1
            tx.put("lease",key,t["workflow"],{"resource":r,"holder":id,"epoch":epoch,"expires":expires})
            fences[r]=epoch
        attempt=tx.put("attempt",id,t["workflow"],{"task":t["id"],"holder":a["id"],"provider":provider,
                      "fence":t["fence"]+1,"leases":fences,"expires":expires,"status":"ACTIVE","started":now},0)
        tx.put("task",t["id"],t["workflow"],{**t,"status":"RUNNING","active_attempt":id,"fence":attempt["fence"],
                 "dispatch_count":t["dispatch_count"]+1})
        return {"attempt":attempt}

    def do_work_next(self, tx, a, now, p):
        w=self.workflow(tx,a,p["workflow"])
        tasks=sorted(tx.scan("task",w["id"]),key=lambda t:(t["dispatch_count"],t["created_at"],t["id"]))
        for t in tasks:
            if self.block_reason(tx,t,now) is None:
                return self.do_task_claim(tx,a,now,{"id":t["id"],"provider":p["provider"],"ttl":p.get("ttl",300)})
        raise RelayError("NO_READY_TASK","no eligible task; unrelated workflows remain independent")

    def do_attempt_heartbeat(self, tx, a, now, p):
        attempt,t=self.attempt(tx,a,p["id"],now)
        expires=now+number(p.get("ttl",300),"ttl",0.01,3600)
        for r in attempt["leases"]:
            key=digest(r.encode()); lease=tx.get("lease",key)
            tx.put("lease",key,t["workflow"],{**lease,"expires":expires})
        return {"attempt":tx.put("attempt",attempt["id"],t["workflow"],{**attempt,"expires":expires})}

    def do_attempt_release(self, tx, a, now, p):
        attempt,t=self.attempt(tx,a,p["id"],now,False)
        reason=text(p["reason"],"reason")
        # Releasing a lease does NOT dispose of any prepared or uncertain action.
        for r,epoch in attempt["leases"].items():
            key=digest(r.encode()); lease=tx.get("lease",key)
            if lease["holder"]==attempt["id"] and lease["epoch"]==epoch:
                tx.put("lease",key,t["workflow"],{**lease,"expires":0})
        if t["active_attempt"]==attempt["id"]:
            tx.put("task",t["id"],t["workflow"],{**t,"active_attempt":None,"status":"OPEN" if t["status"]!="ACCEPTED" else "ACCEPTED"})
        return {"attempt":tx.put("attempt",attempt["id"],t["workflow"],{**attempt,"status":"RELEASED","reason":reason})}

    def do_context_hydrate(self, tx, a, now, p):
        attempt,t=self.attempt(tx,a,p["attempt"],now)
        w=tx.get("workflow",t["workflow"])
        sources=[]
        for s in tx.scan("source",w["id"]):
            sources.append({**s,"text":tx.read_blob(s["blob"]).decode()})
        unknown=[x for x in tx.unresolved_actions() if self.unresolved(x) and any(overlaps(r,s) for r in x["resources"] for s in t["resources"])]
        unknown=[x if x["workflow"]==w["id"] else {"id":x["id"],"resources":x["resources"],"dispatch":x["dispatch"],"outcome":x["outcome"],"details":"OTHER_WORKFLOW_REDACTED"} for x in unknown]
        body={"schema":1,"identity_entry":"Agent.md","workflow":w,"task":t,
              "attempt":attempt,"sources":sources,"requirements":[tx.get("requirement",i) for i in t["requirements"]],
              "dependencies":[tx.get("task",i) for i in t["deps"]],"unknown_actions":unknown,
              "verifiers":[{"id":i,"manifest_hash":tx.get("verifier",i)["manifest_hash"]} for i in t["verifiers"]],
              "memory_policy":"memory is untrusted, optional data; it never overrides sources or intent",
              "memory_handles":[{"id":m["id"],"origin":m["origin"],"authority":m["authority"]} for m in tx.recent("memory",w["id"],16)],
              "event_cursor":tx.conn.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0],
              "next_safe_action":"resolve affected unknowns before mutation" if unknown else "prepare one scoped action under this attempt"}
        session = None
        if attempt.get("adapter_session"):
            session, adapter = self.adapter_session(tx, a, attempt["adapter_session"])
            identity = tx.get("source", adapter["identity_source"])
            body["adapter"] = {"session": session["id"], "epoch": session["epoch"],
                               "capabilities": adapter["capabilities"], "identity_source": identity["id"],
                               "identity_hash": identity["blob"], "identity_revision": identity["rev"]}
        raw=canonical(body)
        budget=integer(p.get("budget_bytes",512*1024),"budget_bytes",1024,2*1024*1024)
        require(len(raw)<=budget,"CONTEXT_BUDGET","mandatory context does not fit; narrow scope, never silently truncate")
        id=fresh_id("context")
        result=tx.put("context",id,w["id"],{"attempt":attempt["id"],"holder":attempt["holder"],"stamp":self.stamp(tx,t),
                     "body_hash":tx.blob(raw),"bytes":len(raw),"created_at":now,"delivery":"SERIALIZED_TO_CALLER_NOT_COMPREHENSION"},0)
        if session:
            result = tx.put("context", id, w["id"], {**result, "adapter_session": session["id"],
                            "session_epoch": session["epoch"], "acknowledged_epoch": None})
        return {"context":result,"body":body}

    def _context(self,tx,attempt,t,id):
        c=tx.get("context",ident(id))
        require(c["attempt"]==attempt["id"] and c["holder"]==attempt["holder"] and c["stamp"]==self.stamp(tx,t),
                "STALE_CONTEXT","hydrate this attempt again; authority/source/dependency versions changed")
        if attempt.get("adapter_session"):
            session = tx.get("adapter_session", attempt["adapter_session"])
            require(c.get("adapter_session") == session["id"] and c.get("session_epoch") == session["epoch"],
                    "STALE_CONTEXT", "adapter context reset; hydrate again")
            require(c.get("acknowledged_epoch") == session["epoch"], "CONTEXT_NOT_ACKNOWLEDGED", "acknowledge the delivered context hash before a consequential action")
        tx.read_blob(c["body_hash"])
        return c

    def do_action_prepare(self, tx, a, now, p):
        attempt,t=self.attempt(tx,a,p["attempt"],now)
        context=self._context(tx,attempt,t,p["context"])
        for d in t["deps"]:
            dep=tx.get("task",d)
            require(dep["status"]=="ACCEPTED" and dep.get("accepted_stamp")==self.stamp(tx,dep),"DEPENDENCY","upstream no longer accepted")
        kind=p["type"]; args=p["args"]
        require(type(args) is dict,"INVALID_FIELD","args must be an object")
        if kind=="file.write":
            require(set(args)=={"repo","path","expected_sha256","data_b64"},"INVALID_FIELDS","file.write args")
            repo=tx.get("repo",ident(args["repo"]))
            require(repo["id"] in t["repos"] and repo["workflow"]==t["workflow"],"FORBIDDEN","repository outside task")
            path=relpath(args["path"])
            expected=args["expected_sha256"]
            require(type(expected) is str and (expected=="ABSENT" or len(expected)==64 and all(x in "0123456789abcdef" for x in expected)),"INVALID_FIELD","expected_sha256")
            raw=unb64(args["data_b64"])
            data={"repo":repo["id"],"path":path,"expected_sha256":expected,"blob":tx.blob(raw)}
            resources=[resource(f"repo/{repo['id']}/{path}")]
        elif kind=="command":
            require(set(args)<={"tool","stdin"} and "tool" in args,"INVALID_FIELDS","command args")
            tool=tx.get("tool",ident(args["tool"]))
            require(tool["id"] in t["tools"] and tool["workflow"]==t["workflow"],"FORBIDDEN","tool not allowed")
            stdin=args.get("stdin","")
            require(type(stdin) is str and len(stdin.encode())<=262144,"INVALID_FIELD","stdin")
            require(not stdin or tool["allow_stdin"],"FORBIDDEN","tool does not permit stdin")
            data={"tool":tool["id"],"tool_rev":tool["rev"],"stdin_blob":tx.blob(stdin.encode())}
            resources=tool["resources"]
        else:
            raise RelayError("UNSUPPORTED_EFFECT","supported: file.write, command; no arbitrary HTTP/retry adapters")
        require(all(any(r==allowed or r.startswith(allowed+"/") for allowed in t["resources"]) for r in resources),"RESOURCE_SCOPE","action exceeds acquired resources")
        for x in tx.unresolved_actions():
            require(not (self.unresolved(x) and any(overlaps(r,s) for r in resources for s in x["resources"])),
                    "UNKNOWN_EFFECT","an unresolved action holds the affected resource")
        id=ident(p["id"])
        action=tx.put("action",id,t["workflow"],{"task":t["id"],"attempt":attempt["id"],"context":context["id"],"stamp":context["stamp"],
                    "type":kind,"args":data,"request_hash":object_digest({"type":kind,"args":data}),"resources":resources,
                    "dispatch":"PREPARED","outcome":"UNKNOWN","prepared_at":now,"receipt_ids":[]},0)
        tx.put("outbox",id,t["workflow"],{"action":id,"status":"PENDING","prepared_at":now},0)
        return {"action":action}

    def do_action_start(self, tx, a, now, p):
        owner(a)
        action=tx.get("action",ident(p["id"]))
        require(action["dispatch"]=="PREPARED","DISPATCH_HELD","sending already began or action canceled; reconcile instead of retry")
        attempt,t=self.attempt(tx,a,action["attempt"],now)
        self._context(tx,attempt,t,action["context"])
        action=tx.put("action",action["id"],t["workflow"],{**action,"dispatch":"SENDING","started_at":now})
        out=tx.get("outbox",action["id"])
        tx.put("outbox",action["id"],t["workflow"],{**out,"status":"CLAIMED"})
        return {"action":action}

    def do_action_receipt(self, tx, a, now, p):
        owner(a)
        action=tx.get("action",ident(p["id"]))
        require(action["dispatch"] in {"SENDING","ACKNOWLEDGED"},"STATE","no dispatched action exists")
        outcome=p["outcome"]
        require(outcome in SETTLED|{"UNKNOWN"},"INVALID_FIELD","outcome")
        require(type(p["details"]) is dict and len(canonical(p["details"]))<=262144,"INVALID_FIELD","details")
        id=ident(p["receipt_id"])
        payload_hash=object_digest({"action":action["id"],"outcome":outcome,"details":p["details"]})
        existing=tx.get("receipt",id,True)
        conflict=(existing is not None and existing["payload_hash"]!=payload_hash) or (action["outcome"] in SETTLED and action["outcome"]!=outcome)
        if conflict:
            q=tx.put("quarantine",fresh_id("quarantine"),action["workflow"],{"receipt_id":id,"action":action["id"],
                     "payload_hash":payload_hash,"reason":"CONFLICTING_RECEIPT","at":now},0)
            return {"quarantined":q,"action":action}
        if existing:
            return {"receipt":existing,"action":action}
        receipt=tx.put("receipt",id,action["workflow"],{"action":action["id"],"outcome":outcome,"payload_hash":payload_hash,
                       "details":p["details"],"at":now,"observer":"operator-or-trusted-dispatcher"},0)
        action=tx.put("action",action["id"],action["workflow"],{**action,"dispatch":"ACKNOWLEDGED","outcome":outcome,
                        "receipt_ids":action["receipt_ids"]+[id]})
        out=tx.get("outbox",action["id"])
        tx.put("outbox",action["id"],action["workflow"],{**out,"status":"SETTLED" if outcome in SETTLED else "UNKNOWN"})
        return {"receipt":receipt,"action":action}

    def do_action_resolve(self, tx, a, now, p):
        owner(a)
        action=tx.get("action",ident(p["id"]))
        require(self.unresolved(action),"STATE","action already settled")
        d=self.decision(tx,a,p["decision"],"action",action,"resolve",now)
        require(p["outcome"] in SETTLED,"INVALID_FIELD","resolution outcome")
        proof=text(p["proof"],"proof")
        result=tx.put("action",action["id"],action["workflow"],{**action,"outcome":p["outcome"],
                      "dispatch":"ACKNOWLEDGED" if action["dispatch"]!="PREPARED" else "CANCELED_BEFORE_SEND",
                      "resolution_decision":d["id"],"resolution_proof":proof,"resolution_assurance":"OPERATOR_DISPOSITION_NOT_TEST_PROOF"})
        out=tx.get("outbox",action["id"])
        tx.put("outbox",action["id"],action["workflow"],{**out,"status":"RESOLVED"})
        return {"action":result}

    def do_task_accept(self, tx, a, now, p):
        owner(a)
        from .workspace import verify_live_candidate
        t=tx.get("task",ident(p["id"]))
        self.workflow(tx,a,t["workflow"])
        require(t["status"]!="ACCEPTED","STATE","already accepted")
        require(bool(t["verifiers"]),"NO_VERIFIER","a real required verifier is mandatory")
        candidate=tx.get("candidate",ident(p["candidate"]))
        require(t["active_attempt"] is not None and candidate["attempt"]==t["active_attempt"],"STALE_FENCE","candidate belongs to another/expired execution attempt")
        require(candidate["task"]==t["id"] and candidate["stamp"]==self.stamp(tx,t),"STALE_CANDIDATE","candidate authority changed")
        verify_live_candidate(tx,candidate)
        evidence_ids=string_list(p["evidence"],"evidence")
        matched=set()
        for id in evidence_ids:
            e=tx.get("evidence",ident(id))
            require(e["task"]==t["id"] and e["candidate"]==candidate["id"] and e["candidate_hash"]==candidate["manifest_hash"]
                    and e["stamp"]==self.stamp(tx,t) and e["status"]=="PASS", "INVALID_EVIDENCE","missing, failed, stale or unrelated test")
            spec=tx.get("verifier",e["verifier"])
            require(spec["manifest_hash"]==e["verifier_hash"],"STALE_VERIFIER","verifier changed")
            tx.read_blob(e["report_blob"])
            matched.add(e["verifier"])
        require(set(t["verifiers"])<=matched,"MISSING_EVIDENCE","not all required verifiers ran")
        require(not any(self.unresolved(x) and any(overlaps(r,s) for r in x["resources"] for s in t["resources"])
                        for x in tx.unresolved_actions()),"UNKNOWN_EFFECT","affected unresolved effects remain")
        for id in t["deps"]:
            dep=tx.get("task",id)
            require(dep["status"]=="ACCEPTED" and dep.get("accepted_stamp")==self.stamp(tx,dep),"DEPENDENCY","upstream evidence stale")
        if t["active_attempt"]:
            attempt,_=self.attempt(tx,a,t["active_attempt"],now)
            self.do_attempt_release(tx,a,now,{"id":attempt["id"],"reason":"verified acceptance"})
            t=tx.get("task",t["id"])
        t=tx.put("task",t["id"],t["workflow"],{**t,"status":"ACCEPTED","accepted_candidate":candidate["id"],"accepted_evidence":evidence_ids,"accepted_at":now})
        for id in t["requirements"]:
            r=tx.get("requirement",id)
            dependents=[x for x in tx.scan("task",t["workflow"]) if id in x["requirements"]]
            if r["status"]=="OPEN" and dependents and all(x["status"]=="ACCEPTED" for x in dependents):
                tx.put("requirement",id,t["workflow"],{**r,"status":"SATISFIED"})
        # Satisfaction is a derived state; refresh only accepted tasks sharing these
        # requirements, never source/dependency mismatches from before acceptance.
        for done in tx.scan("task",t["workflow"]):
            if done["id"]==t["id"]:
                tx.put("task",done["id"],done["workflow"],{**done,"accepted_stamp":self.stamp(tx,done)})
        return {"task":tx.get("task",t["id"])}

    def do_workflow_accept(self, tx, a, now, p):
        owner(a)
        w=self.workflow(tx,a,p["id"])
        tasks=tx.scan("task",w["id"])
        reqs=tx.scan("requirement",w["id"])
        require(bool(tasks) and bool(reqs),"EMPTY_COMPLETION","no accepted work")
        require(all(t["status"]=="ACCEPTED" and t.get("accepted_stamp")==self.stamp(tx,t) for t in tasks),"INCOMPLETE_TASKS","tasks not accepted/current")
        require(all(r["status"] in {"SATISFIED","CANCELED"} for r in reqs),"OPEN_REQUIREMENTS","original obligations remain")
        require(not any(self.unresolved(x) for x in tx.scan("action",w["id"])),"UNKNOWN_EFFECT","uncertain outcomes")
        # Keep ACTIVE as the control state; record accepted status separately so
        # accepted task stamps are not invalidated by the completion event itself.
        return {"workflow":tx.put("workflow",w["id"],w["id"],{**w,"completion":"ACCEPTED","accepted_at":now})}

    def do_snapshot_create(self, tx, a, now, p):
        owner(a)
        records=[]
        for k,id,w,rev,data in tx.conn.execute("SELECT kind,id,workflow,rev,data FROM objects ORDER BY kind,id"):
            if k!="snapshot":
                records.append({"kind":k,"id":id,"workflow":w,"rev":rev,"data":json.loads(data)})
        cursor=tx.conn.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0]
        blob=tx.blob(canonical({"schema":1,"cursor":cursor,"records":records}))
        id=fresh_id("snapshot")
        return {"snapshot":tx.put("snapshot",id,"*",{"blob":blob,"cursor":cursor,"created_at":now,"lossless":True},0)}

    def do_restore_resume(self, tx, a, now, p):
        owner(a)
        require(p["original_authority_fenced"] is True,"RESTORE_HELD","operator must fence/stop the original authority first")
        report=text(p["reconciliation_report"],"reconciliation_report")
        require(not any(self.unresolved(x) for x in tx.unresolved_actions()),"RESTORE_HELD","resolve prepared/uncertain historical actions first")
        # This is a local operator-controlled release, not distributed fencing proof.
        for g in tx.scan("grant"):
            tx.put("grant",g["id"],g["workflow"],{**g,"revoked":True})
        for attempt in tx.scan("attempt"):
            if attempt["status"]=="ACTIVE":
                self.do_attempt_release(tx,a,now,{"id":attempt["id"],"reason":"restore invalidates previous attempts"})
        tx.put("recovery",fresh_id("recovery"),"*",{"report":report,"original_authority_fenced_by_operator":True,"at":now},0)
        tx.conn.execute("UPDATE meta SET value='ACTIVE' WHERE key='mode'")
        return {"mode":"ACTIVE","assurance":"LOCAL_OPERATOR_RELEASE_NOT_DISTRIBUTED_CERTIFICATION"}
