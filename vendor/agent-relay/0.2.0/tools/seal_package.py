#!/usr/bin/env python3
"""Developer release step: seal a fully built/tested package; no runtime imports."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seal',action='store_true',required=True);p.parse_args()
    entries=[]
    for x in sorted(ROOT.rglob('*')):
        if not x.is_file():continue
        rel=x.relative_to(ROOT)
        if any(v in {'__pycache__','build','.git','.venv'} or v.endswith('.egg-info') for v in rel.parts):continue
        if rel.as_posix()=='MANIFEST.sha256.json':continue
        if x.is_symlink():raise ValueError('Symlink release artifact: '+str(rel))
        entries.append({'path':rel.as_posix(),'bytes':x.stat().st_size,'sha256':hashlib.sha256(x.read_bytes()).hexdigest()})
    manifest={'format':1,'release':'agent-relay 0.2.0','created_at':datetime.now(timezone.utc).isoformat(),
              'assurance':'unsigned integrity manifest; not publisher attestation','file_count':len(entries),'files':entries}
    (ROOT/'MANIFEST.sha256.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'sealed':True,'files':len(entries)},indent=2))

if __name__=='__main__':main()
