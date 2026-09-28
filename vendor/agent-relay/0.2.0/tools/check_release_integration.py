#!/usr/bin/env python3
"""Actual installed CLI + real prior wheel + reviewed-fixture migration integration.

All state and review keys are disposable. Signed fixture decisions are destroyed,
not copied into the release or represented as the owner's deployment approval.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
from verify_package import ROOT,verify

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,required=True);p.add_argument('--policy',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--development-unsealed',action='store_true');a=p.parse_args()
    if not a.development_unsealed:verify()
    import agent_relay
    from agent_relay.certification import runtime_identity
    from agent_relay.store import private_write,Store
    from agent_relay.service import call
    from agent_relay.codec import canonical
    sys.path.insert(0,str(ROOT/'tests'))
    from legacy_support import legacy
    from integration_support import daemon
    if Path(agent_relay.__file__).is_relative_to(ROOT/'src'):raise RuntimeError('An installed runtime is required')
    evidence=a.evidence.resolve();policy=a.policy.resolve();checks=[]
    def cli(*argv,expected=0):
        proc=subprocess.run([sys.executable,'-I','-m','agent_relay.cli',*map(str,argv)],capture_output=True,text=True,timeout=15)
        if proc.returncode!=expected:raise RuntimeError(f'Unexpected CLI exit {proc.returncode}: {proc.stderr}')
        return json.loads(proc.stdout if proc.stdout.strip() else proc.stderr)
    start=datetime.now(timezone.utc).isoformat();identity=runtime_identity()[0]
    with tempfile.TemporaryDirectory(prefix='rly-release-') as tmp:
        base=Path(tmp);old=base/'old';new=base/'new'
        original=legacy(old,'unknown')
        planned=cli('migrate','plan','--source',old,'--destination',new)['result']
        cli('migrate','prepare','--source',old,'--destination',new)
        checks.append({'check':'actual_0_1_cli_staged_migration','status':'PASS','original_event_count':original['doctor']['events'],
                       'exact_original_event_bytes_sha256':planned['source_fingerprint']['exact_event_bytes_sha256']})
        evaluation=base/'evaluation.json'
        held=cli('certify','--evidence',evidence,'--policy',policy,'--output',evaluation,expected=3)['result']
        if held['ready'] or not any(g['status']=='NEEDS_REVIEW' for g in held['gates']):raise RuntimeError('Unreviewed boundaries unexpectedly accepted')
        checks.append({'check':'real_current_candidate_held_without_reviews','status':'PASS'})
        private_write(base/'key',secrets.token_bytes(64))
        unsigned=base/'unsigned.json'
        cli('review-template','--evaluation',evaluation,'--reviewer','AUTOMATED_DISPOSABLE_INTEGRATION_FIXTURE','--out',unsigned)
        data=json.loads(unsigned.read_text())
        for decision in data['decisions']:
            decision['reason']='Accepted only inside this disposable automated integration test. No user deployment or production authorization is granted; all stores and review keys are destroyed.'
        unsigned.write_bytes(canonical(data))
        signed=base/'signed.json'
        cli('review-sign','--input',unsigned,'--review-key',base/'key','--out',signed,'--confirm-reviewed')
        cert_args=['--evidence',evidence,'--policy',policy,'--decisions',signed,'--review-key',base/'key']
        evaluated=cli('certify',*cert_args)['result']
        if not evaluated['ready'] or evaluated['full_original_certification']:raise RuntimeError('Incorrect reviewed status')
        checks.append({'check':'actual_cli_reviews_bind_current_evidence_and_remain_exceptions','status':'PASS','fixture_exception_count':evaluated['reviewed_exception_count'],'owner_deployment_approvals':0})
        activate_args=['migrate','activate','--source',old,'--destination',new,*cert_args,'--reconciliation-report','Disposable integration: inspect actual migrated application write']
        blocked=cli(*activate_args,expected=2)
        if blocked['error']['code']!='RESTORE_HELD':raise RuntimeError('Unresolved original effect did not hold activation')
        checks.append({'check':'reviewed_candidate_cannot_override_unknown_effect_hold','status':'PASS'})
        with daemon(new):
            observed=cli('--home',new,'reconcile','action')['result']
            if observed['action']['outcome']!='APPLIED':raise RuntimeError('Independent readback did not reconcile')
        checks.append({'check':'actual_migrated_effect_independent_readback','status':'PASS'})
        cli(*activate_args)
        s=Store(new)
        if s.doctor(True)['mode']!='ACTIVE' or legacy(old,'inspect')['doctor']['mode']!='MIGRATION_HOLD':raise RuntimeError('Wrong authority state after activation')
        checks.append({'check':'one_active_authority_after_evaluated_cli_activation','status':'PASS'})
        refusal=cli('migrate','rollback','--source',old,'--destination',new,expected=2)
        if refusal['error']['code']!='ROLLBACK_UNSAFE':raise RuntimeError('Postactivation rollback was permitted')
        checks.append({'check':'postactivation_rollback_rejected','status':'PASS'})
        last=s.doctor(True)
    if runtime_identity()[0]!=identity:raise RuntimeError('Runtime changed during integration')
    a.out.parent.mkdir(parents=True,exist_ok=True)
    report={'ok':True,'started_at':start,'runtime_sha256':identity,'installed_module':agent_relay.__file__,'checks':checks,
            'final_disposable_store_integrity':last,'review_keys_destroyed':True,'signed_fixture_decisions_shipped':False,
            'owner_deployment_approvals':0,'scope':'Installed CLI integration; real current test report and prior runtime; disposable reviewer fixture only'}
    a.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'ok':True,'checks':len(checks),'owner_deployment_approvals':0,'report':str(a.out)},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
