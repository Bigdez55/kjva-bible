"""Actual TLS sockets/processes, including dropped post-commit response and fencing.

Both endpoints are disposable processes on one machine. This tests network
partition mechanics, not independent physical-host or active-active durability.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import socket
import ssl
import threading
import time
from agent_relay.adapters import ADAPTER_ID
from agent_relay.codec import canonical, MAX_REQUEST
from agent_relay.errors import RelayError
from agent_relay.network import RemoteClient, server_context, client_context
from agent_relay.service import receive, send, MAX_RESPONSE, call
from agent_relay.store import private_write
from support import RelayCase, gates
from integration_support import TLSMaterial, daemon, MCPProcess


@contextmanager
def drop_committed_response(tls, upstream):
    """Relay a real request and observe its committed response, then drop the reply.

    Uses test-only CA material. The production runtime has no drop-success hook.
    The independent observer records the real server's result for comparison.
    """
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(5)
    port=listener.getsockname()[1];observed={}
    config=json.loads(upstream.read_text())
    inbound=server_context({'ca':str(tls.base/'ca.pem'),'cert':str(tls.base/'server.pem'),'key':str(tls.base/'server.key')})
    outbound=client_context(config)
    def proxy():
        try:
            raw,_=listener.accept()
            with raw, inbound.wrap_socket(raw,server_side=True) as front:
                request=receive(front,MAX_REQUEST)
                with socket.create_connection((config['host'],config['port']),5) as wire:
                    with outbound.wrap_socket(wire,server_hostname=config['server_name']) as back:
                        send(back,request,MAX_REQUEST)
                        observed['response']=receive(back,MAX_RESPONSE)
                # Server committed and replied, but the caller receives only EOF.
                front.shutdown(socket.SHUT_RDWR)
        except Exception as exc:observed['error']=repr(exc)
    worker=threading.Thread(target=proxy);worker.start()
    try:yield port,observed
    finally:
        worker.join(7);listener.close()
        if worker.is_alive():raise AssertionError('fault proxy did not stop')
        if 'error' in observed:raise AssertionError(observed['error'])


class NetworkTests(RelayCase):
    def setUp(self):
        super().setUp();self.store.clock=time.time
        self.tls=TLSMaterial(self.base/'tls')
        self.token=self.worker();self.tokenfile=self.base/'worker.token'
        private_write(self.tokenfile,(self.token+'\n').encode())
        self.cmd('peer.register',fingerprint=self.tls.fingerprint(),grant='worker')
        self.listen=self.tls.server_config()

    def client(self,filename='client-connect.json',name='client',tokenfile=None):
        port=json.loads((self.home/'network.status.json').read_text())['port']
        path=self.tls.client_config(port,tokenfile or self.tokenfile,name,filename)
        return RemoteClient(path,timeout=3),path

    @gates('G27','G18','G28')
    def test_real_mtls_worker_connects_to_same_single_authority(self):
        self.task()
        with daemon(self.home,self.listen):
            client,_=self.client()
            version=client.call('version',{})
            self.assertEqual(version['authority_id'],self.store.config['authority_id'])
            attempt=client.call('task.claim',{'id':'t','provider':'tls-worker'},'claim')['attempt']
            self.assertEqual(self.get('task','t')['active_attempt'],attempt['id'])
            self.assertEqual(client.call('get',{'kind':'requirement','id':'r'})['text'],'Required original behavior')
            self.assertEqual(json.loads((self.home/'network.status.json').read_text())['topology'],'ONE_AUTHORITY_REMOTE_WORKERS_NO_REPLICATION')
        self.assertFalse((self.home/'network.status.json').exists())
        self.store.doctor(True)

    @gates('G27','G14','G35')
    def test_lost_response_after_real_commit_replays_once_with_same_command_id(self):
        self.task()
        with daemon(self.home,self.listen):
            direct,path=self.client()
            before=self.store.doctor()['events']
            payload={'id':'t','provider':'partitioned-worker'}
            with drop_committed_response(self.tls,path) as (port,observed):
                via=self.tls.client_config(port,self.tokenfile,filename='proxy-connect.json')
                with self.error('REMOTE_OUTCOME_UNKNOWN'):
                    RemoteClient(via,timeout=3).call('task.claim',payload,'logical-claim')
            self.assertTrue(observed['response']['ok'])
            self.assertEqual(before+1,self.store.doctor()['events'])
            resumed=direct.call('task.claim',payload,'logical-claim')
            self.assertEqual(resumed,observed['response']['result'])
            self.assertEqual(before+1,self.store.doctor()['events'])
            with self.error('IDEMPOTENCY_CONFLICT'):
                direct.call('task.claim',{'id':'t','provider':'changed'},'logical-claim')
            self.assertEqual(before+1,self.store.doctor()['events'])

    @gates('G27','G19','G26','G43')
    def test_partition_expiry_old_worker_reconnect_cannot_renew_promote_or_prepare(self):
        self.task();self.task('independent')
        with daemon(self.home,self.listen):
            client,_=self.client()
            old=client.call('task.claim',{'id':'t','provider':'old','ttl':.05},'old')['attempt']
            context=client.call('context.hydrate',{'attempt':old['id']},'old-context')['context']
            # No messages from old worker while its lease expires; other work advances.
            parallel=call(self.home,self.key,'task.claim',{'id':'independent','provider':'other'},'independent')
            self.assertEqual(parallel['attempt']['task'],'independent')
            time.sleep(.08)
            new=client.call('task.claim',{'id':'t','provider':'successor'},'new')['attempt']
            self.assertGreater(new['fence'],old['fence'])
            for op,payload in [('attempt.heartbeat',{'id':old['id']}),
                               ('action.prepare',{'id':'late','attempt':old['id'],'context':context['id'],'type':'file.write','args':{}})]:
                with self.error('STALE_FENCE'):client.call(op,payload,'reconnect-'+op)
            with self.error('REMOTE_OPERATION_DENIED'):
                client.call('task.accept',{'id':'t','attempt':old['id']},'promote')
            self.assertEqual(self.get('task','t')['active_attempt'],new['id'])

    @gates('G27','G41')
    def test_remote_worker_cannot_enable_a_second_authority_or_owner_tools(self):
        with daemon(self.home,self.listen):
            client,_=self.client();before=self.store.doctor()['chain_head']
            for op in ('action.dispatch','verify.run','workflow.create','restore.resume','peer.register'):
                with self.error('REMOTE_OPERATION_DENIED'):client.call(op,{},'denied-'+op)
            self.assertEqual(before,self.store.doctor()['chain_head'])

    @gates('G27','G28','G41')
    def test_tls_certificate_must_match_registered_worker_grant(self):
        other=self.worker('other');otherfile=self.base/'other.token';private_write(otherfile,other.encode())
        with daemon(self.home,self.listen):
            wrong,_=self.client('mismatch.json',tokenfile=otherfile)
            with self.error('PEER_AUTH'):wrong.call('status',{})
            unregistered,_=self.client('unregistered.json',name='other')
            with self.error('PEER_AUTH'):unregistered.call('status',{})

    @gates('G27','G36','G41')
    def test_revocation_is_checked_even_for_previously_committed_replay(self):
        self.task()
        with daemon(self.home,self.listen):
            client,_=self.client();p={'id':'t','provider':'remote'}
            client.call('task.claim',p,'replay')
            call(self.home,self.key,'peer.revoke',{'fingerprint':self.tls.fingerprint(),'reason':'operator revocation'},'revoke')
            before=self.store.doctor()['events']
            with self.error('PEER_AUTH'):client.call('task.claim',p,'replay')
            self.assertEqual(before,self.store.doctor()['events'])

    @gates('G27','G41')
    def test_owner_key_rejected_even_in_handcrafted_tls_request(self):
        with daemon(self.home,self.listen):
            client,_=self.client()
            with socket.create_connection((client.config['host'],client.config['port']),3) as raw:
                with client.context.wrap_socket(raw,server_hostname='localhost') as wire:
                    send(wire,{'api_version':1,'id':'owner-bypass','op':'status','payload':{},'token':self.key},MAX_REQUEST)
                    response=receive(wire,MAX_RESPONSE)
            self.assertFalse(response['ok']);self.assertEqual(response['error']['code'],'REMOTE_OWNER_FORBIDDEN')

    @gates('G27','G41')
    def test_missing_client_certificate_and_wrong_server_identity_rejected(self):
        with daemon(self.home,self.listen):
            client,path=self.client()
            no_client=ssl.create_default_context(cafile=str(self.tls.base/'ca.pem'))
            no_client.minimum_version=ssl.TLSVersion.TLSv1_3
            with self.assertRaises((ssl.SSLError,ConnectionError,RelayError)):
                with socket.create_connection(('127.0.0.1',client.config['port']),3) as raw:
                    with no_client.wrap_socket(raw,server_hostname='localhost') as wire:
                        send(wire,{'api_version':1,'id':'no-cert','op':'status','payload':{},'token':self.token},MAX_REQUEST)
                        receive(wire,MAX_RESPONSE)
            config=json.loads(path.read_text());config['server_name']='not-the-relay.invalid'
            private_write(self.base/'wrong-host.json',canonical(config))
            with self.error('REMOTE_UNAVAILABLE'):RemoteClient(self.base/'wrong-host.json',timeout=2).call('status',{})

    @gates('G27','G14')
    def test_mutating_remote_call_requires_stable_id_and_unavailable_never_writes_offline(self):
        with daemon(self.home,self.listen):
            client,_=self.client()
            with self.error('COMMAND_ID_REQUIRED'):client.call('memory.add',{'id':'m','workflow':'w','text':'x','origin':'test'})
        before=self.store.doctor()['events']
        with self.error('REMOTE_UNAVAILABLE'):client.call('memory.add',{'id':'m','workflow':'w','text':'x','origin':'test'},'offline')
        self.assertEqual(before,self.store.doctor()['events'])

    @gates('G27','G24','G40')
    def test_real_mcp_stdio_adapter_uses_remote_tls_without_local_store_access(self):
        self.cmd('adapter.register',id='adapter',workflow='w',identity_source='identity',implementation=ADAPTER_ID)
        self.task()
        with daemon(self.home,self.listen):
            _,config=self.client()
            missing=self.base/'no-local-authority'
            process=MCPProcess(missing,self.tokenfile,remote=config)
            try:
                self.assertIn('provider-neutral',process.initialize()['instructions'])
                result,bad=process.tool('relay_claim',{'id':'t','command_id':'remote-claim'})
                self.assertFalse(bad)
                body,bad=process.tool('relay_hydrate',{'attempt':result['attempt']['id'],'command_id':'remote-hydrate'})
                self.assertFalse(bad);self.assertEqual(body['body']['workflow']['id'],'w')
                self.assertFalse(missing.exists())
            finally:process.close()
        self.store.doctor(True)
