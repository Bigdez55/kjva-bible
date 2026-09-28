#!/usr/bin/env python3
"""Release step before tests; pins executable inputs, not their future results."""
import argparse
import hashlib
import json
from verify_candidate import ROOT,inputs

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seal',action='store_true',required=True);p.parse_args()
    entries=[]
    for path in inputs(ROOT):
        if path.is_symlink():raise ValueError('No symlink candidate input')
        entries.append({'path':path.relative_to(ROOT).as_posix(),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (ROOT/'CANDIDATE_MANIFEST.json').write_text(json.dumps({'format':1,'files':entries},indent=2)+'\n')
    print(json.dumps({'candidate_inputs':len(entries)},indent=2))
if __name__=='__main__':main()
