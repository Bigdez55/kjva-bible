#!/usr/bin/env python3
"""Bounded actual mTLS worker-process contention; disposable one-host fixture only."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
from verify_package import ROOT

def child(config,index,seconds):
    from agent_relay.network import RemoteClient
    client=RemoteClient(config,timeout=15);serial=0;acks=0;calls=0;latencies=[];errors=[]
    def invoke(op,p):
        nonlocal serial,acks,calls
        serial+=1;start=time.perf_counter();out=client.call(op,p,f'load-{index}-{serial}')
        latencies.append((time.perf_counter()-start)*1000);calls+=1
        if op not in ('status','get','work.ready','version'):acks+=1
        return out
    try:
        a=invoke('task.claim',{'id':f't{index}','provider':'tls-load-worker','ttl':300})['attempt']
        invoke('context.hydrate',{'attempt':a['id']})
        deadline=time.monotonic()+seconds;n=0
        while time.monotonic()<deadline:
            invoke('attempt.heartbeat',{'id':a['id'],'ttl':300})
            if n%10==0:invoke('memory.add',{'id':f'm{index}-{n}','workflow':'load','text':'durable scoped TLS continuity','origin':'disposable-load'})
            if n%20==0:invoke('get',{'kind':'task','id':f't{index}'})
            n+=1;time.sleep(.003)
        invoke('attempt.release',{'id':a['id'],'reason':'bounded load completed'})
    except Exception as exc:errors.append({'type':type(exc).__name__,'message':str(exc)})
    print(json.dumps({'worker':index,'requests':calls,'acknowledged_mutations':acks,'latency_ms':latencies,'errors':errors}));return 1 if errors else 0

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seconds',type=float,default=60);p.add_argument('--workers',type=int,default=8);p.add_argument('--out',type=Path)
    p.add_argument('--child',action='store_true');p.add_argument('--config',type=Path);p.add_argument('--index',type=int)
    a=p.parse_args()
    if a.child:return child(a.config,a.index,a.seconds)
    if not a.out or not 1<=a.seconds<=3600 or not 1<=a.workers<=12:p.error('out required; seconds 1..3600; workers 1..12')
    sys.path.insert(0,str(ROOT/'tests'))
    from integration_support import TLSMaterial,daemon
    from agent_relay.store import Store,private_write
    from agent_relay.controller import Controller
    from agent_relay.certification import runtime_identity
    import agent_relay
    if Path(agent_relay.__file__).is_relative_to(ROOT/'src'):raise RuntimeError('Use installed wheel')
    start=time.perf_counter();runtime=runtime_identity()[0];started=datetime.now(timezone.utc).isoformat();children=[];handles=[]
    with tempfile.TemporaryDirectory(prefix='rly-tls-load-') as tmp:
        b=Path(tmp);home=b/'ctl';s=Store.initialize(home);c=Controller(s);serial=0
        def cmd(op,**payload):
            nonlocal serial
            serial+=1;return c.command(s.key,f'bootstrap-{serial}',op,payload)
        cmd('workflow.create',id='load',directive='Bounded disposable mTLS continuity load')
        cmd('requirement.add',id='r',workflow='load',text='No lost acknowledged mutations')
        cmd('source.put',id='identity',workflow='load',source_kind='Agent.md',text='Agent: maintain every obligation',expected_rev=0)
        tls=TLSMaterial(b/'tls')
        for i in range(a.workers):
            name=f'worker{i}';tls.issue(name,False)
            cmd('grant.create',id=name,workflow='load')
            cmd('peer.register',fingerprint=tls.fingerprint(name),grant=name)
            private_write(b/(name+'.token'),c.issue_token(s.key,name).encode())
            cmd('task.create',id=f't{i}',workflow='load',title=f'Independent TLS worker {i}',requirements=['r'],resources=[f'load/{i}'])
        with daemon(home,tls.server_config()):
            port=json.loads((home/'network.status.json').read_text())['port'];before=s.doctor()['events']
            try:
                for i in range(a.workers):
                    conf=tls.client_config(port,b/f'worker{i}.token',name=f'worker{i}')
                    f=tempfile.TemporaryFile();handles.append(f)
                    proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--child','--config',str(conf),'--index',str(i),'--seconds',str(a.seconds)],stdout=f,stderr=subprocess.PIPE)
                    children.append(proc)
                rows=[]
                deadline=time.monotonic()+a.seconds+40
                for proc,stream in zip(children,handles):
                    _,err=proc.communicate(timeout=max(1,deadline-time.monotonic()));stream.seek(0)
                    row=json.loads(stream.read());row['returncode']=proc.returncode
                    if err:row['stderr']=err.decode()
                    rows.append(row)
                doctor=s.doctor(True);delta=doctor['events']-before
            finally:
                for proc in children:
                    if proc.poll() is None:proc.kill();proc.wait(timeout=5)
                    if proc.stderr:proc.stderr.close()
                for f in handles:f.close()
    values=sorted(x for row in rows for x in row['latency_ms'])
    def percentile(q):return values[min(len(values)-1,int((len(values)-1)*q))] if values else None
    total=sum(r['acknowledged_mutations'] for r in rows)
    ok=runtime==runtime_identity()[0] and total==delta and all(not r['errors'] and r['returncode']==0 for r in rows)
    report={'ok':ok,'runtime_sha256':runtime,'started_at':started,'elapsed_s':time.perf_counter()-start,
      'requested_seconds_per_worker':a.seconds,'workers':a.workers,'transport':'actual TLS 1.3 mutual authentication, certificate per grant',
      'scope':'bounded one-host loopback multi-process load; NOT physical multi-host or endurance certification',
      'requests':sum(r['requests'] for r in rows),'acknowledged_mutations':total,'journal_event_delta':delta,
      'latency_ms':{'p50':percentile(.5),'p95':percentile(.95),'p99':percentile(.99)},'doctor':doctor,
      'workers_result':rows,'peak_child_maxrss_platform_units':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
      'live_workspace_opened':False,'private_tls_material_destroyed':True}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('ok','elapsed_s','workers','requests','acknowledged_mutations','journal_event_delta')},indent=2))
    return 0 if ok else 1
if __name__=='__main__':raise SystemExit(main())
