#!/usr/bin/env python3
"""Execute the EXACT archived 0.1.0 test sources against the installed NEW runtime.

This is 0.1.0 compatibility evidence, not the unavailable pre-0.1 audit suite.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
from verify_package import verify,ROOT

CHILD=r'''
import hashlib,json,sys,time,unittest,warnings
from pathlib import Path
import agent_relay
sys.path.insert(0,sys.argv[1])
from agent_relay.certification import runtime_identity
before=runtime_identity()[0]
assert not Path(agent_relay.__file__).is_relative_to(Path(sys.argv[2])/'src')
class Result(unittest.TextTestResult):
    records=[]
    def addSuccess(self,test):super().addSuccess(test);self.records.append({'test':test.id(),'status':'PASS'})
    def addError(self,test,error):super().addError(test,error);self.records.append({'test':test.id(),'status':'ERROR','traceback':self._exc_info_to_string(error,test)})
    def addFailure(self,test,error):super().addFailure(test,error);self.records.append({'test':test.id(),'status':'FAIL','traceback':self._exc_info_to_string(error,test)})
    def addSkip(self,test,reason):super().addSkip(test,reason);self.records.append({'test':test.id(),'status':'SKIP','reason':reason})
suite=unittest.defaultTestLoader.discover(sys.argv[1]);start=time.perf_counter()
with open(sys.argv[3]+'/legacy-unittest.log','w') as log, warnings.catch_warnings():
    warnings.simplefilter('error',ResourceWarning)
    result=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=Result).run(suite)
after=runtime_identity()[0]
report={'ok':result.wasSuccessful() and not result.skipped and before==after,'tests_run':result.testsRun,'records':result.records,'elapsed_s':time.perf_counter()-start,
 'runtime_sha256':before,'runtime_after_sha256':after,'installed_version':agent_relay.__version__,'module_path':agent_relay.__file__,'test_source':'EXACT_ARCHIVED_0.1.0_TEST_BYTES','pre_0_1_audit_equivalence_claimed':False}
Path(sys.argv[3]+'/compatibility.json').write_text(json.dumps(report,indent=2)+'\n')
raise SystemExit(0 if report['ok'] else 1)
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--development-unsealed',action='store_true')
    a=parser.parse_args()
    if not a.development_unsealed:verify()
    a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=True)
    archive=ROOT/'compat/v0.1.0-regressions.zip'
    with tempfile.TemporaryDirectory(prefix='relay-compat-') as temp,zipfile.ZipFile(archive) as z:
        root=Path(temp);entries=[]
        for item in z.infolist():
            parts=Path(item.filename).parts
            if len(parts)==2 and parts[0]=='tests' and parts[1].endswith('.py'):
                raw=z.read(item);target=root/parts[1];target.write_bytes(raw)
                entries.append({'path':item.filename,'sha256':hashlib.sha256(raw).hexdigest()})
        if not entries:raise RuntimeError('Missing original test source archive')
        env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME','RELAY_TOKEN')}
        p=subprocess.run([sys.executable,'-I','-c',CHILD,str(root),str(ROOT),str(a.out)],env=env,capture_output=True,text=True,timeout=120)
        (a.out/'compatibility-stderr.txt').write_text(p.stderr)
        (a.out/'source_manifest.json').write_text(json.dumps({'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':entries},indent=2)+'\n')
        if p.returncode:print(p.stderr,file=sys.stderr);return p.returncode
    result=json.loads((a.out/'compatibility.json').read_text())
    print(json.dumps({k:result[k] for k in ('ok','tests_run','installed_version','runtime_sha256','elapsed_s')},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
