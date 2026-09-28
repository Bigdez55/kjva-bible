import base64
from pathlib import Path
import os
import sys
from agent_relay.codec import digest
from agent_relay.controller import fresh_id
from agent_relay.workspace import register_candidate,stable_tree
from agent_relay.verification import register_verifier,run_verifier
from agent_relay.selftest import APP_SOURCE,ORACLE_SOURCE
from support import RelayCase,gates


class VerificationTests(RelayCase):
    @gates("G08","G12","G42")
    def test_cold_client_can_read_persisted_verifier_report_and_run(self):
        self.application()
        evidence=self.verify()["evidence"]
        retrieved=self.get("evidence",evidence["id"])
        self.assertEqual(retrieved["report"]["unit_report"]["tests"],3)
        run=self.get("verification_run",evidence["run"])
        self.assertEqual(run["evidence"],evidence["id"])
        self.assertEqual(run["status"],"PASS")

    @gates("G07","G08","G15")
    def test_real_application_can_be_accepted_only_after_executed_oracle(self):
        a,c,candidate=self.application()
        result=self.verify();e=result["evidence"]
        self.assertEqual(e["status"],"PASS",result)
        self.assertEqual(e["tests"],3)
        accepted=self.cmd("task.accept",id="t",candidate="c",evidence=[e["id"]])
        self.assertEqual(accepted["task"]["status"],"ACCEPTED")
        self.assertEqual(self.get("requirement","r")["status"],"SATISFIED")
        self.cmd("workflow.accept",id="w")
        self.store.doctor(True)

    @gates("G07")
    def test_missing_evidence_never_accepts_candidate(self):
        self.application()
        with self.error("MISSING_EVIDENCE"):self.cmd("task.accept",id="t",candidate="c",evidence=[])
        self.assertEqual(self.get("task","t")["status"],"RUNNING")

    @gates("G07","G42")
    def test_worker_cannot_register_oracle_or_report_fake_pass(self):
        worker=self.worker();self.application()
        with self.error("UNKNOWN_COMMAND"):
            self.cmd("evidence.record",token=worker,id="fake",status="PASS")
        with self.error("FORBIDDEN"):
            run_verifier(self.c,worker,fresh_id("verify"),{"candidate":"c","verifier":"v"})

    @gates("G08","G45")
    def test_edit_after_pass_keeps_historical_pass_but_rejects_acceptance(self):
        self.application();result=self.verify();e=result["evidence"]
        (self.repo/"app.py").write_text(APP_SOURCE+"\n# changed after verification\n")
        with self.error("STALE_CANDIDATE"):self.cmd("task.accept",id="t",candidate="c",evidence=[e["id"]])
        self.assertEqual(self.get("evidence",e["id"])["status"],"PASS")

    @gates("G08","G45")
    def test_untracked_input_after_capture_changes_candidate(self):
        self.application();(self.repo/"new_config.json").write_text('{"feature":true}')
        with self.error("STALE_CANDIDATE"):self.verify()

    @gates("G45")
    def test_capture_contains_untracked_and_binary_inputs(self):
        (self.repo/"payload.bin").write_bytes(bytes(range(256)))
        a,c,candidate=self.application()
        self.assertIn("payload.bin",candidate["manifests"]["repo"]["files"])
        self.assertEqual(candidate["manifests"]["repo"]["files"]["payload.bin"]["sha256"],digest(bytes(range(256))))

    @gates("G16")
    def test_static_prose_impostor_fails_required_behavior(self):
        self.application(source='"""This application is fully operational and production ready."""\n')
        result=self.verify()
        self.assertEqual(result["evidence"]["status"],"FAIL")
        with self.error("INVALID_EVIDENCE"):self.cmd("task.accept",id="t",candidate="c",evidence=[result["evidence"]["id"]])

    @gates("G17")
    def test_hardcoded_success_cannot_fake_durable_state(self):
        fake='def put(*args): return True\ndef get(*args): return "42"\n'
        self.application(source=fake)
        result=self.verify()
        self.assertEqual(result["evidence"]["status"],"FAIL")
        self.assertGreater(result["report"]["unit_report"]["errors"]+result["report"]["unit_report"]["failures"],0)

    @gates("G17")
    def test_backend_write_failure_is_not_success(self):
        bad=APP_SOURCE.replace('conn.commit()','raise OSError("backend unavailable")')
        self.application(source=bad)
        result=self.verify()
        self.assertEqual(result["evidence"]["status"],"FAIL")

    @gates("G42")
    def test_zero_collected_tests_fails(self):
        self.application(oracle='"""A document, not a test."""\n')
        result=self.verify()
        self.assertEqual(result["evidence"]["tests"],0)
        self.assertEqual(result["evidence"]["status"],"FAIL")

    @gates("G42")
    def test_skipped_required_test_fails(self):
        self.application(oracle='import unittest\nclass T(unittest.TestCase):\n @unittest.skip("not implemented")\n def test_behavior(self): pass\n')
        result=self.verify()
        self.assertEqual(result["report"]["unit_report"]["skipped"],1)
        self.assertEqual(result["evidence"]["status"],"FAIL")

    @gates("G42")
    def test_expected_failure_is_not_acceptance(self):
        self.application(oracle='import unittest\nclass T(unittest.TestCase):\n @unittest.expectedFailure\n def test_behavior(self): self.assertTrue(False)\n')
        result=self.verify()
        self.assertEqual(result["evidence"]["status"],"FAIL")

    @gates("G42")
    def test_registered_oracle_is_immutable_not_reread_from_mutable_source(self):
        self.application(source='def put(*args): return True\ndef get(*args): return "42"\n')
        (self.base/"oracle"/"test_app.py").write_text('import unittest\nclass T(unittest.TestCase):\n def test_fake(self): self.assertTrue(True)\n')
        result=self.verify()
        self.assertEqual(result["evidence"]["status"],"FAIL")

    @gates("G14","G42")
    def test_verification_request_deduplication_does_not_run_twice(self):
        self.application()
        first=run_verifier(self.c,self.key,"same-verify",{"candidate":"c","verifier":"v"})
        with self.error("VERIFY_ALREADY_STARTED"):
            run_verifier(self.c,self.key,"same-verify",{"candidate":"c","verifier":"v"})
        self.assertEqual(self.get("evidence",first["evidence"]["id"])["status"],"PASS")

    @gates("G19","G26")
    def test_old_attempt_cannot_promote_old_candidate_after_takeover(self):
        a,c,candidate=self.application(ttl=0.1)
        result=self.verify()
        self.clock.advance(1)
        successor,_=self.claim()
        with self.error("STALE_FENCE"):
            self.cmd("task.accept",id="t",candidate="c",evidence=[result["evidence"]["id"]])

    @gates("G20")
    def test_source_change_invalidates_pass_without_deleting_it(self):
        self.application();result=self.verify()
        self.cmd("source.put",id="identity",workflow="w",source_kind="Agent.md",text="new contract",expected_rev=1)
        with self.error("STALE_CANDIDATE"):
            self.cmd("task.accept",id="t",candidate="c",evidence=[result["evidence"]["id"]])
        self.assertEqual(self.get("evidence",result["evidence"]["id"])["status"],"PASS")

    @gates("G21")
    def test_registered_upstream_revision_invalidates_candidate(self):
        self.application();result=self.verify()
        self.cmd("repo.observe",id="repo",revision="new-producer-revision")
        with self.error("STALE_CANDIDATE"):
            self.cmd("task.accept",id="t",candidate="c",evidence=[result["evidence"]["id"]])

    @gates("G22")
    def test_cross_repository_vector_contains_all_declared_inputs(self):
        one=self.base/"one";two=self.base/"two";one.mkdir();two.mkdir()
        (one/"api.py").write_text("VERSION=1\n");(two/"client.py").write_text("EXPECTED=1\n")
        self.cmd("repo.register",id="one",workflow="w",root=str(one))
        self.cmd("repo.register",id="two",workflow="w",root=str(two))
        self.task(resources=["repo/one","repo/two"],repos=["one","two"])
        a,c=self.claim()
        candidate=register_candidate(self.c,self.key,fresh_id("capture"),{"id":"c","attempt":a["id"],"context":c["id"]})["candidate"]
        self.assertEqual(set(candidate["vector"]),{"one","two"})
        self.assertNotEqual(candidate["vector"]["one"]["manifest_hash"],candidate["vector"]["two"]["manifest_hash"])

    @gates("G05")
    def test_reopen_requires_exact_accepted_task_decision(self):
        self.application();result=self.verify()
        t=self.cmd("task.accept",id="t",candidate="c",evidence=[result["evidence"]["id"]])["task"]
        self.cmd("decision.create",id="d",workflow="w",target_kind="task",target_id="t",target_rev=t["rev"],operation="reopen",reason="new implementation request")
        self.cmd("task.reopen",id="t",decision="d")
        self.assertEqual(self.get("requirement","r")["status"],"OPEN")
        self.assertEqual(self.get("task","t")["spec_revision"],2)

    @gates("G01","G45")
    def test_case_alias_candidate_is_rejected(self):
        (self.repo/"A.txt").write_text("first");(self.repo/"a.txt").write_text("second")
        # This test's Linux fixture supports two distinct names. On a case-insensitive
        # volume, the second creation replaces the first and no two-file collision exists.
        names=[x.name for x in self.repo.iterdir()]
        if len(names)==2:
            with self.error("PATH_ALIAS"):stable_tree(self.repo,[])
        else:
            self.assertEqual(len(names),1)

    @gates("G01","G28")
    def test_secret_path_capture_is_rejected_not_exported(self):
        (self.repo/".env").write_text("API_TOKEN=DO_NOT_EXPORT")
        with self.error("SENSITIVE_PATH"):stable_tree(self.repo,[])

    @gates("G01","G19")
    def test_duplicate_registered_worktree_cannot_bypass_lock_namespace(self):
        self.cmd("repo.register",id="one",workflow="w",root=str(self.repo))
        with self.error("REPO_OVERLAP"):
            self.cmd("repo.register",id="two",workflow="w",root=str(self.repo))

    @gates("G09")
    def test_unaccepted_dependency_prevents_admission(self):
        self.task(id="parent");self.task(id="child",deps=["parent"])
        with self.error("NOT_READY"):self.claim("child")
        # Planning/read-only access remains possible without an execution lease.
        self.assertEqual(self.get("task","child")["deps"],["parent"])

    @gates("G45")
    def test_capture_race_between_passes_is_rejected(self):
        from unittest.mock import patch
        import agent_relay.workspace as module
        f=self.repo/"race.txt";f.write_text("first")
        original=module.scan_tree;calls=[0]
        def changed(root,exclude):
            result=original(root,exclude);calls[0]+=1
            if calls[0]==1:f.write_text("second")
            return result
        with patch.object(module,"scan_tree",changed):
            with self.error("CAPTURE_RACE"):module.stable_tree(self.repo,[])
