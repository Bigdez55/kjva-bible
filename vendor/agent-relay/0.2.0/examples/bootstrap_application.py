#!/usr/bin/env python3
"""Create and verify a real demo application through an already-running local Relay."""
import argparse
from pathlib import Path
import json
from agent_relay.service import call
from agent_relay.store import Store,private_write
from agent_relay.selftest import APP_SOURCE,ORACLE_SOURCE


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home',type=Path,required=True)
    p.add_argument('--base',type=Path,required=True,help='NEW disposable demo source/oracle directory')
    p.add_argument('--prefix',default='demo',help='unique identifier prefix for repeat demonstrations')
    a=p.parse_args();a.base=a.base.absolute()
    if a.base.exists():p.error('--base must be NEW; no existing application will be overwritten')
    a.base.mkdir(mode=0o700);repo=a.base/'app';oracle=a.base/'oracle';repo.mkdir();oracle.mkdir()
    (repo/'app.py').write_text(APP_SOURCE);(oracle/'test_app.py').write_text(ORACLE_SOURCE)
    token=Store(a.home).key
    def id(name):return a.prefix+'-'+name
    def op(name,data,tok=None):return call(a.home,tok or token,name,data)
    w=id('workflow');r=id('requirement');task=id('task');rid=id('repo');v=id('oracle')
    op('workflow.create',{'id':w,'directive':'Demonstrate real durable application persistence and evidence-bound acceptance'})
    op('requirement.add',{'id':r,'workflow':w,'text':'Updates persist and another process reads committed values'})
    op('source.put',{'id':id('identity'),'workflow':w,'source_kind':'Agent.md','text':'Agent: retain authorized obligations','expected_rev':0})
    op('repo.register',{'id':rid,'workflow':w,'root':str(repo)})
    op('verifier.register',{'id':v,'workflow':w,'oracle_root':str(oracle),'min_tests':3})
    op('task.create',{'id':task,'workflow':w,'title':'Deliver persistence','requirements':[r],'resources':['repo/'+rid],'repos':[rid],'verifiers':[v]})
    op('grant.create',{'id':id('worker'),'workflow':w})
    worker=op('grant.token',{'id':id('worker')})['token'];private_write(a.base/'worker.token',worker.encode())
    attempt=op('task.claim',{'id':task,'provider':'manual-demo-client','ttl':300},worker)['attempt']
    context=op('context.hydrate',{'attempt':attempt['id']},worker)['context']
    candidate=op('candidate.capture',{'id':id('candidate'),'attempt':attempt['id'],'context':context['id']},worker)['candidate']
    result=op('verify.run',{'candidate':candidate['id'],'verifier':v})
    accepted=op('task.accept',{'id':task,'candidate':candidate['id'],'evidence':[result['evidence']['id']]})
    final=op('workflow.accept',{'id':w})
    print(json.dumps({'task':accepted,'workflow':final,'evidence':result['evidence'],'demo_directory':str(a.base)},indent=2))

if __name__=='__main__':main()
