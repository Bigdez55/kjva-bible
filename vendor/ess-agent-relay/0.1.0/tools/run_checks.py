#!/usr/bin/env python3
"""Run shipped tests against a verified source tree OR the separately installed runtime."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sqlite3
import sys
import time
import traceback
import unittest
import warnings
from verify_package import ROOT,verify

# These retain the original contracts, not a new set of easier tests with recycled names.
GAPS={
'G01':'Local POSIX path/capture tests; macOS case-insensitive filesystem execution is not certified.',
'G02':'Original audited v1 source and 48-test suite were not available; compatibility equivalence is unproven.',
'G03':'Authority-revision tests cover this runtime API, not hidden provider state or same-UID administrator tampering.',
'G04':'Explicit requirement preservation/disposition is tested; legacy requirement migration is not.',
'G05':'Scoped, expiring, consumed decisions are tested through this runtime.',
'G06':'Strict domain/RPC validation is tested for supplied public commands.',
'G07':'Derived acceptance rejects missing/failed verification; actual user application deployment is not tested.',
'G08':'Source/contract/repository/oracle binding is tested locally; external services are not reproducible candidate inputs.',
'G09':'Task dependency admission is exercised in this runtime.',
'G10':'Mandatory source/intent/obligation inclusion and budget failure are tested; actual model ingestion is not observable.',
'G11':'Untrusted memory cannot replace approved sources; semantic retrieval/provider injection is not implemented.',
'G12':'Real daemon reset with cold manual-client continuation; not actual model-session or compaction certification.',
'G13':'Several real/deterministic crash boundaries exercised; not physical power loss or every external adapter.',
'G14':'Transactional per-actor request ID and exact-payload deduplication are tested.',
'G15':'Real fixture application and durable SQLite readback/restart; no user browser/UI deployment.',
'G16':'A prose-only Python application impostor fails; no browser-page adapter tested.',
'G17':'Hardcoded success and backend loss fail the real fixture oracle; not the user production application.',
'G18':'Independent local threads/processes/socket clients commit; not distributed controllers.',
'G19':'Local hierarchical resource fences and stale acceptance rejection; no enforced Git/deployment publisher.',
'G20':'Registered sources/revisions and live candidate freshness are checked; no background filesystem watcher.',
'G21':'Explicit producer revision invalidates candidate; no live cross-repository event-fabric integration.',
'G22':'Multiple repository inputs captured in one vector; not an assembled deployed multi-repo application.',
'G23':'Partial two-resource effect recovery tested, not interrupted Git publication/deployment across repos.',
'G24':'No native installed provider lifecycle, hook, tool-interception or compaction adapter is enabled.',
'G25':'Manual worker rotation/release preserves job; no real provider rate-limit exercise.',
'G26':'Real SIGKILL plus stale ownership/process observations; no hostile surviving same-UID writer containment.',
'G27':'Multi-host mode is not implemented or enabled; Unix-domain socket/local service only.',
'G28':'Scope checks, secret rejection and key-free backup tested; external one-authority enforcement needs operator fencing.',
'G29':'Incremental hot-path tests and bounded contention samples; not huge-history or 24-hour endurance certification.',
'G30':'No legacy schema migration or original-source rollback equivalence implementation.',
'G31':'Package manifest preflight and installed module/source identity recorded; unsigned integrity is not publisher authentication.',
'G32':'Known unpatched WAL rejected; actual run uses rollback fallback. Patched WAL library was not installed/exercised here.',
'G33':'Connections close on tested success/failure/rollback paths with ResourceWarnings promoted to errors; no long soak.',
'G34':'Preparation/projections/outbox/blob references atomic in tested local transactions.',
'G35':'Duplicate/conflicting/late receipts handled with API authority; no external signed receipt adapter.',
'G36':'Prepared-vs-sent cancellation and revocation tested; external operations cannot be retroactively undone.',
'G37':'Ambiguous file absence and unknown commands hold safely; no destination idempotency-TTL adapter.',
'G38':'Deterministic projection replay and unknown-schema rejection; no cross-version upcaster/migration.',
'G39':'Restore new local key/generation + recovery hold; external original-authority fencing is an operator attestation.',
'G40':'Actual serialized RPC context body is bound; hidden model prompts/compaction remain outside observation.',
'G41':'API scope checks only; same-UID code, filesystem/network and provider transfers are not sandboxed.',
'G42':'Immutable registered real oracle rejects skips/zero/fail/timeouts; malicious same-UID code can bypass OS-level isolation.',
'G43':'Local least-attempted queue fairness/independent progress tested; no sustained provider budget SLA.',
'G44':'Raw benchmark intervals avoid full scrub; startup/manual scrub exists, periodic enforcement is operational.',
'G45':'Two stable full-source passes plus dirty/untracked/mode capture; not an atomic filesystem snapshot.',
'G46':'Installed/source/historical evidence separated with hashes; no external publisher signature/attestation.'}


def tree_hash(root:Path):
    entries=[]
    for path in sorted(root.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo'):
            entries.append({'path':path.relative_to(root).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return hashlib.sha256(json.dumps(entries,sort_keys=True,separators=(',',':')).encode()).hexdigest(),entries

class Result(unittest.TextTestResult):
    records=[]
    def startTest(self,test):
        super().startTest(test);self.began=time.perf_counter()
        method=getattr(test,getattr(test,'_testMethodName',''),None)
        self.current={'test':test.id(),'gate_ids':list(getattr(method,'gate_ids',())), 'status':'RUNNING'}
    def addSuccess(self,test):super().addSuccess(test);self.current['status']='PASS'
    def addFailure(self,test,err):super().addFailure(test,err);self.current.update(status='FAIL',traceback=self._exc_info_to_string(err,test))
    def addError(self,test,err):super().addError(test,err);self.current.update(status='ERROR',traceback=self._exc_info_to_string(err,test))
    def addSkip(self,test,reason):super().addSkip(test,reason);self.current.update(status='SKIP',reason=reason)
    def addExpectedFailure(self,test,err):super().addExpectedFailure(test,err);self.current['status']='EXPECTED_FAILURE'
    def addUnexpectedSuccess(self,test):super().addUnexpectedSuccess(test);self.current['status']='UNEXPECTED_SUCCESS'
    def addSubTest(self,test,subtest,err):
        super().addSubTest(test,subtest,err)
        if err:self.current.update(status='FAIL',traceback=self._exc_info_to_string(err,test))
    def stopTest(self,test):
        self.current['elapsed_s']=time.perf_counter()-self.began;self.records.append(self.current.copy());super().stopTest(test)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expect-installed',action='store_true')
    parser.add_argument('--source',action='store_true',help='explicit development source-mode; never silently used in installed checks')
    parser.add_argument('--development-unsealed',action='store_true',help='build-time only: manifest is not yet sealed')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.expect_installed and args.source:parser.error('choose installed OR source')
    args.out.mkdir(parents=True,exist_ok=True)
    integrity={'sealed':False,'mode':'explicit build-time unsealed source verification'} if args.development_unsealed else verify()
    if args.source:sys.path.insert(0,str(ROOT/'src'))
    spec=importlib.util.find_spec('agent_relay')
    if spec is None or spec.origin is None:raise RuntimeError('Install the wheel first, or explicitly request --source')
    if args.expect_installed and Path(spec.origin).is_relative_to(ROOT/'src'):raise RuntimeError('Source checkout would shadow installed runtime')
    sys.path.insert(0,str(ROOT/'tests'))
    import agent_relay
    installed_root=Path(agent_relay.__file__).parent
    runtime_digest,runtime_files=tree_hash(installed_root)
    tests_digest,test_files=tree_hash(ROOT/'tests')
    source_digest,source_files=tree_hash(ROOT/'src/agent_relay')
    if args.expect_installed and runtime_digest!=source_digest:raise RuntimeError('Installed module bytes differ from supplied source candidate')
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    Result.records=[]
    began=time.perf_counter();started=datetime.now(timezone.utc).isoformat()
    with (args.out/'unittest.log').open('w') as log:
        with warnings.catch_warnings():
            warnings.simplefilter('error',ResourceWarning)
            result=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=Result).run(suite)
    ok=result.wasSuccessful() and not result.skipped and not result.expectedFailures and all(r['status']=='PASS' for r in result.records)
    report={'ok':ok,'started_at':started,'elapsed_s':time.perf_counter()-began,'tests_run':result.testsRun,
            'counts':dict(Counter(x['status'] for x in result.records)),'package_integrity':integrity,
            'environment':{'python':sys.version,'executable':sys.executable,'platform':platform.platform(),
                           'sqlite':sqlite3.sqlite_version,'module_path':str(installed_root),'installed_mode':args.expect_installed},
            'runtime_sha256':runtime_digest,'tests_sha256':tests_digest,'source_sha256':source_digest,
            'runtime_files':runtime_files,'test_files':test_files,'invocation':sys.argv,
            'resource_warning_policy':'error','records':result.records,
            'scope':'single-host trusted-workers local tests; no claim of complete original G01-G46 certification'}
    (args.out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    contract_path=ROOT/'contracts/ORIGINAL_G01_G46.json'
    contracts=json.loads(contract_path.read_text());coverage=[]
    for gate in contracts['gates']:
        id=gate['id'];items=[x for x in result.records if id in x['gate_ids']]
        local='PASS' if items and all(x['status']=='PASS' for x in items) else 'FAIL' if items else 'NOT_RUN'
        disposition='OUT_OF_PROFILE' if id=='G27' else 'BLOCKED_MISSING_ORIGINAL_SOURCE' if id in {'G02','G30'} else 'NO_ENABLED_NATIVE_ADAPTER' if id=='G24' else 'PARTIAL_EVIDENCE_NOT_FULL_CERTIFICATION'
        coverage.append({'id':id,'title':gate['title'],'required_behavior':gate['required_behavior'],
                         'local_test_status':local,'executed_test_count':len(items),'test_ids':[x['test'] for x in items],
                         'original_contract_disposition':disposition,'remaining_boundary':GAPS[id]})
    cov={'generated_from':'verification.json','original_contract_sha256':hashlib.sha256(contract_path.read_bytes()).hexdigest(),
         'runtime_sha256':runtime_digest,'local_gate_counts':dict(Counter(g['local_test_status'] for g in coverage)),
         'all_original_contracts_certified':False,'gates':coverage}
    (args.out/'gate_coverage.json').write_text(json.dumps(cov,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('ok','tests_run','counts','elapsed_s','runtime_sha256')},indent=2))
    print(json.dumps({'local_gate_counts':cov['local_gate_counts'],'all_original_contracts_certified':False},indent=2))
    return 0 if ok else 1

if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,RuntimeError,ValueError) as e:print(str(e),file=sys.stderr);sys.exit(2)
