import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
from agent_relay.errors import RelayError
from agent_relay.selftest import run_selftest,start_service
from agent_relay.service import call,receive,send
from agent_relay.store import Store
from support import gates
import unittest


class ServiceTests(unittest.TestCase):
    @gates("G12","G13","G15","G18","G19","G26","G34")
    def test_real_socket_daemon_crash_recovery_vertical_slice(self):
        result=run_selftest()
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["checks"]),6)
        self.assertTrue(all(x["status"]=="PASS" for x in result["checks"]))
        self.assertFalse(result["live_workspace_opened"])

    @gates("G06","G28")
    def test_rpc_rejects_oversized_envelope(self):
        one,two=socket.socketpair()
        try:
            one.sendall(struct.pack("!I",10000000))
            with self.assertRaises(RelayError) as ctx:receive(two,1024)
            self.assertEqual(ctx.exception.code,"RPC_SIZE")
        finally:one.close();two.close()

    @gates("G06")
    def test_rpc_rejects_invalid_api_version(self):
        with tempfile.TemporaryDirectory(prefix="rly-") as tmp:
            home=Path(tmp)/"ctl";store=Store.initialize(home)
            with open(Path(tmp)/"err","wb") as log:
                proc=start_service(home,log)
                try:
                    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
                        sock.connect(str(home/"relay.sock"))
                        send(sock,{"api_version":999,"id":"r","op":"status","payload":{},"token":store.key},65536)
                        response=receive(sock,65536)
                        self.assertFalse(response["ok"])
                        self.assertEqual(response["error"]["code"],"RPC_SCHEMA")
                finally:proc.terminate();proc.wait(timeout=10)

    @gates("G31")
    def test_cli_initialization_uses_explicit_new_home(self):
        with tempfile.TemporaryDirectory(prefix="rly-") as tmp:
            home=Path(tmp)/"new"
            p=subprocess.run([sys.executable,"-m","agent_relay","--home",str(home),"init"],capture_output=True,text=True,timeout=10)
            self.assertEqual(p.returncode,0,p.stderr)
            result=json.loads(p.stdout)
            self.assertFalse(result["result"]["legacy_state_modified"])
            p2=subprocess.run([sys.executable,"-m","agent_relay","--home",str(home),"init"],capture_output=True,text=True,timeout=10)
            self.assertNotEqual(p2.returncode,0)
            self.assertEqual(json.loads(p2.stderr)["error"]["code"],"ALREADY_EXISTS")
