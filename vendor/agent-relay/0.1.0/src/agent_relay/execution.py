"""Bounded subprocess execution. This is a supervisor, NOT an OS sandbox."""
from __future__ import annotations
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import time
from typing import Callable
from .codec import digest, text
from .errors import RelayError, require

OUTPUT_LIMIT = 1024 * 1024
DENIED_ENV = {"RELAY_TOKEN", "RELAY_HOME", "PYTHONPATH", "PYTHONSTARTUP", "LD_PRELOAD", "LD_LIBRARY_PATH",
              "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH", "BASH_ENV", "ENV"}


def clean_environment(extra: dict) -> dict[str,str]:
    require(type(extra) is dict and len(extra)<=64,"INVALID_FIELD","environment must be an object")
    out={}
    for key,value in extra.items():
        require(type(key) is str and key.replace("_", "").isalnum() and not key[0].isdigit()
                and key not in DENIED_ENV,"UNSAFE_ENV",str(key))
        require(type(value) is str and "\x00" not in value and len(value)<=8192,"INVALID_FIELD",f"environment:{key}")
        out[key]=value
    return out


def pin_command(argv: list[str], cwd: Path) -> dict:
    require(type(argv) is list and argv and all(type(x) is str and "\x00" not in x for x in argv),"INVALID_FIELD","argv")
    exe=shutil.which(argv[0]) if not os.path.isabs(argv[0]) else argv[0]
    require(exe is not None,"MISSING_EXECUTABLE",argv[0])
    invoked=Path(exe).absolute()
    exe=invoked.resolve()
    require(exe.is_file() and os.access(exe,os.X_OK),"MISSING_EXECUTABLE",str(exe))
    pins={str(exe):digest(exe.read_bytes())}
    for arg in argv[1:]:
        if not arg.startswith("-"):
            candidate=Path(arg) if os.path.isabs(arg) else cwd/arg
            if candidate.is_file():
                pins[str(candidate.resolve())]=digest(candidate.read_bytes())
    return {"argv":[str(invoked),*argv[1:]],"files":pins}


def validate_pins(pins: dict) -> None:
    for path,expected in pins["files"].items():
        p=Path(path)
        require(p.is_file() and digest(p.read_bytes())==expected,"TOOL_CHANGED",path)


def _kill_group(pid: int, sig: int):
    try:
        os.killpg(pid,sig)
    except ProcessLookupError:
        pass


def run_process(argv: list[str], cwd: Path, *, timeout: float, stdin: bytes=b"",
                environment: dict | None=None, on_spawn: Callable[[dict],None] | None=None,
                output_limit: int=OUTPUT_LIMIT) -> dict:
    """Drain both pipes without unbounded communicate() buffering; kill full group on limits."""
    env={"PATH":"/usr/bin:/bin:/usr/sbin:/sbin", "LANG":"C.UTF-8", "LC_ALL":"C.UTF-8",
         "PYTHONDONTWRITEBYTECODE":"1", "PYTHONUNBUFFERED":"1"}
    env.update(clean_environment(environment or {}))
    started=time.monotonic()
    try:
        proc=subprocess.Popen(argv,cwd=cwd,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,start_new_session=True,close_fds=True)
    except OSError as e:
        return {"returncode":None,"spawn_error":str(e),"stdout":"","stderr":"","timed_out":False,
                "output_limited":False,"elapsed_s":time.monotonic()-started,"pid":None}
    output={"stdout":bytearray(),"stderr":bytearray()}
    timed_out=False; limited=False; pending=memoryview(stdin); stop_at=None
    selector=selectors.DefaultSelector()
    try:
        if on_spawn:
            identity={"pid":proc.pid,"pgid":proc.pid,"observed_at":time.time(),
                      "command_hash":digest(__import__('json').dumps(argv).encode()),
                      "warning":"PID alone is not safe authority for signaling after restart"}
            on_spawn(identity)
        for name,stream in (("stdout",proc.stdout),("stderr",proc.stderr)):
            os.set_blocking(stream.fileno(),False)
            selector.register(stream,selectors.EVENT_READ,name)
        if pending:
            os.set_blocking(proc.stdin.fileno(),False)
            selector.register(proc.stdin,selectors.EVENT_WRITE,"stdin")
        else:
            proc.stdin.close()
        while selector.get_map() or proc.poll() is None:
            now=time.monotonic()
            if now-started>=timeout and stop_at is None:
                timed_out=True; stop_at=now; _kill_group(proc.pid,signal.SIGTERM)
            if stop_at is not None and now-stop_at>=0.2:
                _kill_group(proc.pid,signal.SIGKILL)
            if stop_at is not None and now-stop_at>=1.0:
                break
            for key,mask in selector.select(0.03):
                stream=key.fileobj; name=key.data
                if name=="stdin":
                    try:
                        count=os.write(stream.fileno(),pending[:65536])
                        pending=pending[count:]
                    except BrokenPipeError:
                        pending=memoryview(b"")
                    except BlockingIOError:
                        continue
                    if not pending:
                        selector.unregister(stream); stream.close()
                    continue
                try:
                    chunk=os.read(stream.fileno(),65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream); stream.close(); continue
                remaining=output_limit-len(output[name])
                output[name].extend(chunk[:max(0,remaining)])
                if len(chunk)>remaining:
                    limited=True
                    if stop_at is None:
                        stop_at=time.monotonic(); _kill_group(proc.pid,signal.SIGTERM)
        if proc.poll() is None:
            _kill_group(proc.pid,signal.SIGKILL)
        proc.wait(timeout=3)
    except BaseException:
        _kill_group(proc.pid,signal.SIGKILL)
        proc.wait(timeout=3)
        raise
    finally:
        selector.close()
        for stream in (proc.stdin,proc.stdout,proc.stderr):
            if stream and not stream.closed:
                stream.close()
    return {"returncode":proc.returncode,"stdout":output["stdout"].decode("utf-8","replace"),
            "stderr":output["stderr"].decode("utf-8","replace"),"timed_out":timed_out,"output_limited":limited,
            "elapsed_s":time.monotonic()-started,"pid":proc.pid}
