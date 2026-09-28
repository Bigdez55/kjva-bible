import base64
import io
import json
import time
from agent_relay.adapters import ADAPTER_ID, CAPABILITIES, implementation_identity
from agent_relay.codec import canonical, digest
from agent_relay.controller import fresh_id
from agent_relay.mcp import MCPAdapter, run
from agent_relay.store import private_write
from support import RelayCase, gates
from integration_support import daemon, MCPProcess


class AdapterTests(RelayCase):
    def open_adapter(self):
        self.worker_token=self.worker()
        self.cmd('adapter.register',id='adapter',workflow='w',identity_source='identity',implementation=ADAPTER_ID)
        self.session=self.cmd('adapter.open',token=self.worker_token,id='session',adapter='adapter',client_name='test',client_version='1')['session']
        return self.session

    def invoke(self,op,**payload):
        return self.cmd('adapter.invoke',token=self.worker_token,session='session',epoch=self.session['epoch'],op=op,payload=payload)

    def start_task(self):
        self.open_adapter()
        self.cmd('repo.register',id='repo',workflow='w',root=str(self.repo))
        self.task(resources=['repo/repo'],repos=['repo'])
        self.attempt=self.invoke('task.claim',id='t',provider='ignored')['attempt']
        self.context=self.invoke('context.hydrate',attempt=self.attempt['id'])['context']
        return self.attempt,self.context

    def ack(self):
        return self.cmd('adapter.acknowledge',token=self.worker_token,session='session',epoch=self.session['epoch'],context=self.context['id'],body_hash=self.context['body_hash'])

    def prepare(self,id='action'):
        return self.invoke('action.prepare',id=id,attempt=self.attempt['id'],context=self.context['id'],type='file.write',args={'repo':'repo','path':'x.txt','expected_sha256':'ABSENT','data_b64':base64.b64encode(b'real payload').decode()})

    @gates('G24','G41')
    def test_owner_key_is_not_allowed_in_provider_adapter(self):
        self.cmd('adapter.register',id='adapter',workflow='w',identity_source='identity',implementation=ADAPTER_ID)
        with self.error('WORKER_CREDENTIAL_REQUIRED'):
            self.cmd('adapter.open',id='session',adapter='adapter',client_name='test',client_version='1')

    @gates('G24','G31')
    def test_only_shipped_adapter_can_be_enabled(self):
        before=self.store.doctor()['chain_head']
        with self.error('UNSUPPORTED_ADAPTER'):
            self.cmd('adapter.register',id='fake',workflow='w',identity_source='identity',implementation='claude-pretend-native')
        self.assertEqual(before,self.store.doctor()['chain_head'])

    @gates('G24','G10')
    def test_identity_entry_must_be_real_owner_registered_agent_source(self):
        self.cmd('source.put',id='other',workflow='w',source_kind='reference',expected_rev=0,text='not identity')
        with self.error('IDENTITY_SOURCE'):
            self.cmd('adapter.register',id='adapter',workflow='w',identity_source='other',implementation=ADAPTER_ID)

    @gates('G24','G41')
    def test_native_tools_and_hidden_compaction_are_explicitly_not_claimed(self):
        self.open_adapter()
        spec=self.get('adapter','adapter',token=self.worker_token)
        self.assertEqual(spec['capabilities'],CAPABILITIES)
        self.assertEqual(spec['capabilities']['native_provider_tools'],'NOT_INTERCEPTED')
        self.assertEqual(spec['capabilities']['native_provider_compaction'],'NOT_OBSERVED_NOT_CLAIMED')
        self.assertEqual(spec['implementation_sha256'],implementation_identity()['sha256'])

    @gates('G24','G40')
    def test_consequential_tool_requires_actual_context_hash_acknowledgment(self):
        self.start_task()
        with self.error('CONTEXT_NOT_ACKNOWLEDGED'):self.prepare()
        with self.error('DELIVERY_HASH'):
            self.cmd('adapter.acknowledge',token=self.worker_token,session='session',epoch=1,context=self.context['id'],body_hash='0'*64)
        self.ack()
        self.assertEqual(self.prepare()['action']['dispatch'],'PREPARED')

    @gates('G24','G12','G40')
    def test_context_reset_invalidates_acknowledgment_even_via_raw_api(self):
        self.start_task();self.ack()
        self.session=self.cmd('adapter.reset',token=self.worker_token,session='session',epoch=1,reason='context was cleared')['session']
        with self.error('STALE_CONTEXT'):
            self.cmd('action.prepare',token=self.worker_token,id='bypass',attempt=self.attempt['id'],context=self.context['id'],type='file.write',args={})
        self.context=self.invoke('context.hydrate',attempt=self.attempt['id'])['context']
        self.ack();self.assertEqual(self.prepare()['action']['dispatch'],'PREPARED')
        self.assertEqual(self.get('requirement','r')['status'],'OPEN')

    @gates('G24','G20','G40')
    def test_source_change_requires_fresh_hydration_before_ack(self):
        self.start_task()
        self.cmd('source.put',id='identity',workflow='w',source_kind='Agent.md',text='Updated identity',expected_rev=1)
        with self.error('STALE_CONTEXT'):self.ack()
        hydrated=self.invoke('context.hydrate',attempt=self.attempt['id'])
        self.assertEqual(hydrated['body']['adapter']['identity_revision'],2)
        self.context=hydrated['context'];self.ack();self.prepare()

    @gates('G24','G41')
    def test_adapter_does_not_expose_owner_tools(self):
        self.open_adapter()
        with self.error('ADAPTER_TOOL_DENIED'):
            self.invoke('workflow.revise',id='w',expected_rev=1,directive='replace all requirements',reason='injection')
        self.assertEqual(self.get('workflow','w')['intent_revision'],1)

    @gates('G24','G41')
    def test_other_worker_cannot_reuse_session(self):
        self.open_adapter();other=self.worker('other')
        with self.error('FORBIDDEN'):
            self.cmd('adapter.reset',token=other,session='session',epoch=1,reason='steal')

    @gates('G24','G26')
    def test_disabled_adapter_fences_old_attempts(self):
        self.start_task();self.ack()
        self.cmd('adapter.disable',id='adapter',reason='operator disabled this executor')
        with self.error('ADAPTER_HELD'):self.cmd('attempt.heartbeat',token=self.worker_token,id=self.attempt['id'])

    @gates('G24','G13','G25')
    def test_close_releases_leases_but_does_not_discard_unknown_action(self):
        self.start_task();self.ack();action=self.prepare()['action']
        self.cmd('action.start',id=action['id'])
        self.cmd('adapter.close',token=self.worker_token,session='session',epoch=1,reason='provider stopped')
        self.assertEqual(self.get('attempt',self.attempt['id'])['status'],'RELEASED')
        self.assertEqual(self.get('action',action['id'])['outcome'],'UNKNOWN')
        with self.error('NOT_READY'):self.claim()

    @gates('G24','G14')
    def test_adapter_tool_duplicate_command_does_not_double_claim(self):
        self.open_adapter();self.task()
        p={'session':'session','epoch':1,'op':'task.claim','payload':{'id':'t','provider':'test'}}
        a=self.cmd('adapter.invoke',token=self.worker_token,cid='same',**p)
        before=self.store.doctor()['events']
        b=self.cmd('adapter.invoke',token=self.worker_token,cid='same',**p)
        self.assertEqual(a,b);self.assertEqual(before,self.store.doctor()['events'])


class MCPWireTests(RelayCase):
    def setup_adapter(self):
        token=self.worker()
        self.cmd('adapter.register',id='adapter',workflow='w',identity_source='identity',implementation=ADAPTER_ID)
        path=self.base/'worker.token';private_write(path,(token+'\n').encode())
        return token,path

    @gates('G24','G10','G40')
    def test_real_stdio_handshake_identity_tools_hydration_ack_and_interception(self):
        token,path=self.setup_adapter();self.task()
        with daemon(self.home):
            m=MCPProcess(self.home,path)
            try:
                init=m.initialize();self.assertIn('provider-neutral identity',init['instructions'])
                listing=m.request('tools/list')['result']['tools']
                self.assertTrue(any(x['name']=='relay_prepare' for x in listing))
                claimed,bad=m.tool('relay_claim',{'id':'t','command_id':'claim'})
                self.assertFalse(bad);aid=claimed['attempt']['id']
                data,bad=m.tool('relay_hydrate',{'attempt':aid,'command_id':'hydrate'})
                self.assertFalse(bad);self.assertEqual(data['context']['body_hash'],digest(canonical(data['body'])))
                ack,bad=m.tool('relay_acknowledge',{'context':data['context']['id'],'body_hash':data['context']['body_hash'],'command_id':'ack'})
                self.assertFalse(bad)
                deny,bad=m.tool('workflow.revise',{})
                self.assertTrue(bad);self.assertEqual(deny['code'],'MCP_PARAMS')
            finally:m.close()
        self.assertEqual(self.get('attempt',aid)['status'],'RELEASED')
        self.store.doctor(True)

    @gates('G24','G12','G25','G26')
    def test_real_mcp_process_kill_and_cold_successor_preserve_original_job(self):
        token,path=self.setup_adapter();self.task()
        with daemon(self.home):
            m=MCPProcess(self.home,path,name='provider-A')
            try:
                m.initialize()
                result,bad=m.tool('relay_claim',{'id':'t','ttl':.05,'command_id':'claim-old'})
                self.assertFalse(bad);old=result['attempt']['id']
            finally:m.close(kill=True)
            time.sleep(.08)
            successor=MCPProcess(self.home,path,name='provider-B')
            try:
                successor.initialize()
                result,bad=successor.tool('relay_claim',{'id':'t','command_id':'claim-new'})
                self.assertFalse(bad);new=result['attempt']['id'];self.assertNotEqual(old,new)
                context,bad=successor.tool('relay_hydrate',{'attempt':new,'command_id':'cold'})
                self.assertFalse(bad)
                self.assertEqual(context['body']['requirements'][0]['text'],'Required original behavior')
                self.assertEqual(context['body']['workflow']['id'],'w')
                # Returning old process cannot promote or renew its former authority.
                from agent_relay.service import call
                with self.error('STALE_FENCE'):call(self.home,token,'attempt.heartbeat',{'id':old},'old-return')
            finally:successor.close()

    @gates('G24')
    def test_protocol_requires_initialize_and_initialized_notification(self):
        _,path=self.setup_adapter()
        with daemon(self.home):
            m=MCPProcess(self.home,path)
            try:
                self.assertEqual(m.request('tools/list')['error']['data']['code'],'MCP_LIFECYCLE')
                m.initialize()
                self.assertEqual(m.request('initialize',{})['error']['data']['code'],'MCP_LIFECYCLE')
                self.assertEqual(m.request('ping')['result'],{})
            finally:m.close()

    @gates('G24','G41')
    def test_stdio_rejects_malformed_and_oversized_frames(self):
        class NoClient:
            def call(self,*args):raise AssertionError('no mutation before valid initialize')
        for data,code,rc in ((b'{invalid}\n',-32700,0),(b'x'*(4*1024*1024+1),-32600,2)):
            out=io.BytesIO()
            actual=run(MCPAdapter(NoClient(),'adapter'),io.BytesIO(data),out)
            self.assertEqual(actual,rc);self.assertEqual(json.loads(out.getvalue())['error']['code'],code)
