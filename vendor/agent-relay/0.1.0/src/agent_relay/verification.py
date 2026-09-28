"""Owner-pinned oracle, immutable candidates, bounded execution and real evidence."""
from __future__ import annotations
from importlib.resources import files
import json
from pathlib import Path
import sys
import tempfile
from .codec import canonical,digest,ident,integer,number,object_digest,text
from .controller import owner,fresh_id
from .errors import require,RelayError
from .execution import run_process
from .workspace import stable_tree,stage_candidate,verify_live_candidate


def register_verifier(controller,token,command_id,payload):
    require(type(payload) is dict and {"id","workflow","oracle_root"}<=payload.keys()
            and payload.keys()<={"id","workflow","oracle_root","min_tests","timeout"},"INVALID_FIELDS","verifier.register")
    id=ident(payload["id"]);workflow=ident(payload["workflow"])
    root=Path(text(payload["oracle_root"],"oracle_root",4096)).expanduser().resolve()
    require(root.is_dir(),"ORACLE_PATH","oracle must be an existing directory")
    # Authenticate before reading private source files.
    controller.store.read(token,lambda tx,a:(owner(a),controller.workflow(tx,a,workflow)))
    manifest,raws=stable_tree(root,[])
    min_tests=integer(payload.get("min_tests",1),"min_tests",1,100000)
    require(any(Path(x).name.startswith("test") and x.endswith(".py") for x in raws),"EMPTY_VERIFIER","no test*.py oracle files")
    timeout=number(payload.get("timeout",60),"timeout",0.1,3600)
    def apply(tx,a,now):
        owner(a);controller.workflow(tx,a,workflow)
        blobs={path:tx.blob(raw) for path,raw in raws.items()}
        config={"files":manifest["files"],"min_tests":min_tests,"timeout":timeout,"engine":"unittest",
                "python":str(Path(sys.executable).absolute()),"python_hash":digest(Path(sys.executable).resolve().read_bytes()),
                "runner_hash":digest(files("agent_relay").joinpath("verifier_worker.py").read_bytes())}
        v=tx.put("verifier",id,workflow,{"manifest":config,"manifest_hash":object_digest(config),"blobs":blobs,
                    "registered_at":now,"authority":"OWNER_PINNED_ORACLE","assurance":"TRUSTED_CODE_SAME_UID"},0)
        return {"verifier":v}
    return controller.store.command(token,command_id,"verifier.register",payload,apply)


def run_verifier(controller,token,command_id,payload):
    require(type(payload) is dict and set(payload)=={"candidate","verifier"},"INVALID_FIELDS","verify.run requires candidate, verifier")
    def read(tx,a):
        owner(a)
        c=tx.get("candidate",ident(payload["candidate"]))
        t=tx.get("task",c["task"])
        v=tx.get("verifier",ident(payload["verifier"]))
        controller.workflow(tx,a,t["workflow"])
        require(v["id"] in t["verifiers"] and v["workflow"]==t["workflow"],"FORBIDDEN","verifier not required by task")
        require(c["stamp"]==controller.stamp(tx,t),"STALE_CANDIDATE","candidate authority changed")
        verify_live_candidate(tx,c)
        return c,t,v
    candidate,task,verifier=controller.store.read(token,read)
    config=verifier["manifest"]
    require(digest(Path(config["python"]).read_bytes())==config["python_hash"],"VERIFIER_CHANGED","Python executable changed")
    runner=files("agent_relay").joinpath("verifier_worker.py").read_bytes()
    require(digest(runner)==config["runner_hash"],"VERIFIER_CHANGED","runner code changed")
    # Execution admission is idempotent: a retried run ID cannot secretly execute twice.
    runid=fresh_id("verification")
    def admit(tx,a,now):
        owner(a)
        r=tx.put("verification_run",runid,task["workflow"],{"task":task["id"],"candidate":candidate["id"],"verifier":verifier["id"],
                    "status":"RUNNING","started_at":now},0)
        return {"run":r}
    admitted=controller.store.command(token,command_id,"_verify.admit",payload,admit)
    require(admitted["run"]["id"]==runid,"VERIFY_ALREADY_STARTED",f"original run {admitted['run']['id']} may be complete/unknown; use get verification_run with that ID, do not blindly repeat")
    with tempfile.TemporaryDirectory(prefix="relay-verify-",dir=controller.store.home) as tmp:
        base=Path(tmp);workspace=base/"workspace";workspace.mkdir(mode=0o700)
        oracle=base/"oracle";oracle.mkdir(mode=0o700)
        resultpath=base/"result.json";runnerpath=base/"runner.py";runnerpath.write_bytes(runner)
        def stage(tx,a):
            owner(a);stage_candidate(tx,candidate,workspace)
            for name,key in verifier["blobs"].items():
                path=oracle/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(tx.read_blob(key));path.chmod(0o400)
        controller.store.read(token,stage)
        argv=[config["python"],"-I",str(runnerpath),"--workspace",str(workspace),"--oracle",str(oracle),"--result",str(resultpath)]
        result=run_process(argv,workspace,timeout=config["timeout"])
        report={"schema":1,"tests":0,"failures":0,"errors":1,"skipped":0,"successful":False}
        if resultpath.is_file() and not resultpath.is_symlink() and resultpath.stat().st_size<=65536:
            try:report=json.loads(resultpath.read_text())
            except (ValueError,OSError):pass
        if type(report) is not dict:
            report={"schema":1,"tests":0,"failures":0,"errors":1,"skipped":0,"successful":False,"reason":"invalid runner report"}
        input_unchanged=True
        for repo,m in candidate["manifests"].items():
            for name,item in m["files"].items():
                path=workspace/repo/name
                if not path.is_file() or path.is_symlink() or digest(path.read_bytes())!=item["sha256"]:
                    input_unchanged=False
        oracle_unchanged=all((oracle/name).is_file() and not (oracle/name).is_symlink()
                             and digest((oracle/name).read_bytes())==entry["sha256"] for name,entry in config["files"].items())
        valid_report=(type(report) is dict and report.get("schema")==1 and
                      all(type(report.get(k)) is int and report[k]>=0 for k in ("tests","failures","errors","skipped")))
        passed=(valid_report and report["tests"]>=config["min_tests"] and report["failures"]==report["errors"]==report["skipped"]==0
                and report.get("expected_failures",0)==0 and report.get("unexpected_successes",0)==0 and report.get("successful") is True
                and result["returncode"]==0 and not result["timed_out"] and not result["output_limited"] and input_unchanged and oracle_unchanged)
        allreport={"unit_report":report,"process":result,"input_unchanged":input_unchanged,"oracle_unchanged":oracle_unchanged,
                   "candidate_hash":candidate["manifest_hash"],"verifier_hash":verifier["manifest_hash"],
                   "runtime":{"python":sys.version,"executable":config["python"],"runner_hash":config["runner_hash"]},
                   "assurance":"LOCAL_TRUSTED_CODE_NOT_HOSTILE_CODE_SANDBOX"}
    def finish(tx,a,now):
        owner(a)
        current=tx.get("task",task["id"])
        freshness=candidate["stamp"]==controller.stamp(tx,current)
        if freshness:
            try:verify_live_candidate(tx,candidate)
            except RelayError:freshness=False
        status="PASS" if passed and freshness else "FAIL" if not passed else "STALE"
        blob=tx.blob(canonical(allreport))
        e=tx.put("evidence",fresh_id("evidence"),task["workflow"],{"task":task["id"],"candidate":candidate["id"],
                  "candidate_hash":candidate["manifest_hash"],"verifier":verifier["id"],"verifier_hash":verifier["manifest_hash"],
                  "stamp":candidate["stamp"],"status":status,"tests":report.get("tests",0),"report_blob":blob,
                  "created_at":now,"run":runid,"evidence_class":"EXECUTED_LOCAL_TRUSTED_CODE"},0)
        run=tx.get("verification_run",runid)
        tx.put("verification_run",runid,task["workflow"],{**run,"status":status,"evidence":e["id"],"finished_at":now})
        return {"evidence":e,"report":allreport}
    return controller.store.command(token,fresh_id("verify-finish"),"_verify.finish",{"run":runid,"report_hash":object_digest(allreport)},finish)
