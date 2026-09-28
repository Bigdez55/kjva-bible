"""Immutable candidate capture and safe managed file effects.

Registered roots are operator-approved. Symlink traversal and portable aliases
are rejected. Cooperating workers must honor managed resource scopes; this is
not a filesystem snapshot or a sandbox against the same privileged OS user.
"""
from __future__ import annotations
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
from .codec import canonical,digest,object_digest,relpath,ident,text,string_list
from .errors import RelayError,require
from .store import Transaction

SKIP_DIRS={".git",".venv","venv","__pycache__",".pytest_cache",".mypy_cache",".ruff_cache","node_modules"}
MAX_FILES=5000
MAX_TREE=64*1024*1024


def _signature(s):
    return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,stat.S_IMODE(s.st_mode))


def git_identity(root: Path) -> dict | None:
    if not (root/".git").exists():
        return None
    env={"PATH":"/usr/bin:/bin", "GIT_OPTIONAL_LOCKS":"0","GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null"}
    def run(args):
        from .execution import run_process
        p=run_process(["/usr/bin/git","--no-optional-locks","-c","core.fsmonitor=false","-c","core.hooksPath=/dev/null","-C",str(root),*args],root,timeout=15,environment=env)
        require(not p["output_limited"] and not p["timed_out"], "GIT_CAPTURE_LIMIT", "Git metadata capture exceeded its bounded budget")
        return p["stdout"].strip() if p["returncode"]==0 else None
    return {"head":run(["rev-parse","--verify","HEAD"]),"tree":run(["rev-parse","HEAD^{tree}"]),
            "status":run(["status","--porcelain=v1","--untracked-files=all"]),
            "submodule_index":run(["ls-files","--stage"])}


def scan_tree(root: Path, exclude: list[str]) -> tuple[dict,dict[str,bytes]]:
    root=root.resolve(strict=True)
    entries={}; raws={}; total=0; portable=set()
    git_before=git_identity(root)
    for directory,dirs,names in os.walk(root,followlinks=False):
        here=Path(directory)
        allowed=[]
        for name in sorted(dirs):
            path=here/name; relative=path.relative_to(root).as_posix()
            if name in SKIP_DIRS or any(relative==x or relative.startswith(x+"/") for x in exclude):
                continue
            require(not path.is_symlink(),"SYMLINK",relative)
            relpath(relative)
            allowed.append(name)
        dirs[:]=allowed
        for name in sorted(names):
            path=here/name; relative=path.relative_to(root).as_posix()
            if name==".git" or name.startswith(".relay-write-") or any(relative==x or relative.startswith(x+"/") for x in exclude):
                continue
            relative=relpath(relative)
            folded=relative.casefold()
            require(folded not in portable,"PATH_ALIAS",relative)
            portable.add(folded)
            s=path.lstat()
            require(stat.S_ISREG(s.st_mode) and s.st_nlink==1,"UNSAFE_FILE",relative)
            require(s.st_size<=16*1024*1024,"FILE_LIMIT",relative)
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
            with os.fdopen(fd,"rb") as f:
                before=os.fstat(f.fileno())
                raw=f.read(16*1024*1024+1)
                after=os.fstat(f.fileno())
            require(_signature(s)==_signature(before)==_signature(after)==_signature(path.lstat()),"CAPTURE_RACE",relative)
            total+=len(raw)
            require(total<=MAX_TREE and len(entries)<MAX_FILES,"CANDIDATE_LIMIT","candidate exceeds bounded capture profile")
            entries[relative]={"sha256":digest(raw),"size":len(raw),"executable":bool(s.st_mode&0o111)}
            raws[relative]=raw
    git_after=git_identity(root)
    require(git_before==git_after,"CAPTURE_RACE","Git changed during capture")
    return {"files":entries,"git":git_after,"exclude":exclude,"built_in_excludes":sorted(SKIP_DIRS),"total_bytes":total},raws


def stable_tree(root: Path, exclude: list[str]) -> tuple[dict,dict[str,bytes]]:
    first,raws=scan_tree(root,exclude)
    second,_=scan_tree(root,exclude)
    require(first==second,"CAPTURE_RACE","inputs changed between capture passes")
    return first,raws


def register_candidate(controller,token,command_id,payload):
    require(type(payload) is dict and set(payload)=={"id","attempt","context"},"INVALID_FIELDS","candidate.capture requires id, attempt, context")
    ident(payload["id"])
    def get(tx,actor):
        attempt,task=controller.attempt(tx,actor,payload["attempt"],controller.store.clock())
        context=controller._context(tx,attempt,task,payload["context"])
        require(bool(task["repos"]),"NO_REPOSITORIES","candidate must cover registered inputs")
        return task,context,[tx.get("repo",r) for r in task["repos"]]
    task,context,repos=controller.store.read(token,get)
    manifests={}; contents={}
    for repo in repos:
        manifest,raws=stable_tree(Path(repo["root"]),repo["exclude"])
        manifests[repo["id"]]=manifest
        contents[repo["id"]]=raws
    def apply(tx,actor,now):
        attempt,current=controller.attempt(tx,actor,payload["attempt"],now)
        require(controller._context(tx,attempt,current,payload["context"])["stamp"]==context["stamp"],"STALE_CONTEXT","capture context changed")
        blobs={}
        for repo,raws in contents.items():
            blobs[repo]={name:tx.blob(raw) for name,raw in raws.items()}
        vector={r:{"manifest_hash":object_digest(m),"git_head":m["git"]["head"] if m["git"] else None} for r,m in manifests.items()}
        obj=tx.put("candidate",payload["id"],task["workflow"],{"task":task["id"],"attempt":attempt["id"],"stamp":context["stamp"],
                    "manifests":manifests,"manifest_hash":object_digest(manifests),"vector":vector,"blobs":blobs,
                    "roots":{r["id"]:r["root"] for r in repos},"captured_at":now,"capture_profile":"stable-two-pass-not-atomic-filesystem-snapshot"},0)
        return {"candidate":obj}
    return controller.store.command(token,command_id,"candidate.capture",payload,apply)


def verify_live_candidate(tx:Transaction,candidate:dict):
    actual={}
    for id,root in candidate["roots"].items():
        repo=tx.get("repo",id)
        require(repo["root"]==root,"STALE_CANDIDATE","root registration changed")
        manifest,_=stable_tree(Path(root),repo["exclude"])
        actual[id]=manifest
    require(object_digest(actual)==candidate["manifest_hash"],"STALE_CANDIDATE","working tree, untracked input, mode, Git ref or configuration changed")
    for files in candidate["blobs"].values():
        for b in files.values():
            tx.read_blob(b)


def stage_candidate(tx:Transaction,candidate:dict,destination:Path):
    for repo,entries in candidate["manifests"].items():
        target=destination/repo; target.mkdir(parents=True,mode=0o700)
        for name,entry in entries["files"].items():
            path=target/relpath(name); path.parent.mkdir(parents=True,exist_ok=True)
            raw=tx.read_blob(candidate["blobs"][repo][name])
            require(digest(raw)==entry["sha256"],"CANDIDATE_CORRUPT",name)
            path.write_bytes(raw)
            path.chmod(0o700 if entry["executable"] else 0o600)


@contextmanager
def safe_parent(root:Path,relative:str):
    parts=relpath(relative).split("/")
    # Resolve at registration time; reject any later symlink inserted anywhere.
    absolute=root.absolute()
    fd=os.open("/",os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=new
        for part in parts[:-1]:
            new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=new
        yield fd,parts[-1]
    except OSError as e:
        raise RelayError("FILESYSTEM_BOUNDARY",str(e)) from e
    finally:
        os.close(fd)


def _read_at(fd:int,name:str):
    try:
        filefd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
    except FileNotFoundError:
        return None
    with os.fdopen(filefd,"rb") as f:
        s=os.fstat(f.fileno())
        require(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=32*1024*1024,"UNSAFE_FILE",name)
        raw=f.read(32*1024*1024+1)
        require(len(raw)<=32*1024*1024,"FILE_LIMIT",name)
        return raw


def file_observation(root:Path,path:str) -> str:
    with safe_parent(root,path) as (fd,name):
        raw=_read_at(fd,name)
        return "ABSENT" if raw is None else digest(raw)


def managed_write(root:Path,path:str,expected:str,raw:bytes) -> dict:
    with safe_parent(root,path) as (fd,name):
        current=_read_at(fd,name)
        observed="ABSENT" if current is None else digest(current)
        require(observed==expected,"COMPARE_AND_SET",f"expected {expected}; actual {observed}")
        tmp=".relay-write-"+secrets.token_hex(16)
        outfd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        if current is not None:
            os.fchmod(outfd, stat.S_IMODE(os.stat(name,dir_fd=fd,follow_symlinks=False).st_mode) & 0o777)
        try:
            with os.fdopen(outfd,"wb") as f:
                f.write(raw);f.flush();os.fsync(f.fileno())
            # All competing Relay-managed writes are excluded by resource barriers.
            # Independent same-UID filesystem writers are outside that boundary.
            os.replace(tmp,name,src_dir_fd=fd,dst_dir_fd=fd)
            os.fsync(fd)
        finally:
            try:os.unlink(tmp,dir_fd=fd)
            except FileNotFoundError:pass
        check=_read_at(fd,name)
        require(check is not None and digest(check)==digest(raw),"READBACK_FAILED",path)
        return {"path":path,"before":observed,"after":digest(raw),"bytes":len(raw),"durable_readback":True}
