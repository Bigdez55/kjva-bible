"""Installed, disposable end-to-end rehearsal using the actual socket daemon.

Real process termination and a real SQLite application are exercised. No model,
provider API, physical host power cut, multi-host operation, or live user store
is exercised. All data is in a newly created temporary directory.
"""
from __future__ import annotations
import base64
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from . import __version__
from .codec import digest
from .errors import RelayError,require
from .service import call
from .store import Store

APP_SOURCE='''from contextlib import closing
import sqlite3

def put(path, key, value):
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS values_table (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
        conn.execute("INSERT INTO values_table VALUES (?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key,value))
        conn.commit()
    return True

def get(path, key):
    with closing(sqlite3.connect(path)) as conn:
        row=conn.execute("SELECT v FROM values_table WHERE k=?", (key,)).fetchone()
        return row[0] if row else None
'''

ORACLE_SOURCE='''from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import app

class RealApplicationOracle(unittest.TestCase):
    def test_write_independent_database_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=str(Path(tmp)/"app.sqlite3")
            self.assertTrue(app.put(db,"answer","42"))
            with closing(sqlite3.connect(db)) as conn:
                self.assertEqual(conn.execute("SELECT v FROM values_table WHERE k='answer'").fetchone()[0],"42")
    def test_fresh_process_reads_committed_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=str(Path(tmp)/"app.sqlite3")
            app.put(db,"answer","42")
            p=subprocess.run([sys.executable,"-c","import app,sys;print(app.get(sys.argv[1],'answer'))",db],
                              cwd=Path(app.__file__).parent,capture_output=True,text=True,timeout=5)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(p.stdout.strip(),"42")
    def test_update_is_persistent_not_hardcoded(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=str(Path(tmp)/"app.sqlite3")
            app.put(db,"k","first")
            app.put(db,"k","second")
            self.assertEqual(app.get(db,"k"),"second")
'''


def start_service(home:Path,stderr_file):
    proc=subprocess.Popen([sys.executable,"-m","agent_relay.cli","--home",str(home),"serve"],
                          stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=stderr_file)
    token=(home/"owner.key").read_text().strip()
    for _ in range(200):
        if proc.poll() is not None:raise RelayError("SELFTEST_SERVICE","daemon exited at startup")
        if (home/"relay.sock").exists():
            try:
                call(home,token,"version",{},timeout=0.5)
                return proc
            except (RelayError,OSError):pass
        time.sleep(0.01)
    proc.kill();proc.wait()
    raise RelayError("SELFTEST_SERVICE","daemon did not start")


def run_selftest():
    start=time.monotonic();checks=[];proc=None
    with tempfile.TemporaryDirectory(prefix="rly-") as tmp:
        base=Path(tmp);home=base/"ctl";repo=base/"repo";oracle=base/"oracle"
        repo.mkdir();oracle.mkdir()
        (repo/"app.py").write_text(APP_SOURCE)
        (oracle/"test_app.py").write_text(ORACLE_SOURCE)
        store=Store.initialize(home)
        token=store.key
        with (base/"service.stderr").open("wb") as log:
            try:
                proc=start_service(home,log)
                def op(name,p,worker=None):return call(home,worker or token,name,p)
                op("workflow.create",{"id":"demo","directive":"Build a durable application; preserve every requirement across provider handoff.","constraints":["Never claim completion from a narrative alone."]})
                op("requirement.add",{"id":"persist","workflow":"demo","text":"A write must survive restart and be independently readable."})
                op("requirement.add",{"id":"independent","workflow":"demo","text":"Unrelated work must progress during a held effect."})
                op("source.put",{"id":"identity","workflow":"demo","source_kind":"Agent.md","text":"Identity: Agent. Provider sessions are disposable. The authority is this Relay job.","expected_rev":0})
                op("repo.register",{"id":"app","workflow":"demo","root":str(repo)})
                op("verifier.register",{"id":"app-oracle","workflow":"demo","oracle_root":str(oracle),"min_tests":3})
                op("task.create",{"id":"build","workflow":"demo","title":"Deliver working persistence","requirements":["persist"],"resources":["repo/app"],"repos":["app"],"verifiers":["app-oracle"]})
                op("task.create",{"id":"parallel","workflow":"demo","title":"Independent continuity task","requirements":["independent"],"resources":["independent/document"]})
                for grant in ("worker-a","worker-b"):
                    op("grant.create",{"id":grant,"workflow":"demo"})
                wa=op("grant.token",{"id":"worker-a"})["token"]
                wb=op("grant.token",{"id":"worker-b"})["token"]
                attempt=op("task.claim",{"id":"build","provider":"manual-client-A","ttl":0.3},wa)["attempt"]
                ctx=op("context.hydrate",{"attempt":attempt["id"]},wa)["context"]
                data=b"durable effect written before acknowledgement\n"
                op("action.prepare",{"id":"write-note","attempt":attempt["id"],"context":ctx["id"],"type":"file.write",
                                     "args":{"repo":"app","path":"note.txt","expected_sha256":"ABSENT","data_b64":base64.b64encode(data).decode()}},wa)
                # Deliberately lose both executor and authority processes after external commit.
                op("action.start",{"id":"write-note"})
                script="from agent_relay.workspace import managed_write; from pathlib import Path; import sys,os,signal; managed_write(Path(sys.argv[1]),'note.txt','ABSENT',bytes.fromhex(sys.argv[2])); os.kill(os.getpid(),signal.SIGKILL)"
                external=subprocess.run([sys.executable,"-c",script,str(repo),data.hex()],capture_output=True,timeout=10)
                require(external.returncode==-signal.SIGKILL,"SELFTEST","executor was not killed")
                proc.kill();proc.wait(timeout=5)
                checks.append({"check":"executor_and_controller_SIGKILL_after_effect_before_receipt","status":"PASS","executor_returncode":external.returncode})
                proc=start_service(home,log)
                time.sleep(0.35)
                try:op("task.claim",{"id":"build","provider":"manual-client-B"},wb)
                except RelayError as e:require(e.code=="NOT_READY","SELFTEST",e.code)
                else:raise RelayError("SELFTEST","unknown effect did not hold takeover")
                independent=op("task.claim",{"id":"parallel","provider":"manual-client-B"},wb)["attempt"]
                op("attempt.heartbeat",{"id":independent["id"]},wb)
                op("attempt.release",{"id":independent["id"],"reason":"independent progress observed"},wb)
                checks.append({"check":"unknown_effect_holds_only_affected_resources","status":"PASS"})
                recovered=op("action.reconcile",{"id":"write-note"})
                require(recovered["action"]["outcome"]=="APPLIED","SELFTEST","readback failed")
                checks.append({"check":"lost_ack_independent_readback_no_rewrite","status":"PASS","destination_sha256":digest((repo/"note.txt").read_bytes())})
                successor=op("task.claim",{"id":"build","provider":"manual-client-B"},wb)["attempt"]
                cold=op("context.hydrate",{"attempt":successor["id"]},wb)
                require(cold["body"]["workflow"]["directive"].startswith("Build a durable application"),"SELFTEST","intent lost")
                require(cold["body"]["requirements"][0]["id"]=="persist","SELFTEST","obligation lost")
                try:op("attempt.heartbeat",{"id":attempt["id"]},wa)
                except RelayError as e:require(e.code=="STALE_FENCE","SELFTEST",e.code)
                else:raise RelayError("SELFTEST","stale attempt was accepted")
                checks.append({"check":"cold_successor_same_job_new_attempt_and_stale_fence_rejection","status":"PASS"})
                candidate=op("candidate.capture",{"id":"candidate-demo","attempt":successor["id"],"context":cold["context"]["id"]},wb)["candidate"]
                result=op("verify.run",{"candidate":candidate["id"],"verifier":"app-oracle"})
                require(result["evidence"]["status"]=="PASS","SELFTEST",json.dumps(result))
                accepted=op("task.accept",{"id":"build","candidate":candidate["id"],"evidence":[result["evidence"]["id"]]})
                require(accepted["task"]["status"]=="ACCEPTED","SELFTEST","acceptance failed")
                checks.append({"check":"real_application_persistence_and_exact_candidate_acceptance","status":"PASS","application_tests":result["evidence"]["tests"],"candidate_hash":candidate["manifest_hash"]})
                health=op("doctor",{"scrub":True})
                checks.append({"check":"event_projection_command_blob_integrity","status":health["full_scrub"]})
                proc.terminate();proc.wait(timeout=10);proc=None
                return {"ok":True,"version":__version__,"elapsed_s":time.monotonic()-start,"checks":checks,
                        "doctor":health,"application_verifier_report":result["report"],
                        "scope":"installed local socket runtime, disposable files, process SIGKILL",
                        "not_exercised":["real model/provider lifecycle","physical power loss","multi-host","long-duration endurance","existing user relay"],
                        "live_workspace_opened":False}
            finally:
                if proc is not None and proc.poll() is None:
                    proc.terminate()
                    try:proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
