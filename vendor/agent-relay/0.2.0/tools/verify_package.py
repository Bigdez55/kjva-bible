#!/usr/bin/env python3
"""Read-only stdlib package integrity check; imports no target code."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path,PurePosixPath
import sys

ROOT=Path(__file__).resolve().parents[1]

def verify(root:Path=ROOT)->dict:
    manifest=root/'MANIFEST.sha256.json'
    if not manifest.is_file():
        raise ValueError('Missing MANIFEST.sha256.json; do not install an incomplete delivery')
    data=json.loads(manifest.read_text())
    entries=data.get('files')
    if not isinstance(entries,list) or not entries:raise ValueError('Invalid package manifest')
    seen=set()
    for entry in entries:
        name=entry['path'];parts=PurePosixPath(name)
        if parts.is_absolute() or any(x in ('..','.') for x in parts.parts) or '\\' in name or name in seen:
            raise ValueError('Unsafe/duplicate manifest path: '+name)
        seen.add(name);path=root.joinpath(*parts.parts)
        if any(x.is_symlink() for x in [path,*list(path.parents)[:len(parts.parts)-1]]):
            raise ValueError('Symlink artifact not permitted: '+name)
        if not path.is_file():raise ValueError('Missing artifact: '+name)
        h=hashlib.sha256();size=0
        with path.open('rb') as f:
            while chunk:=f.read(1024*1024):h.update(chunk);size+=len(chunk)
        if h.hexdigest()!=entry['sha256'] or size!=entry['bytes']:
            raise ValueError('Artifact changed: '+name)
    # Ignore only conventional runtime caches/build metadata, never extra executable source.
    ignored={'__pycache__','build','.git','.venv'}
    extras=[]
    for path in root.rglob('*'):
        if not path.is_file():continue
        rel=path.relative_to(root)
        if any(x in ignored or x.endswith('.egg-info') for x in rel.parts):continue
        if rel.as_posix() not in seen and rel.as_posix()!='MANIFEST.sha256.json':extras.append(rel.as_posix())
    if extras:raise ValueError('Unmanifested files: '+', '.join(sorted(extras)))
    return {'ok':True,'files_verified':len(seen),'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),
            'assurance':'hash consistency, not publisher signature/authenticity'}

if __name__=='__main__':
    try:print(json.dumps(verify(),indent=2))
    except (OSError,ValueError,KeyError,TypeError) as e:print('PACKAGE VERIFICATION FAILED: '+str(e),file=sys.stderr);sys.exit(2)
