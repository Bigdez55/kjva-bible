from contextlib import closing
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import warnings
from agent_relay.codec import canonical,digest,decode_blob,encode_blob
from agent_relay.controller import Controller,fresh_id
from agent_relay.errors import RelayError
from agent_relay.store import Store,Transaction,wal_fixed
from support import RelayCase,gates


class StoreTests(RelayCase):
    @gates("G02","G33")
    def test_closed_connection_normal_and_exception_paths(self):
        with self.store.connection() as conn:conn.execute("SELECT 1")
        with self.assertRaises(sqlite3.ProgrammingError):conn.execute("SELECT 1")
        with self.assertRaises(RuntimeError):
            with self.store.connection(True) as failed:
                failed.execute("SELECT 1");raise RuntimeError("abort")
        with self.assertRaises(sqlite3.ProgrammingError):failed.execute("SELECT 1")

    @gates("G32")
    def test_auto_journal_is_safe_for_actual_linked_sqlite(self):
        report=self.store.doctor()
        self.assertEqual(report["foreign_keys"],1)
        self.assertEqual(report["journal_mode"],"wal" if wal_fixed() else "delete")
        self.assertEqual(report["synchronous"],2 if wal_fixed() else 3)

    @gates("G32")
    def test_wal_rejects_known_unpatched_library(self):
        if wal_fixed():
            other=Store.initialize(self.base/"wal",journal="wal")
            self.assertEqual(other.doctor()["journal_mode"],"wal")
        else:
            with self.error("SQLITE_WAL_UNPATCHED"):Store.initialize(self.base/"wal",journal="wal")
            self.assertFalse((self.base/"wal").exists())

    @gates("G32")
    def test_wal_fix_version_rules_include_backports_not_other_old_branches(self):
        self.assertTrue(wal_fixed((3,51,3)));self.assertTrue(wal_fixed((3,53,0)))
        self.assertTrue(wal_fixed((3,50,7)));self.assertTrue(wal_fixed((3,44,6)))
        for v in ((3,51,2),(3,50,6),(3,46,1),(3,45,99)):
            self.assertFalse(wal_fixed(v))

    @gates("G34")
    def test_conditional_lossless_compression_and_deduplication(self):
        def apply(tx,a,now):
            x=tx.blob(b"same-data"*10000);y=tx.blob(b"same-data"*10000)
            return {"first":x,"second":y}
        r=self.store.command(self.key,"blobs","_test.blobs",{},apply)
        self.assertEqual(r["first"],r["second"])
        with self.store.connection() as conn:
            codec,size,payload=conn.execute("SELECT codec,size,data FROM blobs WHERE hash=?",(r["first"],)).fetchone()
            self.assertEqual(codec,"zlib");self.assertLess(len(payload),size)
            self.assertEqual(Transaction(conn).read_blob(r["first"]),b"same-data"*10000)
        self.store.doctor(True)

    @gates("G34")
    def test_blob_quota_failure_preserves_old_store(self):
        with self.store.connection(True) as conn:
            conn.execute("UPDATE meta SET value='1' WHERE key='blob_quota'")
        before=self.store.doctor()["chain_head"]
        with self.error("STORE_QUOTA"):
            self.cmd("memory.add",id="huge",workflow="w",text="this is too large",origin="test")
        self.assertEqual(before,self.store.doctor()["chain_head"])

    @gates("G38")
    def test_replay_rebuilds_projections_and_command_dedup_without_effects(self):
        a,c,action=self.prepare_file()
        before=self.store.doctor(True)
        with self.store.connection(True) as conn:
            conn.execute("DELETE FROM objects");conn.execute("DELETE FROM commands")
        with self.error("PROJECTION_DRIFT"):self.store.doctor(True)
        result=self.store.rebuild()
        self.assertEqual(result["effects_dispatched"],0)
        after=self.store.doctor(True)
        self.assertEqual(before["chain_head"],after["chain_head"])
        self.assertEqual(before["objects"],after["objects"])
        self.assertFalse((self.repo/"x.txt").exists())
        self.store.rebuild();self.store.doctor(True)

    @gates("G38")
    def test_unknown_database_schema_is_rejected(self):
        with self.store.connection(True) as conn:conn.execute("PRAGMA user_version=900")
        with self.error("SCHEMA_VERSION"):self.store.doctor()

    @gates("G02","G46")
    def test_event_table_rejects_mutation(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.connection(True) as conn:conn.execute("UPDATE events SET hash='wrong' WHERE seq=1")
        self.store.doctor(True)

    @gates("G38","G46")
    def test_corrupt_event_fails_integrity_not_silently_rehashed(self):
        with self.store.connection(True) as conn:
            conn.execute("DROP TRIGGER events_no_update");conn.execute("UPDATE events SET body='{}' WHERE seq=1")
        with self.error("CHAIN_CORRUPT"):self.store.doctor(True)
        with self.error("CHAIN_CORRUPT"):self.store.rebuild()

    @gates("G44")
    def test_cold_blob_corruption_detected_by_explicit_scrub(self):
        self.cmd("memory.add",id="cold",workflow="w",text="cold data retained",origin="test")
        m=self.get("memory","cold")
        with self.store.connection(True) as conn:
            conn.execute("DROP TRIGGER blobs_no_update")
            conn.execute("UPDATE blobs SET data=? WHERE hash=?",(b"bad",m["blob"]))
        with self.error("CORRUPT_BLOB"):self.store.doctor(True)

    @gates("G34")
    def test_decompression_bomb_is_length_bounded(self):
        codec,payload=encode_blob(b"x"*10000)
        with self.error("CORRUPT_BLOB"):decode_blob(codec,payload,4,digest(b"xxxx"))

    @gates("G28","G39")
    def test_backup_excludes_keys_restore_rotates_credentials_and_holds_actions(self):
        worker=self.worker();self.task();a,c=self.claim(token=worker)
        dest=self.base/"backup";self.store.backup(dest)
        self.assertEqual({p.name for p in dest.iterdir()},{"relay.sqlite3","backup.json"})
        restored=Store.restore(dest,self.base/"restored");restored.clock=self.clock
        self.assertNotEqual(restored.key,self.key)
        ctl=Controller(restored)
        with self.error("AUTH_GENERATION"):ctl.query(worker,"status",{})
        with self.error("RECOVERY_ONLY"):
            ctl.command(restored.key,"new","workflow.create",{"id":"new","directive":"new"})
        self.assertEqual(restored.doctor(True)["mode"],"RECOVERY_ONLY")

    @gates("G39")
    def test_restore_release_requires_explicit_original_fence_attestation(self):
        dest=self.base/"backup";self.store.backup(dest)
        restored=Store.restore(dest,self.base/"restored");restored.clock=self.clock;ctl=Controller(restored)
        with self.error("RESTORE_HELD"):
            ctl.command(restored.key,"resume","restore.resume",{"original_authority_fenced":False,"reconciliation_report":"no"})
        r=ctl.command(restored.key,"resume2","restore.resume",{"original_authority_fenced":True,"reconciliation_report":"Operator stopped original authority; inspected destination effects."})
        self.assertEqual(r["mode"],"ACTIVE")
        restored.doctor(True)

    @gates("G39")
    def test_restore_unknown_action_prevents_operator_release(self):
        a,c,action=self.prepare_file();self.cmd("action.start",id=action["id"])
        dest=self.base/"backup";self.store.backup(dest)
        restored=Store.restore(dest,self.base/"restored");restored.clock=self.clock;ctl=Controller(restored)
        with self.error("RESTORE_HELD"):
            ctl.command(restored.key,"resume","restore.resume",{"original_authority_fenced":True,"reconciliation_report":"Not enough: effects still unknown."})

    @gates("G02","G31")
    def test_initialization_never_overwrites_existing_home(self):
        before=self.store.doctor()["chain_head"]
        with self.error("ALREADY_EXISTS"):Store.initialize(self.home)
        self.assertEqual(before,self.store.doctor()["chain_head"])

    @gates("G28")
    def test_insecure_control_permissions_are_rejected(self):
        (self.home/"owner.key").chmod(0o644)
        with self.error("INSECURE_PERMISSIONS"):Store(self.home)
        (self.home/"owner.key").chmod(0o600)

    @gates("G26","G34")
    def test_sigkill_uncommitted_transaction_rolls_back(self):
        before=self.store.doctor(True)
        script="import sqlite3,sys,os,signal;c=sqlite3.connect(sys.argv[1]);c.execute('BEGIN IMMEDIATE');c.execute(\"INSERT INTO objects VALUES('task','ghost','w',1,'{}')\");os.kill(os.getpid(),signal.SIGKILL)"
        r=subprocess.run([sys.executable,"-c",script,str(self.store.db)],capture_output=True,timeout=10)
        self.assertEqual(r.returncode,-signal.SIGKILL)
        self.assertEqual(before["chain_head"],self.store.doctor(True)["chain_head"])
        with self.error("NOT_FOUND"):self.get("task","ghost")

    @gates("G10","G38")
    def test_lossless_snapshot_keeps_obligations_and_unknown_actions(self):
        a,c,action=self.prepare_file()
        snap=self.cmd("snapshot.create")["snapshot"]
        with self.store.connection() as conn:
            body=json.loads(Transaction(conn).read_blob(snap["blob"]))
        self.assertTrue(any(x["kind"]=="requirement" and x["id"]=="r" for x in body["records"]))
        self.assertTrue(any(x["kind"]=="action" and x["data"]["outcome"]=="UNKNOWN" for x in body["records"]))
        self.store.doctor(True)

    @gates("G29","G34")
    def test_journal_capacity_holds_new_work_without_deleting_history(self):
        before=self.store.doctor()
        with self.store.connection(True) as conn:
            conn.execute("UPDATE meta SET value='1' WHERE key='journal_quota'")
        with self.error("JOURNAL_QUOTA"):
            self.cmd("memory.add",id="overflow",workflow="w",text="new work",origin="test")
        self.assertEqual(self.store.doctor()["chain_head"],before["chain_head"])
        self.assertEqual(self.store.doctor()["events"],before["events"])

    @gates("G29","G35")
    def test_late_receipt_has_reserved_journal_capacity(self):
        a,c,action=self.prepare_file();self.cmd("action.start",id=action["id"])
        with self.store.connection(True) as conn:
            conn.execute("UPDATE meta SET value='1' WHERE key='journal_quota'")
        receipt=self.cmd("action.receipt",id=action["id"],receipt_id="late",outcome="APPLIED",details={})
        self.assertEqual(receipt["action"]["outcome"],"APPLIED")
        self.store.doctor(True)
