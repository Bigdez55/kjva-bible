#!/usr/bin/env python3
"""Cooperating worker: claim eligible work and retrieve the actual context body."""
import argparse
import json
from pathlib import Path
from agent_relay.service import call


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home',type=Path,required=True)
    p.add_argument('--token-file',type=Path,required=True)
    p.add_argument('--workflow',required=True)
    p.add_argument('--provider-label',default='manual-client')
    a=p.parse_args()
    if a.token_file.is_symlink() or a.token_file.stat().st_mode&0o077:p.error('Use a private regular worker token file, mode 0600')
    token=a.token_file.read_text().strip()
    claim=call(a.home,token,'work.next',{'workflow':a.workflow,'provider':a.provider_label,'ttl':300})
    context=call(a.home,token,'context.hydrate',{'attempt':claim['attempt']['id']})
    print(json.dumps({'attempt':claim['attempt'],'context':context},indent=2))
    # The calling integration must deliver this body to its model, renew the lease before expiry,
    # preserve returned IDs, and explicitly prepare approved effects. There is no hidden model loop.

if __name__=='__main__':main()
