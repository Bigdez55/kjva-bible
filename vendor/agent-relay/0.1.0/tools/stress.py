#!/usr/bin/env python3
"""Bounded contention run of the actual local socket service; never touches user state."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import sqlite3
import subprocess
import sys
import tempfile
import time


def child(home:Path,tokenfile:Path,index:int,deadline:float):
    from agent_relay.service import call
    token=tokenfile.read_text().strip();samples=[];writes=0;errors=[];serial=0
    def op(name,p,write=True):
        nonlocal writes,serial
        serial+=1;start=time.perf_counter()
        result=call(home,token,name,p,f'worker-{index}-{serial}',timeout=30)
        samples.append((name,(time.perf_counter()-start)*1000))
        if write:writes+=1
        return result
    try:
        attempt=op('task.claim',{'id':f't{index}','provider':'bounded-stress-client','ttl':300})['attempt']
        op('context.hydrate',{'attempt':attempt['id']})
        n=0
        while time.monotonic()<deadline:
            op('attempt.heartbeat',{'id':attempt['id'],'ttl':300})
            if n%10==0:op('memory.add',{'id':f'm{index}-{n}','workflow':'stress','text':'retained evidence '+str(n),'origin':'bounded-contention-fixture'})
            if n%25==0:op('context.hydrate',{'attempt':attempt['id']})
            if n%5==0:op('get',{'kind':'task','id':f't{index}'},False)
            n+=1;time.sleep(0.002)
        op('attempt.release',{'id':attempt['id'],'reason':'bounded contention interval ended'})
    except Exception as e:errors.append({'type':type(e).__name__,'message':str(e)})
    print(json.dumps({'worker':index,'samples':samples,'write_acknowledgments':writes,'errors':errors}))
    return 1 if errors else 0


def percentile(values,q):
    v=sorted(values)
    if not v:return None
    k=(len(v)-1)*q;i=int(k);return v[i]+(v[min(i+1,len(v)-1)]-v[i])*(k-i)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds',type=float,default=60)
    p.add_argument('--workers',type=int,default=8)
    p.add_argument('--out',type=Path)
    p.add_argument('--child',action='store_true');p.add_argument('--home',type=Path);p.add_argument('--token-file',type=Path);p.add_argument('--index',type=int);p.add_argument('--deadline',type=float)
    a=p.parse_args()
    if a.child:return child(a.home,a.token_file,a.index,a.deadline)
    if not 1<=a.workers<=12 or not 1<=a.seconds<=86400:p.error('workers 1..12, seconds 1..86400')
    if not a.out:p.error('--out required')
    from agent_relay.selftest import start_service
    from agent_relay.service import call
    from agent_relay.store import Store,private_write
    import agent_relay
    a.out.mkdir(parents=True,exist_ok=True)
    children=[];handles=[];server=None;result=None
    started=datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix='rly-load-') as tmp:
        base=Path(tmp);home=base/'ctl';s=Store.initialize(home)
        def op(name,p):return call(home,s.key,name,p)
        with (base/'daemon.stderr').open('wb') as daemon_log:
            try:
                server=start_service(home,daemon_log)
                op('workflow.create',{'id':'stress','directive':'Exercise independent bounded local workflow transitions without lost commits'})
                op('requirement.add',{'id':'r','workflow':'stress','text':'Concurrent clients preserve durable transitions'})
                op('source.put',{'id':'identity','workflow':'stress','source_kind':'Agent.md','text':'Agent: preserve source authority','expected_rev':0})
                for i in range(a.workers):
                    op('task.create',{'id':f't{i}','workflow':'stress','title':f'Independent worker {i}','requirements':['r'],'resources':[f'stress/{i}']})
                    op('grant.create',{'id':f'w{i}','workflow':'stress'})
                    tok=op('grant.token',{'id':f'w{i}'})['token']
                    private_write(base/f'w{i}.token',tok.encode())
                before=op('doctor',{'scrub':True});start=time.monotonic();deadline=start+a.seconds
                for i in range(a.workers):
                    output=(base/f'worker{i}.json').open('wb');err=(base/f'worker{i}.stderr').open('wb');handles.extend([output,err])
                    children.append(subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--child','--home',str(home),
                        '--token-file',str(base/f'w{i}.token'),'--index',str(i),'--deadline',str(deadline)],stdout=output,stderr=err))
                rss=[]
                while any(c.poll() is None for c in children):
                    if time.monotonic()>deadline+60:raise RuntimeError('Workload exceeded bounded termination allowance')
                    status=Path(f'/proc/{server.pid}/status')
                    if status.is_file():
                        for line in status.read_text().splitlines():
                            if line.startswith('VmRSS:'):rss.append(int(line.split()[1])*1024)
                    time.sleep(0.2)
                elapsed=time.monotonic()-start
                for handle in handles:handle.close()
                handles=[]
                reports=[]
                for i,c in enumerate(children):
                    raw=(base/f'worker{i}.json').read_text()
                    if not raw:raise RuntimeError((base/f'worker{i}.stderr').read_text())
                    item=json.loads(raw);item['exit_code']=c.returncode;reports.append(item)
                after=op('doctor',{'scrub':True})
                server.terminate();server.wait(timeout=30);server=None
                samples=[(r['worker'],op,ms) for r in reports for op,ms in r['samples']]
                write_acks=sum(r['write_acknowledgments'] for r in reports)
                events_delta=after['events']-before['events']
                failures=[e for r in reports for e in r['errors']]
                journal_files={x.name:x.stat().st_size for x in home.iterdir() if x.is_file() and ('.sqlite3' in x.name)}
                result={'ok':not failures and all(r['exit_code']==0 for r in reports) and events_delta==write_acks and after['full_scrub']=='PASS',
                        'started_at':started,'requested_workload_s':a.seconds,'observed_workload_s':elapsed,
                        'workers':a.workers,'client_processes':a.workers,'service_processes':1,'completed_requests':len(samples),
                        'acknowledged_writes':write_acks,'event_count_delta':events_delta,'write_event_accounting_matches':events_delta==write_acks,
                        'latency_ms':{op:{'count':len(v:=[x[2] for x in samples if x[1]==op]),'p50':percentile(v,.50),'p95':percentile(v,.95),'p99':percentile(v,.99),'max':max(v)} for op in sorted({x[1] for x in samples})},
                        'sampled_service_RSS_max_bytes':max(rss) if rss else None,'RSS_method':'/proc sample at 0.2 second intervals when available; not exact peak',
                        'environment':{'python':sys.version,'sqlite':sqlite3.sqlite_version,'platform':platform.platform(),'module':agent_relay.__file__},
                        'before':before,'after':after,'database_file_bytes':journal_files,'errors':failures,
                        'worker_counts':[{'worker':r['worker'],'requests':len(r['samples']),'writes':r['write_acknowledgments'],'exit_code':r['exit_code']} for r in reports],
                        'timing_excludes':'initialization, grant/task setup and before/after full scrubs',
                        'live_workspace_opened':False,'not_exercised':['physical power loss','multi-host','real model/provider','one-hour or 24-hour soak','production deployment']}
                with (a.out/'stress_samples.csv').open('w',newline='') as f:
                    w=csv.writer(f);w.writerow(['worker','operation','elapsed_ms']);w.writerows(samples)
                (a.out/'stress.json').write_text(json.dumps(result,indent=2)+'\n')
                (a.out/'stress-daemon.stderr').write_bytes((base/'daemon.stderr').read_bytes())
            finally:
                for c in children:
                    if c.poll() is None:c.terminate()
                for c in children:
                    try:c.wait(timeout=5)
                    except subprocess.TimeoutExpired:c.kill();c.wait()
                for handle in handles:handle.close()
                if server and server.poll() is None:server.terminate();server.wait(timeout=30)
    print(json.dumps({k:result[k] for k in ('ok','observed_workload_s','completed_requests','acknowledged_writes','event_count_delta','workers')},indent=2))
    return 0 if result['ok'] else 1

if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,RuntimeError,ValueError) as e:print(str(e),file=sys.stderr);sys.exit(2)
