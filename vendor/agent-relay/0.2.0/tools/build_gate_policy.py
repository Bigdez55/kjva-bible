#!/usr/bin/env python3
"""Release-maintainer step only: materialize the reviewed, exact local test policy.

This writes a candidate artifact. It does NOT approve exceptions, mark gates
certified, or run tests. A runtime accepts only its installed copy of this policy.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
from run_checks import tree_hash,GAPS
ROOT=Path(__file__).resolve().parents[1]

# Remaining boundaries requiring a separate scoped reviewer decision. Other gates
# describe the implemented API behavior within ONE trusted authority. None is an
# unqualified claim about every app/provider/OS/deployment.
REVIEW={
 'G01':GAPS['G01'],
 'G02':'0.1.0 compatibility and migration are executed against the archived wheel. The earlier standalone audited recorder and its original 48-test suite are unavailable; equivalence to that older lineage is not certified.',
 'G10':GAPS['G10'],
 'G13':GAPS['G13'],
 'G15':GAPS['G15'],
 'G16':GAPS['G16'],
 'G17':GAPS['G17'],
 'G19':GAPS['G19'],
 'G22':GAPS['G22'],
 'G23':GAPS['G23'],
 'G27':GAPS['G27'],
 'G28':GAPS['G28'],
 'G29':GAPS['G29'],
 'G32':GAPS['G32'],
 'G33':GAPS['G33'],
 'G37':GAPS['G37'],
 'G39':GAPS['G39'],
 'G40':GAPS['G40'],
 'G41':GAPS['G41'],
 'G42':GAPS['G42'],
 'G44':GAPS['G44'],
 'G45':GAPS['G45'],
}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--write-candidate',action='store_true',required=True);p.parse_args()
    raw=(ROOT/'contracts/ORIGINAL_G01_G46.json').read_bytes();original=json.loads(raw)
    by_gate={g['id']:[] for g in original['gates']}
    for file in sorted((ROOT/'tests').glob('test_*.py')):
        tree=ast.parse(file.read_text())
        for cls in tree.body:
            if not isinstance(cls,ast.ClassDef):continue
            for fn in cls.body:
                if not isinstance(fn,ast.FunctionDef):continue
                for decorator in fn.decorator_list:
                    if isinstance(decorator,ast.Call) and isinstance(decorator.func,ast.Name) and decorator.func.id=='gates':
                        for arg in decorator.args:
                            gate=ast.literal_eval(arg)
                            by_gate[gate].append(f'{file.stem}.{cls.name}.{fn.name}')
    if any(not tests for tests in by_gate.values()):raise SystemExit('Every original gate needs actual named tests')
    policy={'version':1,'profile':'ONE_AUTHORITY_TRUSTED_WORKERS_MCP_STDIO_AND_OPTIONAL_MTLS_SCHEMA2',
        'scope':'Local installed-runtime conformance; only mcp-stdio-v1 is enabled by registration. Native provider tools and hidden compaction are never claimed. Network faults use real loopback TLS; physical two-host certification requires review.',
        'original_contract_sha256':hashlib.sha256(raw).hexdigest(),
        'tests_sha256':tree_hash(ROOT/'tests')[0],
        'runner_sha256':hashlib.sha256((ROOT/'tools/run_checks.py').read_bytes()).hexdigest(),
        'gates':[{'id':g['id'],'title':g['title'],'required_behavior':g['required_behavior'],
                 'required_tests':sorted(by_gate[g['id']]),'remaining_boundary':REVIEW.get(g['id'],''),
                 'scope_note':GAPS[g['id']]} for g in original['gates']]}
    encoded=json.dumps(policy,indent=2,sort_keys=True)+'\n'
    (ROOT/'contracts/LOCAL_GATE_POLICY.json').write_text(encoded)
    (ROOT/'src/agent_relay/data/gate_policy.json').write_text(encoded)
    print(json.dumps({'policy_sha256':hashlib.sha256(encoded.encode()).hexdigest(),'gates':len(by_gate),
          'remaining_boundaries_requiring_review':len(REVIEW),'approved_exceptions':0},indent=2))
if __name__=='__main__':main()
