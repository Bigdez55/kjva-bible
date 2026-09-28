"""Real subprocess/socket fixtures. They never open a live user store."""
from __future__ import annotations
from contextlib import contextmanager
import json
import os
from pathlib import Path
import selectors
import ssl
import subprocess
import sys
import tempfile
import time
from agent_relay.codec import canonical, digest
from agent_relay.errors import RelayError
from agent_relay.service import call
from agent_relay.store import private_write


@contextmanager
def daemon(home: Path, tls_config: Path | None = None):
    with tempfile.TemporaryFile() as log:
        argv = [sys.executable, '-m', 'agent_relay.cli', '--home', str(home), 'serve']
        if tls_config:
            argv += ['--tls-config', str(tls_config)]
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log)
        try:
            token = (home / 'owner.key').read_text().strip()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    log.seek(0)
                    raise AssertionError(f'daemon exited {proc.returncode}: {log.read().decode()}')
                try:
                    call(home, token, 'version', {}, timeout=.2)
                    if not tls_config or (home / 'network.status.json').exists():
                        break
                except (RelayError, OSError):
                    pass
                time.sleep(.01)
            else:
                raise AssertionError('daemon startup timeout')
            yield proc
        finally:
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
            else:
                proc.wait()


class MCPProcess:
    def __init__(self, home: Path, token_file: Path, adapter='adapter', name='test-client', remote=None):
        self.log = tempfile.TemporaryFile()
        argv = [sys.executable, '-m', 'agent_relay.mcp', '--adapter', adapter]
        argv += ['--remote-config', str(remote)] if remote else ['--home', str(home), '--token-file', str(token_file)]
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log)
        self.counter = 0
        self.name = name

    def send(self, value):
        self.proc.stdin.write(canonical(value) + b'\n'); self.proc.stdin.flush()

    def receive(self):
        with selectors.DefaultSelector() as sel:
            sel.register(self.proc.stdout, selectors.EVENT_READ)
            if not sel.select(8):
                raise AssertionError('MCP response timeout')
        raw = self.proc.stdout.readline(16*1024*1024)
        if not raw:
            self.log.seek(0)
            raise AssertionError('MCP exited: '+self.log.read().decode())
        return json.loads(raw)

    def request(self, method, params=None):
        self.counter += 1
        self.send({'jsonrpc':'2.0','id':self.counter,'method':method,'params':params or {}})
        return self.receive()

    def initialize(self):
        value = self.request('initialize', {'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':self.name,'version':'fixture-1'}})
        if 'error' in value: raise AssertionError(value)
        self.send({'jsonrpc':'2.0','method':'notifications/initialized'})
        return value['result']

    def tool(self, name, arguments):
        value = self.request('tools/call', {'name':name,'arguments':arguments})
        if 'error' in value: raise AssertionError(value)
        result = value['result']
        payload = json.loads(result['content'][0]['text'])
        return payload, result['isError']

    def close(self, kill=False):
        try:
            if self.proc.poll() is None:
                if kill:
                    self.proc.kill()
                else:
                    self.proc.stdin.close()
                try: self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired: self.proc.kill(); self.proc.wait(timeout=5)
        finally:
            for f in (self.proc.stdin,self.proc.stdout):
                if f is not None: f.close()
            self.log.close()


class TLSMaterial:
    def __init__(self, base: Path):
        self.base = base
        base.mkdir(mode=0o700)
        self.run('req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-noenc','-days','1',
                 '-subj','/CN=Relay disposable fixture CA','-keyout',str(base/'ca.key'),'-out',str(base/'ca.pem'),
                 '-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign')
        self.issue('server', True)
        self.issue('client', False)
        self.issue('other', False)
        for p in base.iterdir(): p.chmod(0o600)

    def run(self,*args):
        p = subprocess.run(['openssl',*args], capture_output=True, text=True, timeout=10)
        if p.returncode: raise AssertionError(p.stderr)

    def issue(self,name,server):
        b=self.base
        self.run('req','-new','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-noenc','-subj','/CN='+name,
                 '-keyout',str(b/(name+'.key')),'-out',str(b/(name+'.csr')))
        ext=b/(name+'.ext')
        ext.write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage='+('serverAuth' if server else 'clientAuth')+'\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n'+('subjectAltName=DNS:localhost,IP:127.0.0.1\n' if server else ''))
        self.run('x509','-req','-in',str(b/(name+'.csr')),'-CA',str(b/'ca.pem'),'-CAkey',str(b/'ca.key'),'-CAcreateserial',
                 '-out',str(b/(name+'.pem')),'-days','1','-extfile',str(ext))

    def fingerprint(self,name='client'):
        return digest(ssl.PEM_cert_to_DER_cert((self.base/(name+'.pem')).read_text()))

    def server_config(self, name='listen.json', port=0):
        path=self.base/name
        private_write(path,canonical({'version':1,'host':'127.0.0.1','port':port,'cert':str(self.base/'server.pem'),'key':str(self.base/'server.key'),'ca':str(self.base/'ca.pem')}))
        return path

    def client_config(self,port,token_file,name='client',filename=None):
        path=self.base/(filename or name+'-connect.json')
        private_write(path,canonical({'version':1,'host':'127.0.0.1','port':port,'server_name':'localhost',
            'cert':str(self.base/(name+'.pem')),'key':str(self.base/(name+'.key')),'ca':str(self.base/'ca.pem'),'token_file':str(token_file)}))
        return path
