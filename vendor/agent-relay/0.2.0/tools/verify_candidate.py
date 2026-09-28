#!/usr/bin/env python3
"""Verify immutable executable/test/contract inputs independently of generated reports."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DIRECTORIES=('src','tests','tools','dist','compat','contracts')
EXTRA=('pyproject.toml','Agent.md','AGENTS.md')

def inputs(root):
    paths=[]
    for directory in DIRECTORIES:
        for path in (root/directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and not any(p.endswith('.egg-info') for p in path.parts) and path.suffix not in ('.pyc','.pyo'):
                paths.append(path)
    paths.extend(root/name for name in EXTRA if (root/name).is_file())
    return sorted(paths)

def verify_candidate(root=None):
    root=Path(root or ROOT).resolve();manifest_path=root/'CANDIDATE_MANIFEST.json'
    manifest=json.loads(manifest_path.read_text())
    actual={p.relative_to(root).as_posix():p for p in inputs(root)}
    declared=manifest['files'];names=[x['path'] for x in declared]
    if len(set(names))!=len(names) or set(names)!=set(actual):raise ValueError('Candidate inputs missing, unexpected or duplicated')
    for entry in declared:
        path=actual[entry['path']]
        if path.is_symlink() or path.stat().st_size!=entry['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError('Candidate mismatch before import: '+entry['path'])
    return {'verified':True,'manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),'input_count':len(actual),
            'scope':'exact source, tests, tools, wheel, compatibility archive, contracts and agent instructions; excludes generated evidence to avoid a hash cycle'}

if __name__=='__main__':print(json.dumps(verify_candidate(),indent=2))
