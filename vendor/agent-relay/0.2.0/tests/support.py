from __future__ import annotations
import base64
from contextlib import contextmanager
from pathlib import Path
import tempfile
import time
import unittest
from agent_relay.codec import digest
from agent_relay.controller import Controller,fresh_id
from agent_relay.dispatch import dispatch,reconcile
from agent_relay.errors import RelayError
from agent_relay.store import Store
from agent_relay.workspace import register_candidate
from agent_relay.verification import register_verifier,run_verifier
from agent_relay.selftest import APP_SOURCE,ORACLE_SOURCE


def gates(*ids):
    def decorate(fn):
        fn.gate_ids=ids
        return fn
    return decorate


class Clock:
    def __init__(self):self.value=time.time()
    def __call__(self):return self.value
    def advance(self,n):self.value+=n


class RelayCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="rt-")
        self.base=Path(self.tmp.name);self.home=self.base/"ctl"
        self.clock=Clock();self.store=Store.initialize(self.home);self.store.clock=self.clock
        self.c=Controller(self.store);self.key=self.store.key
        self.repo=self.base/"repo";self.repo.mkdir()
        self.cmd("workflow.create",id="w",directive="Preserve authorized work and every outstanding obligation",constraints=["Do not claim an untested result works"])
        self.cmd("requirement.add",id="r",workflow="w",text="Required original behavior")
        self.cmd("source.put",id="identity",workflow="w",source_kind="Agent.md",text="Agent, provider-neutral identity",expected_rev=0)

    def tearDown(self):self.tmp.cleanup()

    def cmd(self,op,/,token=None,cid=None,**p):
        return self.c.command(token or self.key,cid or fresh_id("cmd"),op,p)

    def get(self,kind,id,token=None):return self.c.query(token or self.key,"get",{"kind":kind,"id":id})

    def worker(self,id="worker",workflow="w"):
        self.cmd("grant.create",id=id,workflow=workflow)
        return self.c.issue_token(self.key,id)

    def task(self,id="t",**extra):
        p={"id":id,"workflow":"w","title":"Task "+id,"requirements":["r"],"resources":["task/"+id],**extra}
        return self.cmd("task.create",**p)["task"]

    def claim(self,id="t",token=None,ttl=300):
        a=self.cmd("task.claim",token=token,id=id,provider="test-client",ttl=ttl)["attempt"]
        c=self.cmd("context.hydrate",token=token,attempt=a["id"])["context"]
        return a,c

    def prepare_file(self,action="a",name="x.txt",data=b"hello",expected="ABSENT",token=None,ttl=300):
        self.cmd("repo.register",id="repo",workflow="w",root=str(self.repo))
        self.task(resources=["repo/repo"],repos=["repo"])
        a,c=self.claim(token=token,ttl=ttl)
        result=self.cmd("action.prepare",token=token,id=action,attempt=a["id"],context=c["id"],type="file.write",
                  args={"repo":"repo","path":name,"expected_sha256":expected,"data_b64":base64.b64encode(data).decode()})
        return a,c,result["action"]

    def application(self,source=APP_SOURCE,oracle=ORACLE_SOURCE,ttl=300):
        (self.repo/"app.py").write_text(source)
        od=self.base/"oracle";od.mkdir();(od/"test_app.py").write_text(oracle)
        self.cmd("repo.register",id="repo",workflow="w",root=str(self.repo))
        register_verifier(self.c,self.key,fresh_id("verifier"),{"id":"v","workflow":"w","oracle_root":str(od),"min_tests":1})
        self.task(resources=["repo/repo"],repos=["repo"],verifiers=["v"])
        a,c=self.claim(ttl=ttl)
        cand=register_candidate(self.c,self.key,fresh_id("capture"),{"id":"c","attempt":a["id"],"context":c["id"]})["candidate"]
        return a,c,cand

    def verify(self):return run_verifier(self.c,self.key,fresh_id("verify"),{"candidate":"c","verifier":"v"})

    @contextmanager
    def error(self,code):
        with self.assertRaises(RelayError) as caught:
            yield
        self.assertEqual(caught.exception.code,code,caught.exception.message)
