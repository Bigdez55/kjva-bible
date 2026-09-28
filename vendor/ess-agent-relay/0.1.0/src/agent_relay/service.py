"""Versioned, bounded JSON RPC over a private Unix-domain socket."""
from __future__ import annotations
import json
import os
from pathlib import Path
import signal
import socket
import socketserver
import struct
import threading
import time
from . import __version__
from .codec import MAX_REQUEST,canonical,strict_loads,ident
from .controller import Controller,owner,fresh_id
from .dispatch import dispatch,reconcile
from .errors import RelayError,require
from .verification import register_verifier,run_verifier
from .workspace import register_candidate

MAX_RESPONSE=16*1024*1024


def receive(sock:socket.socket,limit:int) -> dict:
    def readn(n):
        chunks=[]
        while n:
            part=sock.recv(min(n,65536))
            require(bool(part),"RPC_EOF","connection closed early")
            chunks.append(part);n-=len(part)
        return b"".join(chunks)
    size=struct.unpack("!I",readn(4))[0]
    require(0<size<=limit,"RPC_SIZE",f"message limit {limit}")
    obj=strict_loads(readn(size))
    require(type(obj) is dict,"RPC_SCHEMA","RPC envelope must be an object")
    return obj


def send(sock:socket.socket,value:dict,limit:int):
    raw=canonical(value)
    require(len(raw)<=limit,"RPC_SIZE","response too large; narrow the request")
    sock.sendall(struct.pack("!I",len(raw))+raw)


def route(controller:Controller,request:dict) -> dict:
    require(set(request)=={"api_version","id","op","payload","token"} and type(request["api_version"]) is int
            and request["api_version"]==1,"RPC_SCHEMA","expected API version 1 envelope")
    op=request["op"];p=request["payload"];token=request["token"];id=ident(request["id"],"request id")
    require(type(op) is str and type(p) is dict,"RPC_SCHEMA","op/string and payload/object required")
    if op=="version":
        controller.store.read(token,lambda tx,a:True)
        return {"version":__version__,"profile":"single-host-trusted-workers","api_version":1}
    if op in {"status","get","work.ready"}:
        return controller.query(token,op,p)
    if op=="grant.token":
        require(set(p)=={"id"},"INVALID_FIELDS","grant.token requires id")
        return {"token":controller.issue_token(token,p["id"])}
    if op=="doctor":
        controller.store.read(token,lambda tx,a:owner(a))
        return controller.store.doctor(scrub=p.get("scrub",False) is True)
    if op=="candidate.capture":return register_candidate(controller,token,id,p)
    if op=="verifier.register":return register_verifier(controller,token,id,p)
    if op=="verify.run":return run_verifier(controller,token,id,p)
    if op=="action.dispatch":return dispatch(controller,token,id,p)
    if op=="action.reconcile":return reconcile(controller,token,id,p)
    return controller.command(token,id,op,p)


class RPCHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(30)
        try:
            request=receive(self.request,MAX_REQUEST)
            response={"ok":True,"result":route(self.server.controller,request)}
        except RelayError as e:
            response={"ok":False,"error":{"code":e.code,"message":e.message}}
        except (OSError,ValueError,KeyError,TypeError) as e:
            response={"ok":False,"error":{"code":"REQUEST_FAILED","message":str(e)}}
        except Exception:
            # Do not return stack traces or secrets to workers. Log only the class.
            response={"ok":False,"error":{"code":"INTERNAL","message":"controller error; inspect operator diagnostics"}}
        try:send(self.request,response,MAX_RESPONSE)
        except (OSError,RelayError):pass


class RPCServer(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=False
    block_on_close=True
    request_queue_size=32
    def __init__(self,address,controller):
        self.controller=controller
        self.capacity=threading.BoundedSemaphore(16)
        super().__init__(address,RPCHandler)
    def process_request(self,request,client_address):
        if not self.capacity.acquire(False):
            try:send(request,{"ok":False,"error":{"code":"BUSY","message":"controller concurrency limit"}},MAX_RESPONSE)
            except (OSError,RelayError):pass
            self.shutdown_request(request);return
        try:super().process_request(request,client_address)
        except BaseException:self.capacity.release();raise
    def process_request_thread(self,request,client_address):
        try:super().process_request_thread(request,client_address)
        finally:self.capacity.release()


def serve(controller:Controller,auto_dispatch:bool=False):
    store=controller.store
    path=store.home/"relay.sock"
    require(len(os.fsencode(path))<100,"SOCKET_PATH","use a shorter home path (<100 bytes including /relay.sock)")
    stop=threading.Event()
    with store.service_lock():
        store.doctor(scrub=True)  # one complete recovery check before admitting any client
        if path.exists():
            require(path.is_socket(),"SOCKET_PATH","existing path is not a socket")
            path.unlink()
        server=RPCServer(str(path),controller);os.chmod(path,0o600)
        dispatcher=None
        if auto_dispatch:
            def loop():
                seen=set()
                while not stop.is_set():
                    try:
                        actions=store.read(store.key,lambda tx,a:[x for x in tx.scan("action") if x["dispatch"]=="PREPARED"])
                        for action in actions:
                            if action["id"] in seen or stop.is_set():continue
                            seen.add(action["id"])
                            try:dispatch(controller,store.key,fresh_id("auto"),{"id":action["id"]})
                            except RelayError:pass # held; operator resolves. Never blind-loop an effect.
                    except (RelayError,OSError):pass
                    stop.wait(0.2)
            dispatcher=threading.Thread(target=loop,name="relay-dispatch",daemon=False);dispatcher.start()
        previous={}
        if threading.current_thread() is threading.main_thread():
            def shutdown(signum,frame):
                stop.set();threading.Thread(target=server.shutdown,daemon=True).start()
            for sig in (signal.SIGTERM,signal.SIGINT):
                previous[sig]=signal.signal(sig,shutdown)
        try:server.serve_forever(poll_interval=0.1)
        finally:
            stop.set()
            if dispatcher:dispatcher.join()
            server.server_close();path.unlink(missing_ok=True)
            for sig,handler in previous.items():signal.signal(sig,handler)


def call(home:Path,token:str,op:str,payload:dict,command_id:str|None=None,timeout:float=3700) -> dict:
    request={"api_version":1,"id":command_id or fresh_id("cmd"),"op":op,"payload":payload,"token":token}
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:sock.connect(str(Path(home)/"relay.sock"))
        except OSError as e:raise RelayError("SERVICE_UNAVAILABLE","start relayctl --home <home> serve") from e
        send(sock,request,MAX_REQUEST)
        response=receive(sock,MAX_RESPONSE)
    if not response.get("ok"):
        e=response.get("error",{})
        raise RelayError(e.get("code","RPC_ERROR"),e.get("message","unknown error"))
    return response["result"]
