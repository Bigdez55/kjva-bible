"""Installation-safe operator and worker CLI. No legacy store autodiscovery."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
from . import __version__
from .codec import canonical,strict_loads
from .controller import Controller
from .errors import RelayError,require
from .service import call,serve
from .store import Store,private_write

DEFAULT_HOME=Path.home()/".local/share/ess-agent-relay/control"


def parser():
    p=argparse.ArgumentParser(prog="relayctl",description="ESS Agent Relay: explicit local authority; no implicit legacy migration")
    p.add_argument("--home",type=Path,default=DEFAULT_HOME)
    p.add_argument("--token-file",type=Path,help="worker token; never pass tokens on the command line")
    p.add_argument("--version",action="version",version=__version__)
    sub=p.add_subparsers(dest="command",required=True)
    init=sub.add_parser("init");init.add_argument("--journal",choices=["auto","wal","delete"],default="auto")
    init.add_argument("--blob-quota-mib",type=int,default=1024)
    server=sub.add_parser("serve");server.add_argument("--auto-dispatch",action="store_true",help="explicitly enable serial dispatch of preauthorized file/tool actions")
    doc=sub.add_parser("doctor");doc.add_argument("--scrub",action="store_true")
    c=sub.add_parser("call");c.add_argument("op");c.add_argument("--data",default="{}",help="JSON, @file.json, or - for stdin")
    c.add_argument("--command-id",help="reuse this ID for retries of the same command only")
    s=sub.add_parser("status");s.add_argument("--workflow")
    g=sub.add_parser("get");g.add_argument("kind");g.add_argument("id")
    tok=sub.add_parser("token");tok.add_argument("grant");tok.add_argument("--out",type=Path,required=True)
    for action in ("dispatch","reconcile"):
        a=sub.add_parser(action);a.add_argument("id");a.add_argument("--command-id")
    verify=sub.add_parser("verify");verify.add_argument("candidate");verify.add_argument("verifier");verify.add_argument("--command-id")
    back=sub.add_parser("backup");back.add_argument("destination",type=Path)
    restore=sub.add_parser("restore");restore.add_argument("backup",type=Path)
    sub.add_parser("rebuild")
    test=sub.add_parser("selftest");test.add_argument("--output",type=Path)
    return p


def credential(args):
    if args.token_file:
        require(args.token_file.is_file(),"TOKEN_FILE","missing token file")
        require(not args.token_file.stat().st_mode&0o077,"TOKEN_FILE","token file must have mode 0600")
        return args.token_file.read_text().strip()
    if os.environ.get("RELAY_TOKEN"):
        return os.environ["RELAY_TOKEN"]
    return Store(args.home).key


def main(argv=None):
    args=parser().parse_args(argv)
    args.home=args.home.expanduser().absolute()
    try:
        if args.command=="init":
            store=Store.initialize(args.home,args.journal,args.blob_quota_mib*1024*1024)
            result={"initialized":str(store.home),"profile":store.config["profile"],"journal":store.config["journal"],
                    "owner_key_file":str(store.home/"owner.key"),"legacy_state_modified":False}
        elif args.command=="serve":
            require(args.token_file is None,"FORBIDDEN","worker credentials cannot launch an authority")
            serve(Controller(Store(args.home)),args.auto_dispatch);return 0
        elif args.command=="restore":
            store=Store.restore(args.backup,args.home)
            result={"restored":str(store.home),"mode":"RECOVERY_ONLY","old_credentials_valid":False}
        elif args.command=="selftest":
            from .selftest import run_selftest
            result=run_selftest()
            if args.output:
                args.output.parent.mkdir(parents=True,exist_ok=True)
                private_write(args.output,canonical(result))
            if not result["ok"]:
                print(json.dumps(result,indent=2));return 1
        elif args.command in {"backup","rebuild"}:
            require(args.token_file is None,"FORBIDDEN","operator-only maintenance")
            store=Store(args.home)
            with store.service_lock():
                result=store.backup(args.destination) if args.command=="backup" else store.rebuild()
        elif args.command=="doctor" and not (args.home/"relay.sock").exists():
            require(args.token_file is None,"FORBIDDEN","offline doctor is operator-only")
            store=Store(args.home)
            with store.service_lock():result=store.doctor(args.scrub)
        else:
            token=credential(args)
            cid=getattr(args,"command_id",None)
            if args.command=="call":
                raw=sys.stdin.read(4*1024*1024+1) if args.data=="-" else Path(args.data[1:]).read_text() if args.data.startswith("@") else args.data
                require(len(raw.encode())<=4*1024*1024,"REQUEST_SIZE","request too large")
                result=call(args.home,token,args.op,strict_loads(raw),cid)
            elif args.command=="status":result=call(args.home,token,"status",{"workflow":args.workflow} if args.workflow else {})
            elif args.command=="get":result=call(args.home,token,"get",{"kind":args.kind,"id":args.id})
            elif args.command=="doctor":result=call(args.home,token,"doctor",{"scrub":args.scrub})
            elif args.command=="token":
                result=call(args.home,token,"grant.token",{"id":args.grant})
                args.out.parent.mkdir(parents=True,exist_ok=True)
                private_write(args.out,(result["token"]+"\n").encode())
                result={"token_file":str(args.out),"mode":"0600","token_printed":False}
            elif args.command in {"dispatch","reconcile"}:
                result=call(args.home,token,"action."+args.command,{"id":args.id},cid)
            elif args.command=="verify":result=call(args.home,token,"verify.run",{"candidate":args.candidate,"verifier":args.verifier},cid)
            else:raise RelayError("COMMAND","unsupported command")
        print(json.dumps({"ok":True,"result":result},indent=2,ensure_ascii=False))
        return 0
    except (RelayError,OSError) as e:
        print(json.dumps({"ok":False,"error":{"code":getattr(e,"code","OS_ERROR"),"message":str(e)}}),file=sys.stderr)
        return 2


def doctor_main():
    args=sys.argv[1:]
    scrub="--scrub" in args
    args=[x for x in args if x!="--scrub"]
    return main([*args,"doctor",*(["--scrub"] if scrub else [])])


if __name__=="__main__":
    raise SystemExit(main())
