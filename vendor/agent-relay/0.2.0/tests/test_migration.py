from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from agent_relay.codec import canonical,digest
from agent_relay.controller import Controller
from agent_relay.dispatch import reconcile
from agent_relay.errors import RelayError
from agent_relay.migration import plan,prepare,rollback,activate,history_fingerprint,MARKER,MANIFEST
from agent_relay.store import Store
from support import gates
from legacy_support import legacy
from integration_support import daemon


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='rly-migrate-');self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.old=self.base/'old';self.new=self.base/'new'

    def events(self,home):
        with closing(sqlite3.connect(home/'relay.sqlite3')) as conn:
            return conn.execute('SELECT seq,previous,hash,body FROM events ORDER BY seq').fetchall()

    def blobs(self,home):
        with closing(sqlite3.connect(home/'relay.sqlite3')) as conn:
            return conn.execute('SELECT hash,codec,size,data FROM blobs ORDER BY hash').fetchall()

    def held_evaluation(self):
        # Tests of migration admission use an explicit deterministic evaluator stub;
        # they do not claim these dictionaries are production acceptance reports.
        from agent_relay.certification import runtime_identity
        return {'ready':True,'runtime_sha256':runtime_identity()[0],'test_fixture_not_production_attestation':True}

    @gates('G30','G31')
    def test_plan_uses_actual_legacy_runtime_and_changes_no_database_bytes(self):
        original=legacy(self.old);before=digest((self.old/'relay.sqlite3').read_bytes())
        result=plan(self.old,self.new)
        self.assertEqual(result['source_schema'],1);self.assertEqual(result['target_schema'],2)
        self.assertEqual(result['source_fingerprint']['head'],original['doctor']['chain_head'])
        self.assertEqual(before,digest((self.old/'relay.sqlite3').read_bytes()))
        self.assertFalse(self.new.exists())
        self.assertIn('0.1.0',original['module'])

    @gates('G30','G02','G04','G38')
    def test_migration_preserves_exact_original_event_bytes_blobs_and_requirements(self):
        original=legacy(self.old);events=self.events(self.old);blobs=self.blobs(self.old)
        result=prepare(self.old,self.new)
        self.assertTrue(result['prepared']);self.assertEqual(self.events(self.old),events)
        self.assertEqual(self.events(self.new)[:len(events)],events)
        self.assertEqual(len(self.events(self.new)),len(events)+1)
        self.assertEqual(self.blobs(self.new),blobs)
        new=Store(self.new);c=Controller(new)
        self.assertEqual(c.query(new.key,'get',{'kind':'requirement','id':'r'})['text'],'Store and read back application data')
        self.assertEqual(new.doctor(True)['full_scrub'],'PASS')
        self.assertEqual(new.doctor()['mode'],'RECOVERY_ONLY')
        self.assertEqual(legacy(self.old,'inspect')['doctor']['mode'],'MIGRATION_HOLD')
        self.assertNotEqual(new.key,original['owner_key'])
        with self.assertRaises(RelayError):c.query(original['token'],'status',{})
        with self.assertRaises(RelayError):c.command(new.key,'no-dispatch','task.claim',{'id':'t','provider':'too-soon'})

    @gates('G30','G08','G46')
    def test_historical_real_application_test_pass_is_preserved_not_upgraded(self):
        old=legacy(self.old,'verified');before=self.events(self.old)
        prepare(self.old,self.new)
        new=Store(self.new);c=Controller(new)
        evidence=c.query(new.key,'get',{'kind':'evidence','id':old['evidence']['id']})
        self.assertEqual({k:evidence[k] for k in old['evidence']},old['evidence'])
        self.assertEqual(self.events(self.new)[:len(before)],before)
        manifest=json.loads((self.new/MANIFEST).read_text())
        m=c.query(new.key,'get',{'kind':'migration','id':manifest['id']})
        self.assertFalse(m['historical_evidence_upgraded']);self.assertEqual(m['effects_dispatched'],0)

    @gates('G30','G02','G39')
    def test_controlled_preactivation_rollback_reopens_original_binary_in_recovery_only(self):
        legacy(self.old);before=self.events(self.old)
        prepare(self.old,self.new);result=rollback(self.old,self.new)
        self.assertTrue(result['rolled_back']);self.assertEqual(self.events(self.old),before)
        self.assertEqual(legacy(self.old,'inspect')['doctor']['mode'],'RECOVERY_ONLY')
        new=Store(self.new);c=Controller(new)
        self.assertEqual(new.doctor(True)['mode'],'RETIRED')
        with self.assertRaises(RelayError):
            c.command(new.key,'resurrect','restore.resume',{'original_authority_fenced':True,'reconciliation_report':'cannot reopen retired target'})

    @gates('G30','G34','G39')
    def test_interrupted_migration_at_each_boundary_can_rollback_without_lost_history(self):
        for step in ('before_fence','after_fence','after_copy','before_publish','after_publish'):
            with self.subTest(step=step):
                base=self.base/step;base.mkdir();old=base/'old';new=base/'new'
                legacy(old);before=self.events(old)
                def stop(point):
                    if point==step:raise RuntimeError('injected interruption '+step)
                with self.assertRaisesRegex(RuntimeError,step):prepare(old,new,fault=stop)
                restored=rollback(old,new)
                self.assertTrue(restored['rolled_back']);self.assertEqual(before,self.events(old))
                self.assertEqual(legacy(old,'inspect')['doctor']['mode'],'RECOVERY_ONLY')

    @gates('G30','G35')
    def test_rollback_rejects_late_receipt_after_unfinalized_copy_marker(self):
        legacy(self.old,'unknown')
        def stop(point):
            if point=='after_copy':raise RuntimeError('stop')
        with self.assertRaises(RuntimeError):prepare(self.old,self.new,fault=stop)
        marker=json.loads((self.old/MARKER).read_text());stage=Path(marker['stage']);s=Store(stage)
        reconcile(Controller(s),s.key,'late-receipt',{'id':'action'})
        with self.assertRaises(RelayError) as failure:rollback(self.old,self.new)
        self.assertEqual(failure.exception.code,'ROLLBACK_UNSAFE')
        self.assertEqual(legacy(self.old,'inspect')['doctor']['mode'],'MIGRATION_HOLD')

    @gates('G30','G35','G39')
    def test_unknown_original_effect_blocks_activation_until_independent_readback(self):
        legacy(self.old,'unknown');prepare(self.old,self.new)
        with self.assertRaises(RelayError) as held:
            activate(self.old,self.new,self.held_evaluation(),'test fixture reviewed')
        self.assertEqual(held.exception.code,'RESTORE_HELD')
        new=Store(self.new)
        observed=reconcile(Controller(new),new.key,'readback',{'id':'action'})
        self.assertEqual(observed['action']['outcome'],'APPLIED')
        result=activate(self.old,self.new,self.held_evaluation(),'independent file readback completed')
        self.assertEqual(result['mode'],'ACTIVE')
        self.assertEqual(legacy(self.old,'inspect')['doctor']['mode'],'MIGRATION_HOLD')
        with self.assertRaises(RelayError) as refused:rollback(self.old,self.new)
        self.assertEqual(refused.exception.code,'ROLLBACK_UNSAFE')

    @gates('G30','G31')
    def test_acceptance_mismatch_cannot_activate_migrated_store(self):
        legacy(self.old);prepare(self.old,self.new)
        for value in ({'ready':False},{'ready':True,'runtime_sha256':'0'*64}):
            with self.subTest(value=value),self.assertRaises(RelayError) as held:
                activate(self.old,self.new,value,'missing current-candidate acceptance')
            self.assertEqual(held.exception.code,'ACCEPTANCE_HELD')
        self.assertEqual(Store(self.new).doctor()['mode'],'RECOVERY_ONLY')

    @gates('G30','G06')
    def test_unrecognized_schema_is_not_heuristically_imported(self):
        Store.initialize(self.old)
        with self.assertRaises(RelayError) as failure:prepare(self.old,self.new)
        self.assertEqual(failure.exception.code,'MIGRATION_UNSUPPORTED')
        self.assertFalse((self.old/MARKER).exists());self.assertFalse(self.new.exists())

    @gates('G30','G01')
    def test_existing_destination_and_nested_target_leave_source_unmodified(self):
        legacy(self.old);before=self.events(self.old);self.new.mkdir()
        for target in (self.new,self.old/'nested'):
            with self.assertRaises(RelayError):prepare(self.old,target)
            self.assertEqual(before,self.events(self.old));self.assertFalse((self.old/MARKER).exists())

    @gates('G30','G38')
    def test_corrupt_legacy_projection_rejected_before_source_fence(self):
        legacy(self.old)
        with closing(sqlite3.connect(self.old/'relay.sqlite3')) as conn:
            conn.execute("DELETE FROM objects WHERE kind='requirement'");conn.commit()
        with self.assertRaises(RelayError) as failure:prepare(self.old,self.new)
        self.assertEqual(failure.exception.code,'PROJECTION_DRIFT')
        self.assertFalse((self.old/MARKER).exists());self.assertFalse(self.new.exists())

    @gates('G30','G19')
    def test_migration_refuses_store_held_by_another_service_lock(self):
        from agent_relay.migration import home_lock
        legacy(self.old)
        with home_lock(self.old), self.assertRaises(RelayError) as failure:prepare(self.old,self.new)
        self.assertEqual(failure.exception.code,'SERVICE_RUNNING')

    @gates('G30','G38')
    def test_migrated_projection_rebuild_keeps_historical_hashes(self):
        legacy(self.old);prepare(self.old,self.new);before=self.events(self.new);s=Store(self.new)
        s.rebuild();self.assertEqual(before,self.events(self.new));self.assertEqual(s.doctor(True)['full_scrub'],'PASS')

    @gates('G30','G13','G39')
    def test_real_process_death_during_migration_leaves_fenced_recoverable_state(self):
        for step in ('after_copy','after_publish'):
            with self.subTest(step=step):
                folder=self.base/step;folder.mkdir();old=folder/'old';new=folder/'new'
                legacy(old);before=self.events(old)
                script="from pathlib import Path; import os,sys; from agent_relay.migration import prepare; prepare(Path(sys.argv[1]),Path(sys.argv[2]),fault=lambda step:os._exit(91) if step==sys.argv[3] else None)"
                child=subprocess.run([sys.executable,'-c',script,str(old),str(new),step],capture_output=True,text=True,timeout=10)
                self.assertEqual(child.returncode,91,child.stderr)
                self.assertEqual(legacy(old,'inspect')['doctor']['mode'],'MIGRATION_HOLD')
                self.assertTrue(rollback(old,new)['rolled_back'])
                self.assertEqual(before,self.events(old))
                self.assertEqual(legacy(old,'inspect')['doctor']['mode'],'RECOVERY_ONLY')

    @gates('G30','G01')
    def test_parent_symlink_alias_cannot_place_migration_inside_source(self):
        legacy(self.old);alias=self.base/'alias';alias.symlink_to(self.old,target_is_directory=True)
        with self.assertRaises(RelayError) as held:prepare(self.old,alias/'nested')
        self.assertEqual(held.exception.code,'MIGRATION_PATH')
        self.assertFalse((self.old/MARKER).exists())
