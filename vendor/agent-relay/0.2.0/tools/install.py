#!/usr/bin/env python3
"""Offline, additive installation. Never opens or migrates a live Relay store."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import venv
from verify_package import verify,ROOT

def run(argv:list[str],env:dict[str,str],timeout:int=120)->subprocess.CompletedProcess:
    p=subprocess.run(argv,env=env,cwd='/',text=True,capture_output=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError(f'Command failed ({p.returncode}): {argv}\n{p.stdout}\n{p.stderr}')
    return p

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix',type=Path,default=Path.home()/'.local/share/agent-relay/0.2.0')
    args=parser.parse_args();prefix=args.prefix.expanduser().absolute()
    if sys.version_info<(3,11):raise RuntimeError('Python 3.11+ required; select the intended interpreter explicitly')
    if os.name!='posix':raise RuntimeError('This release requires POSIX and Unix-domain sockets')
    manifest=verify()
    if prefix.exists() or prefix.is_symlink():raise RuntimeError('Refusing existing prefix: '+str(prefix))
    wheel=ROOT/'dist/agent_relay-0.2.0-py3-none-any.whl'
    if not wheel.is_file():raise RuntimeError('Expected packaged wheel not present')
    old=os.umask(0o077)
    try:venv.EnvBuilder(with_pip=True,clear=False,symlinks=False).create(prefix)
    finally:os.umask(old)
    os.chmod(prefix,0o700)
    env={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','PYTHONHOME','RELAY_TOKEN','PIP_INDEX_URL','PIP_EXTRA_INDEX_URL'}}
    env['PYTHONNOUSERSITE']='1';env['PIP_DISABLE_PIP_VERSION_CHECK']='1';env['PIP_CONFIG_FILE']=os.devnull
    python=str(prefix/'bin/python');cli=str(prefix/'bin/relayctl')
    installation=run([python,'-I','-m','pip','install','--no-index','--no-deps','--disable-pip-version-check',str(wheel)],env)
    identity=json.loads(run([python,'-I','-c','import json,sys,sqlite3,agent_relay; print(json.dumps({"prefix":sys.prefix,"module":agent_relay.__file__,"version":agent_relay.__version__,"python":sys.version,"sqlite":sqlite3.sqlite_version}))'],env).stdout)
    if not Path(identity['module']).is_relative_to(prefix):raise RuntimeError('Target import did not resolve to new installation')
    selftest=prefix/'installed-selftest.json'
    result=run([cli,'selftest','--output',str(selftest)],env,120)
    observed=json.loads(selftest.read_text())
    if observed.get('ok') is not True:raise RuntimeError('Installed recovery test did not pass')
    report={'ok':True,'installed_at':datetime.now(timezone.utc).isoformat(),'prefix':str(prefix),
            'package_verification':manifest,'wheel_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),
            'identity':identity,'selftest':observed,'pip_output':installation.stdout,
            'live_store_opened':False,'legacy_migration_performed':False,'service_installed_or_started':False}
    output=prefix/'installation.json';output.write_text(json.dumps(report,indent=2)+'\n');os.chmod(output,0o600)
    print(json.dumps({'ok':True,'installed_prefix':str(prefix),'cli':cli,'version':identity['version'],
                      'selftest_checks':len(observed['checks']),'report':str(output),
                      'next':'Read INSTALL_FOR_CODING_AGENT.md before initializing an explicitly selected NEW control home.'},indent=2))
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,RuntimeError,ValueError,subprocess.TimeoutExpired) as e:
        print('INSTALLATION STOPPED: '+str(e)+'\nExisting state was not modified. Inspect any newly created prefix before retrying.',file=sys.stderr);sys.exit(2)
