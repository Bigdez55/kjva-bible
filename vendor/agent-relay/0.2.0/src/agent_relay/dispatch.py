"""Durable dispatch and conservative reconciliation. No automatic effect retries."""
from pathlib import Path
from .codec import canonical,digest,ident
from .controller import fresh_id,owner
from .errors import RelayError,require
from .execution import run_process,validate_pins
from .workspace import file_observation,managed_write


def dispatch(controller,token,command_id,payload):
    require(type(payload) is dict and set(payload)=={"id"},"INVALID_FIELDS","action.dispatch requires id")
    id=ident(payload["id"])
    # Exact replay of this outer command must never relaunch an already-started effect.
    started=controller.command(token,command_id,"action.start",payload)
    action=controller.store.read(token,lambda tx,a:(owner(a),tx.get("action",id))[1])
    require(action["dispatch"]=="SENDING","DISPATCH_HELD","effect is already acknowledged; inspect its receipt")
    # A second invocation with the SAME start command ID also must not dispatch twice.
    # Claim a unique execution record in a separate transaction before touching the destination.
    def claim(tx,a,now):
        owner(a)
        cur=tx.get("action",id)
        attempt,task=controller.attempt(tx,a,cur["attempt"],now)
        controller._context(tx,attempt,task,cur["context"])
        require(cur["dispatch"]=="SENDING" and not cur.get("execution_claimed"),"DISPATCH_HELD","execution may already have begun; reconcile")
        return {"action":tx.put("action",id,cur["workflow"],{**cur,"execution_claimed":True})}
    controller.store.command(token,fresh_id("execute"),"_execution.claim",{"id":id},claim)
    outcome="UNKNOWN"; details={}
    try:
        def inputs(tx,a):
            owner(a)
            cur=tx.get("action",id)
            if cur["type"]=="file.write":
                repo=tx.get("repo",cur["args"]["repo"])
                return repo,tx.read_blob(cur["args"]["blob"])
            tool=tx.get("tool",cur["args"]["tool"])
            require(tool["rev"]==cur["args"]["tool_rev"],"TOOL_CHANGED","registered command changed")
            return tool,tx.get("repo",tool["repo"]),tx.read_blob(cur["args"]["stdin_blob"])
        data=controller.store.read(token,inputs)
        if action["type"]=="file.write":
            repo,raw=data
            details=managed_write(Path(repo["root"]),action["args"]["path"],action["args"]["expected_sha256"],raw)
            details["observer"]="managed-file-write-with-readback"
            outcome="APPLIED"
        else:
            tool,repo,stdin=data
            validate_pins(tool["pins"])
            def spawned(info):
                def apply(tx,a,now):
                    owner(a);cur=tx.get("action",id)
                    return {"action":tx.put("action",id,cur["workflow"],{**cur,"process":info})}
                controller.store.command(token,fresh_id("spawn"),"_process.observed",{"id":id,"process":info},apply)
            result=run_process(tool["argv"],Path(repo["root"]),timeout=tool["timeout"],stdin=stdin,
                               environment=tool["environment"],on_spawn=spawned)
            def record(tx,a,now):
                owner(a)
                blob=tx.blob(canonical(result))
                return {"output_blob":blob}
            output=controller.store.command(token,fresh_id("output"),"_process.output",{"id":id,"digest":digest(canonical(result))},record)
            details={"observer":"bounded-cooperative-process","output_blob":output["output_blob"],
                     **{k:v for k,v in result.items() if k not in {"stdout","stderr"}}}
            outcome="APPLIED" if result["returncode"]==0 and not result["timed_out"] and not result["output_limited"] else "UNKNOWN"
            if result.get("spawn_error"):
                outcome="NOT_APPLIED"
    except RelayError as e:
        details={"observer":"dispatcher-error","code":e.code,"message":e.message}
        # These failures are detected before a destination write/process starts.
        outcome="NOT_APPLIED" if e.code in {"COMPARE_AND_SET","TOOL_CHANGED"} else "UNKNOWN"
    except OSError as e:
        details={"observer":"dispatcher-error","message":str(e)}
        outcome="UNKNOWN"
    return controller.command(token,fresh_id("receipt-command"),"action.receipt",
                              {"id":id,"receipt_id":fresh_id("receipt"),"outcome":outcome,"details":details})


def reconcile(controller,token,command_id,payload):
    require(type(payload) is dict and set(payload)=={"id"},"INVALID_FIELDS","action.reconcile requires id")
    def read(tx,a):
        owner(a)
        action=tx.get("action",ident(payload["id"]))
        if action["type"]=="file.write":
            return action,tx.get("repo",action["args"]["repo"])
        return action,None
    action,repo=controller.store.read(token,read)
    if not controller.unresolved(action):
        return {"action":action,"reconciled":True}
    require(action["dispatch"] in {"SENDING","ACKNOWLEDGED"},"RECONCILE_HELD","prepared-but-unsent actions need a scoped operator disposition")
    if action["type"]!="file.write":
        return {"action":action,"reconciled":False,"reason":"command outcome not independently queryable; do not blindly retry"}
    observed=file_observation(Path(repo["root"]),action["args"]["path"])
    if observed!=action["args"]["blob"]:
        return {"action":action,"reconciled":False,"observed_sha256":observed,
                "reason":"absence or different bytes do not prove the original effect never happened"}
    return controller.command(token,command_id,"action.receipt",{"id":action["id"],"receipt_id":fresh_id("receipt"),"outcome":"APPLIED",
             "details":{"observer":"independent-file-readback","desired_sha256":observed,
                        "semantics":"desired state observed; not proof of which process originally wrote it"}})
