import base64
import os
from pathlib import Path
import sys
from agent_relay.codec import digest,relpath,resource
from agent_relay.controller import fresh_id
from agent_relay.dispatch import dispatch,reconcile
from agent_relay.execution import run_process
from agent_relay.workspace import managed_write,file_observation
from support import RelayCase,gates


class EffectTests(RelayCase):
    @gates("G01")
    def test_canonical_paths_reject_traversal_and_aliases(self):
        for path in ("../escape","./x","a//x","a/./x","/absolute","a\\x","a/../x",".","e\u0301.txt",".git/config",".env"):
            with self.subTest(path=path):
                with self.assertRaises(Exception):relpath(path)
        self.assertEqual(relpath("src/main.py"),"src/main.py")

    @gates("G01","G19")
    def test_filesystem_resource_locks_are_casefolded(self):
        self.assertEqual(resource("repo/r/FILE.py"),resource("repo/r/file.py"))

    @gates("G01","G34")
    def test_failed_preparation_does_not_leave_blobs_or_events(self):
        self.cmd("repo.register",id="repo",workflow="w",root=str(self.repo))
        self.task(resources=["unrelated/path"],repos=["repo"])
        a,c=self.claim();before=self.store.doctor()
        with self.error("RESOURCE_SCOPE"):
            self.cmd("action.prepare",id="bad",attempt=a["id"],context=c["id"],type="file.write",
                     args={"repo":"repo","path":"x","expected_sha256":"ABSENT","data_b64":base64.b64encode(b"unique content").decode()})
        after=self.store.doctor()
        for k in ("blobs","objects","events","chain_head","blob_stored_bytes"):self.assertEqual(before[k],after[k])
        self.store.doctor(True)

    @gates("G01")
    def test_symlink_cannot_redirect_managed_write(self):
        outside=self.base/"outside";outside.mkdir()
        (self.repo/"sub").symlink_to(outside,target_is_directory=True)
        a,c,action=self.prepare_file(name="sub/x")
        result=dispatch(self.c,self.key,fresh_id("dispatch"),{"id":action["id"]})
        self.assertNotEqual(result["action"]["outcome"],"APPLIED")
        self.assertFalse((outside/"x").exists())

    @gates("G01")
    def test_hardlink_cannot_alias_unmanaged_file(self):
        outside=self.base/"outside";outside.write_text("secret")
        os.link(outside,self.repo/"x.txt")
        a,c,action=self.prepare_file(expected=digest(b"secret"))
        result=dispatch(self.c,self.key,fresh_id("dispatch"),{"id":action["id"]})
        self.assertNotEqual(result["action"]["outcome"],"APPLIED")
        self.assertEqual(outside.read_text(),"secret")

    @gates("G13","G34")
    def test_prepare_atomically_records_intent_outbox_and_blob_before_effect(self):
        a,c,action=self.prepare_file()
        self.assertFalse((self.repo/"x.txt").exists())
        with self.store.connection() as conn:
            from agent_relay.store import Transaction
            tx=Transaction(conn)
            self.assertEqual(tx.get("outbox",action["id"])["status"],"PENDING")
            self.assertEqual(tx.read_blob(action["args"]["blob"]),b"hello")
            self.assertEqual(tx.get("action",action["id"])["dispatch"],"PREPARED")
        self.store.doctor(True)

    @gates("G13","G15")
    def test_managed_effect_reads_back_actual_file(self):
        a,c,action=self.prepare_file()
        result=dispatch(self.c,self.key,fresh_id("dispatch"),{"id":action["id"]})
        self.assertEqual((self.repo/"x.txt").read_bytes(),b"hello")
        self.assertEqual(result["action"]["outcome"],"APPLIED")
        self.assertTrue(result["receipt"]["details"]["durable_readback"])
        self.store.doctor(True)

    @gates("G14")
    def test_duplicate_dispatch_does_not_reexecute(self):
        a,c,action=self.prepare_file()
        dispatch(self.c,self.key,"dispatch-id",{"id":action["id"]})
        before=(self.repo/"x.txt").stat().st_mtime_ns
        with self.error("DISPATCH_HELD"):dispatch(self.c,self.key,"dispatch-id",{"id":action["id"]})
        self.assertEqual(before,(self.repo/"x.txt").stat().st_mtime_ns)

    @gates("G13","G37")
    def test_lost_ack_reconciles_without_rewrite(self):
        a,c,action=self.prepare_file()
        self.cmd("action.start",id=action["id"])
        managed_write(self.repo,"x.txt","ABSENT",b"hello")
        before=(self.repo/"x.txt").stat().st_mtime_ns
        result=reconcile(self.c,self.key,fresh_id("reconcile"),{"id":action["id"]})
        self.assertEqual(result["action"]["outcome"],"APPLIED")
        self.assertEqual(before,(self.repo/"x.txt").stat().st_mtime_ns)

    @gates("G37")
    def test_absence_is_not_proof_of_failed_effect(self):
        a,c,action=self.prepare_file()
        self.cmd("action.start",id=action["id"])
        result=reconcile(self.c,self.key,fresh_id("reconcile"),{"id":action["id"]})
        self.assertFalse(result["reconciled"])
        self.assertEqual(self.get("action",action["id"])["outcome"],"UNKNOWN")

    @gates("G18","G19")
    def test_unknown_effect_blocks_only_conflicting_resources(self):
        a,c,action=self.prepare_file(ttl=0.1)
        self.cmd("action.start",id=action["id"])
        self.clock.advance(1)
        self.task(id="parallel",resources=["independent/resource"])
        b,d=self.claim("parallel")
        self.assertEqual(b["task"],"parallel")
        with self.error("NOT_READY"):self.claim("t")

    @gates("G35")
    def test_late_receipt_accepted_after_attempt_expiry(self):
        a,c,action=self.prepare_file(ttl=0.1)
        self.cmd("action.start",id=action["id"])
        self.clock.advance(2)
        result=self.cmd("action.receipt",id=action["id"],receipt_id="late",outcome="APPLIED",details={"source":"external result"})
        self.assertEqual(result["action"]["outcome"],"APPLIED")
        with self.error("STALE_FENCE"):self.cmd("attempt.heartbeat",id=a["id"])

    @gates("G35")
    def test_duplicate_receipt_retains_one_observation(self):
        a,c,action=self.prepare_file();self.cmd("action.start",id=action["id"])
        p={"id":action["id"],"receipt_id":"receipt","outcome":"APPLIED","details":{"n":1}}
        self.cmd("action.receipt",**p);self.cmd("action.receipt",**p)
        self.assertEqual(self.get("action",action["id"])["receipt_ids"],["receipt"])

    @gates("G35")
    def test_conflicting_receipt_is_quarantined_not_regressed(self):
        a,c,action=self.prepare_file();self.cmd("action.start",id=action["id"])
        self.cmd("action.receipt",id=action["id"],receipt_id="receipt",outcome="APPLIED",details={"n":1})
        result=self.cmd("action.receipt",id=action["id"],receipt_id="receipt",outcome="NOT_APPLIED",details={"n":2})
        self.assertIn("quarantined",result)
        self.assertEqual(self.get("action",action["id"])["outcome"],"APPLIED")

    @gates("G35")
    def test_old_unknown_receipt_cannot_regress_settled_outcome(self):
        a,c,action=self.prepare_file();self.cmd("action.start",id=action["id"])
        self.cmd("action.receipt",id=action["id"],receipt_id="new",outcome="APPLIED",details={})
        r=self.cmd("action.receipt",id=action["id"],receipt_id="older",outcome="UNKNOWN",details={})
        self.assertIn("quarantined",r)

    @gates("G36")
    def test_cancel_before_send_cancels_outbox(self):
        a,c,action=self.prepare_file()
        self.cmd("workflow.cancel",id="w",reason="owner cancels")
        with self.error("DISPATCH_HELD"):self.cmd("action.start",id=action["id"])
        self.assertEqual(self.get("action",action["id"])["dispatch"],"CANCELED_BEFORE_SEND")
        self.assertFalse((self.repo/"x.txt").exists())

    @gates("G36")
    def test_cancel_after_send_waits_for_outcome(self):
        a,c,action=self.prepare_file();self.cmd("action.start",id=action["id"])
        self.cmd("workflow.cancel",id="w",reason="owner cancels")
        with self.error("UNKNOWN_EFFECT"):self.cmd("workflow.settle_cancel",id="w")
        self.cmd("action.receipt",id=action["id"],receipt_id="late",outcome="APPLIED",details={})
        self.cmd("attempt.release",id=a["id"],reason="observed worker stopped")
        result=self.cmd("workflow.settle_cancel",id="w")
        self.assertEqual(result["workflow"]["status"],"CANCELED")
        self.assertEqual(self.get("action",action["id"])["outcome"],"APPLIED")

    @gates("G13")
    def test_compare_and_set_does_not_overwrite_unexpected_state(self):
        (self.repo/"x.txt").write_text("unexpected")
        a,c,action=self.prepare_file()
        result=dispatch(self.c,self.key,fresh_id("dispatch"),{"id":action["id"]})
        self.assertEqual(result["action"]["outcome"],"NOT_APPLIED")
        self.assertEqual((self.repo/"x.txt").read_text(),"unexpected")

    @gates("G01")
    def test_existing_executable_mode_is_preserved(self):
        f=self.repo/"script.sh";f.write_bytes(b"old");f.chmod(0o700)
        managed_write(self.repo,"script.sh",digest(b"old"),b"new")
        self.assertEqual(f.stat().st_mode&0o777,0o700)

    @gates("G41")
    def test_worker_cannot_supply_forged_action_receipt(self):
        worker=self.worker();a,c,action=self.prepare_file(token=worker)
        self.cmd("action.start",id=action["id"])
        with self.error("FORBIDDEN"):
            self.cmd("action.receipt",token=worker,id=action["id"],receipt_id="fake",outcome="APPLIED",details={})

    @gates("G26","G43")
    def test_subprocess_timeout_is_bounded(self):
        result=run_process([sys.executable,"-c","import time; time.sleep(20)"],self.repo,timeout=0.1)
        self.assertTrue(result["timed_out"])
        self.assertLess(result["elapsed_s"],3)
        self.assertIsNotNone(result["returncode"])

    @gates("G29","G43")
    def test_output_flood_is_bounded(self):
        result=run_process([sys.executable,"-c","import os;\nwhile True: os.write(1,b'x'*65536)"],self.repo,timeout=5,output_limit=1024)
        self.assertTrue(result["output_limited"])
        self.assertLessEqual(len(result["stdout"]),1024)

    @gates("G28","G41")
    def test_subprocess_does_not_inherit_relay_token(self):
        old=os.environ.get("RELAY_TOKEN");os.environ["RELAY_TOKEN"]="SECRET_DO_NOT_LEAK"
        try:r=run_process([sys.executable,"-c","import os;print(os.environ.get('RELAY_TOKEN','absent'))"],self.repo,timeout=5)
        finally:
            if old is None:os.environ.pop("RELAY_TOKEN",None)
            else:os.environ["RELAY_TOKEN"]=old
        self.assertEqual(r["stdout"].strip(),"absent")

    @gates("G41")
    def test_tool_registration_rejects_loader_injection_environment(self):
        self.cmd("repo.register",id="repo",workflow="w",root=str(self.repo))
        with self.error("UNSAFE_ENV"):
            self.cmd("tool.register",id="tool",workflow="w",argv=[sys.executable,"-c","print('x')"],repo="repo",resources=["repo/repo"],reason="test",environment={"LD_PRELOAD":"evil"})

    @gates("G13","G41")
    def test_approved_fixed_command_executes_and_records_process(self):
        self.cmd("repo.register",id="repo",workflow="w",root=str(self.repo))
        self.cmd("tool.register",id="tool",workflow="w",argv=[sys.executable,"-c","from pathlib import Path;Path('made.txt').write_text('real')"],repo="repo",resources=["repo/repo"],reason="explicit operator approval")
        self.task(resources=["repo/repo"],repos=["repo"],tools=["tool"])
        a,c=self.claim()
        self.cmd("action.prepare",id="exec",attempt=a["id"],context=c["id"],type="command",args={"tool":"tool"})
        result=dispatch(self.c,self.key,fresh_id("dispatch"),{"id":"exec"})
        self.assertEqual((self.repo/"made.txt").read_text(),"real")
        self.assertEqual(result["action"]["outcome"],"APPLIED")
        self.assertIn("pid",self.get("action","exec")["process"])

    @gates("G08","G42")
    def test_changed_approved_tool_script_is_rejected(self):
        script=self.repo/"tool.py";script.write_text("print('old')")
        self.cmd("repo.register",id="repo",workflow="w",root=str(self.repo))
        self.cmd("tool.register",id="tool",workflow="w",argv=[sys.executable,"tool.py"],repo="repo",resources=["repo/repo"],reason="approved")
        self.task(resources=["repo/repo"],repos=["repo"],tools=["tool"]);a,c=self.claim()
        self.cmd("action.prepare",id="exec",attempt=a["id"],context=c["id"],type="command",args={"tool":"tool"})
        script.write_text("print('changed')")
        result=dispatch(self.c,self.key,fresh_id("dispatch"),{"id":"exec"})
        self.assertEqual(result["action"]["outcome"],"NOT_APPLIED")
        self.assertEqual(result["receipt"]["details"]["code"],"TOOL_CHANGED")

    @gates("G37")
    def test_generic_command_unknown_is_not_retried(self):
        self.cmd("repo.register",id="repo",workflow="w",root=str(self.repo))
        self.cmd("tool.register",id="tool",workflow="w",argv=[sys.executable,"-c","raise SystemExit(7)"],repo="repo",resources=["repo/repo"],reason="approved")
        self.task(resources=["repo/repo"],repos=["repo"],tools=["tool"]);a,c=self.claim()
        self.cmd("action.prepare",id="exec",attempt=a["id"],context=c["id"],type="command",args={"tool":"tool"})
        r=dispatch(self.c,self.key,fresh_id("dispatch"),{"id":"exec"})
        self.assertEqual(r["action"]["outcome"],"UNKNOWN")
        rr=reconcile(self.c,self.key,fresh_id("reconcile"),{"id":"exec"})
        self.assertFalse(rr["reconciled"])

    @gates("G23")
    def test_partial_two_resource_delivery_is_not_whole_job_success(self):
        a,c,first=self.prepare_file(action="first",name="first.txt")
        dispatch(self.c,self.key,fresh_id("dispatch"),{"id":"first"})
        self.cmd("action.prepare",id="second",attempt=a["id"],context=c["id"],type="file.write",
                 args={"repo":"repo","path":"second.txt","expected_sha256":"ABSENT","data_b64":"c2Vjb25k"})
        self.cmd("action.start",id="second")
        self.assertEqual(self.get("action","first")["outcome"],"APPLIED")
        self.assertEqual(self.get("action","second")["outcome"],"UNKNOWN")
        with self.error("INCOMPLETE_TASKS"):self.cmd("workflow.accept",id="w")
        self.assertEqual(self.get("requirement","r")["status"],"OPEN")
