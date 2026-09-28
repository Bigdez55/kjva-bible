from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from agent_relay.controller import fresh_id
from agent_relay.errors import RelayError
from agent_relay.store import Store
from support import RelayCase,gates


class ConcurrencyTests(RelayCase):
    @gates("G18")
    def test_eight_independent_tasks_make_concurrent_progress(self):
        for i in range(8):self.task(id=f"t{i}")
        barrier=threading.Barrier(8)
        def worker(i):
            barrier.wait()
            a,c=self.claim(f"t{i}")
            for _ in range(20):self.cmd("attempt.heartbeat",id=a["id"])
            self.cmd("attempt.release",id=a["id"],reason="done with independent bounded step")
            return i
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(worker,range(8)))
        self.assertEqual(results,list(range(8)))
        self.store.doctor(True)

    @gates("G19")
    def test_competing_parent_child_resource_claims_have_one_winner(self):
        self.task(id="a",resources=["interface/api"])
        self.task(id="b",resources=["interface/api/v2"])
        barrier=threading.Barrier(2)
        def run(id):
            barrier.wait()
            try:self.claim(id);return "CLAIMED"
            except RelayError as e:return e.code
        with ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(run,["a","b"]))
        self.assertEqual(sorted(out),["CLAIMED","NOT_READY"])

    @gates("G19","G26")
    def test_stale_lease_holder_cannot_heartbeat_after_replacement(self):
        self.task();a,c=self.claim(ttl=0.1)
        self.clock.advance(1)
        b,d=self.claim()
        self.assertGreater(b["fence"],a["fence"])
        with self.error("STALE_FENCE"):self.cmd("attempt.heartbeat",id=a["id"])
        self.cmd("attempt.heartbeat",id=b["id"])

    @gates("G26")
    def test_old_release_does_not_release_new_lease(self):
        self.task();a,c=self.claim(ttl=0.1)
        self.clock.advance(1)
        b,d=self.claim()
        self.cmd("attempt.release",id=a["id"],reason="late old cleanup")
        self.cmd("attempt.heartbeat",id=b["id"])
        self.assertEqual(self.get("task","t")["active_attempt"],b["id"])

    @gates("G18","G43")
    def test_ready_queue_prioritizes_not_yet_attempted_work(self):
        for i in range(3):self.task(id=f"t{i}")
        first=self.cmd("work.next",workflow="w",provider="manual")["attempt"]
        self.cmd("attempt.release",id=first["id"],reason="yield")
        second=self.cmd("work.next",workflow="w",provider="manual")["attempt"]
        self.assertNotEqual(first["task"],second["task"])

    @gates("G18","G25","G43")
    def test_provider_release_keeps_task_identity_and_allows_successor(self):
        worker=self.worker("first");successor=self.worker("second")
        self.task();a,c=self.claim(token=worker)
        self.cmd("attempt.release",token=worker,id=a["id"],reason="provider quota exhausted")
        b,d=self.claim(token=successor)
        self.assertEqual(a["task"],b["task"])
        self.assertNotEqual(a["id"],b["id"])
        body=self.get("context",d["id"],successor)["body"]
        self.assertEqual(body["requirements"][0]["id"],"r")

    @gates("G18","G29")
    def test_four_real_processes_append_without_lost_commits(self):
        self.store.clock=time.time
        before=self.store.doctor()["events"]
        script='''from pathlib import Path
import sys
from agent_relay.store import Store
from agent_relay.controller import Controller
s=Store(Path(sys.argv[1]));c=Controller(s)
for n in range(25):
 i=sys.argv[2]+str(n)
 c.command(s.key,'cmd-'+i,'memory.add',{'id':'m-'+i,'workflow':'w','text':'process '+i,'origin':'process-test'})
'''
        procs=[subprocess.Popen([sys.executable,"-c",script,str(self.home),str(i)+"-"],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for i in range(4)]
        for proc in procs:
            out,err=proc.communicate(timeout=30)
            self.assertEqual(proc.returncode,0,err.decode())
        report=self.store.doctor(True)
        self.assertEqual(report["events"]-before,100)

    @gates("G26")
    def test_second_service_or_maintenance_owner_is_rejected(self):
        with self.store.service_lock():
            with self.error("SERVICE_RUNNING"):
                with self.store.service_lock():pass
