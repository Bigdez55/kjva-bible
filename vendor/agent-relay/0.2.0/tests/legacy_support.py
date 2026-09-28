"""Execute the frozen real 0.1.0 wheel in a separate isolated Python process.

This is not a hand-authored schema imitation. Source identity is checked before
import. No legacy module is imported into the new runtime's process.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
WHEEL=ROOT/'compat/ess_agent_relay-0.1.0-py3-none-any.whl'
# Filled from the provided archive, not from whichever file happens to be installed.
LEGACY_SHA256='8bce0915a5ef3ebc8be0cf7ebf2b7c1483ea1c82e790bafaafcb03315b48a4bf'

BOOTSTRAP=r'''
import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import agent_relay
assert agent_relay.__version__ == '0.1.0'
assert sys.argv[1] in agent_relay.__file__
from agent_relay.controller import Controller
from agent_relay.store import Store
home=Path(sys.argv[2]); mode=sys.argv[3]
if mode == 'inspect':
    s=Store(home)
    print(json.dumps({'version':agent_relay.__version__,'module':agent_relay.__file__,'doctor':s.doctor(True)}))
    raise SystemExit(0)
s=Store.initialize(home); c=Controller(s); serial=0
def cmd(op,**p):
    global serial
    serial+=1
    return c.command(s.key,'original-'+str(serial),op,p)
cmd('workflow.create',id='w',directive='Original owner directive: preserve durable application behavior',constraints=['Never erase the original requirements'])
cmd('requirement.add',id='r',workflow='w',text='Store and read back application data')
cmd('source.put',id='identity',workflow='w',source_kind='Agent.md',text='Original Agent.md identity',expected_rev=0)
cmd('memory.add',id='m',workflow='w',text='Original historical memory '*200,origin='actual-v0.1-runtime')
cmd('grant.create',id='worker',workflow='w')
token=c.issue_token(s.key,'worker')
repo=home.parent/'application';repo.mkdir(exist_ok=True)
cmd('repo.register',id='repo',workflow='w',root=str(repo))
verifiers=[]
if mode=='verified':
    from agent_relay.selftest import APP_SOURCE,ORACLE_SOURCE
    from agent_relay.verification import register_verifier,run_verifier
    from agent_relay.workspace import register_candidate
    (repo/'app.py').write_text(APP_SOURCE)
    oracle=home.parent/'oracle';oracle.mkdir();(oracle/'test_app.py').write_text(ORACLE_SOURCE)
    register_verifier(c,s.key,'pin-oracle',{'id':'v','workflow':'w','oracle_root':str(oracle),'min_tests':3})
    verifiers=['v']
cmd('task.create',id='t',workflow='w',title='Original task',requirements=['r'],resources=['repo/repo'],repos=['repo'],verifiers=verifiers)
attempt=cmd('task.claim',id='t',provider='original-worker')['attempt']
context=cmd('context.hydrate',attempt=attempt['id'])['context']
evidence=None
if mode=='unknown':
    import base64
    cmd('action.prepare',id='action',attempt=attempt['id'],context=context['id'],type='file.write',args={'repo':'repo','path':'state.txt','expected_sha256':'ABSENT','data_b64':base64.b64encode(b'unknown-applied-state').decode()})
    cmd('action.start',id='action')
    # Actual application-side effect occurred, but receipt is missing.
    (repo/'state.txt').write_bytes(b'unknown-applied-state')
if mode=='verified':
    register_candidate(c,s.key,'capture',{'id':'candidate','attempt':attempt['id'],'context':context['id']})
    evidence=run_verifier(c,s.key,'verify',{'candidate':'candidate','verifier':'v'})['evidence']
    assert evidence['status']=='PASS'
print(json.dumps({'version':agent_relay.__version__,'module':agent_relay.__file__,'token':token,'owner_key':s.key,'attempt':attempt,'context':context,'evidence':evidence,'doctor':s.doctor(True)}))
'''

def legacy(home, mode='basic'):
    if hashlib.sha256(WHEEL.read_bytes()).hexdigest()!=LEGACY_SHA256:
        raise AssertionError('Supplied 0.1.0 wheel identity changed before import')
    result=subprocess.run([sys.executable,'-I','-c',BOOTSTRAP,str(WHEEL),str(home),mode],capture_output=True,text=True,timeout=15)
    if result.returncode:
        raise AssertionError(f'Actual legacy runtime failed: {result.stderr}')
    return json.loads(result.stdout)
