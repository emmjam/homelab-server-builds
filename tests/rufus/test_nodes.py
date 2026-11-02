"""Passive discovery, state expiry, API isolation and probe safety."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,MagicMock,patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'NodeDiscovery'));sys.path.insert(0,str(ROOT/'Rufus'))
import collector
from nodes import Nodes,NodeStatusError
from app import Application,handler

class NodesTests(unittest.TestCase):
    def setUp(self):
        self.node={'id':'ai-agent','hostname':'ai-agent.lan','ssh':{'host':'ai-agent.lan','user':'rundeck','host_key_alias':'ai-agent'},
                   'machine_type':'HP','supported_workloads':['cpu','inference'],'known_capabilities':{'os':None}}
        self.config={'nodes':[self.node],'interval_seconds':300,'stale_seconds':660,'ssh_timeout_seconds':20,
            'ssh_key':'existing-key','known_hosts':'existing-hosts','busy_cpu_percent':85,'busy_memory_percent':15,'min_disk_bytes':100}
        self.facts={'hostname':'ai-agent','hardware':{'cpu':{'model':'test CPU','physical_cores':4},'ram_bytes':1000,
            'storage':[{'mount':'/','available_bytes':1000,'read_only':False}]},'os':{'id':'debian','version':'13'},
            'power':{'suspend_to_ram':True},'runtimes':{'ollama':{'reachable':True,'models':[{'name':'qwen3:4b'}]}},
            'metrics':{'cpu_busy_percent':1,'memory_available_bytes':900},'health':'running'}
        self.runner=Mock(return_value=Mock(returncode=0,stdout=json.dumps(self.facts)))
        self.connect=MagicMock();self.now=1000
    def check(self,old=None):return collector.check(self.node,old or {},self.config,'# fixed probe',clock=lambda:self.now,run=self.runner,connect=self.connect)
    def test_online_hardware_models_and_fixed_ssh(self):
        record=self.check();self.assertEqual(record['observation']['state'],'online_available')
        self.assertEqual(record['last_success_at'],1000)
        self.assertEqual(record['last_verified_capabilities']['runtimes']['ollama']['models'][0]['name'],'qwen3:4b')
        argv=self.runner.call_args.args[0]
        self.assertEqual(argv[-1],'python3 -');self.assertIn('StrictHostKeyChecking=yes',argv)
        self.assertNotIn('sudo',argv);self.assertNotIn('shell',self.runner.call_args.kwargs)
    def test_busy_and_workload_specific_unavailability(self):
        self.facts['metrics']['cpu_busy_percent']=95;self.runner.return_value.stdout=json.dumps(self.facts)
        self.assertEqual(self.check()['observation']['state'],'online_busy')
        self.facts['metrics']['cpu_busy_percent']=1;self.facts['runtimes']['ollama']['reachable']=False
        self.runner.return_value.stdout=json.dumps(self.facts)
        r=self.check()['observation'];self.assertEqual(r['state'],'online_available')
        self.assertEqual(r['workloads']['inference']['state'],'unavailable');self.assertEqual(r['workloads']['cpu']['state'],'available')
    def test_unhealthy_os_and_disk_are_not_available(self):
        for key,value in [('health','degraded'),('health','maintenance')]:
            facts=copy.deepcopy(self.facts);facts[key]=value;self.runner.return_value.stdout=json.dumps(facts)
            self.assertEqual(self.check()['observation']['state'],'online_unavailable')
        self.facts['hardware']['storage'][0]['available_bytes']=0;self.runner.return_value.stdout=json.dumps(self.facts)
        self.assertEqual(self.check()['observation']['state'],'online_unavailable')
    def test_unreachable_is_not_sleeping_and_facts_survive(self):
        old=self.check();self.now+=300;self.connect.side_effect=OSError()
        with patch('collector.shutil.which',return_value=None):record=self.check(old)
        self.assertEqual(record['observation']['state'],'unreachable');self.assertIsNone(record['observation']['awake'])
        self.assertEqual(record['last_success_at'],1000);self.assertEqual(record['last_verified_capabilities'],old['last_verified_capabilities'])
        self.assertIsNone(record['observation']['metrics'])
    def test_sleep_requires_recent_explicit_evidence_and_awake_overrides_it(self):
        self.node['power_evidence']={'state':'sleeping','observed_at':900,'source':'independent confirmed power observation'}
        self.assertEqual(collector.offline(self.node['power_evidence'],1000,660),'sleeping')
        self.assertEqual(collector.offline(self.node['power_evidence'],2000,660),'unreachable')
        self.assertEqual(collector.offline({'state':'sleeping'},1000,660),'unreachable')
        self.assertEqual(self.check()['observation']['state'],'online_available')
    def test_ssh_auth_failure_is_awake_without_claiming_healthy(self):
        self.runner.return_value.returncode=255
        record=self.check()['observation'];self.assertTrue(record['awake']);self.assertFalse(record['ssh_available'])
        self.assertEqual(record['state'],'online_unavailable')
    def test_refresh_after_wake_and_hostname_mismatch(self):
        self.connect.side_effect=OSError()
        with patch('collector.shutil.which',return_value=None):old=self.check()
        self.connect.side_effect=None;self.now+=300
        self.assertEqual(self.check(old)['last_success_at'],1300)
        self.facts['hostname']='other-node';self.runner.return_value.stdout=json.dumps(self.facts)
        record=self.check();self.assertIsNone(record['last_success_at']);self.assertEqual(record['observation']['reason'],'Node identity mismatch')
    def test_stale_status_expires_without_deleting_known_hardware(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'nodes.json';record=self.check()
            path.write_text(json.dumps({'schema_version':1,'collected_at':1000,'stale_seconds':660,'nodes':[record]}))
            view=Nodes(path,clock=lambda:self.now)
            self.assertFalse(view.get('ai-agent')['stale']);self.now=1661
            stale=view.get('ai-agent');self.assertTrue(stale['stale']);self.assertEqual(stale['observation']['state'],'stale')
            self.assertIsNone(stale['observation']['metrics']);self.assertIsNone(stale['observation']['awake'])
            self.assertEqual(stale['last_verified_capabilities'],record['last_verified_capabilities'])
            with self.assertRaises(NodeStatusError):view.get('not-in-inventory')
    def test_clock_skew_does_not_expire_a_fresh_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'nodes.json';record=self.check()
            path.write_text(json.dumps({'schema_version':1,'collected_at':1005,
                'received_at':905,'stale_seconds':660,'nodes':[record]}))
            view=Nodes(path,clock=lambda:906)
            self.assertFalse(view.get('ai-agent')['stale'])
            self.assertEqual(view.get('ai-agent')['age_seconds'],6)
            self.assertTrue(Nodes(path,clock=lambda:1566).get('ai-agent')['stale'])

    def test_inventory_injection_is_rejected_before_execution(self):
        for field in ('host','user','host_key_alias'):
            config=copy.deepcopy(self.config);config['nodes'][0]['ssh'][field]='host; touch /tmp/forbidden'
            with self.assertRaises(ValueError):collector.validate(config)
    def test_publisher_no_commands_and_atomic_fixed_snapshot(self):
        spec=importlib.util.spec_from_file_location('node_publisher',ROOT/'NodeDiscovery/publish.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'nodes.json';module.publish(json.dumps({'schema_version':1,'nodes':[]}),path)
            self.assertEqual(json.loads(path.read_text())['nodes'],[])
            self.assertEqual(path.stat().st_mode & 0o777,0o640)
            with self.assertRaises(ValueError):module.publish('x'*1048577,path)
    def test_status_api_has_no_action_or_refresh_path(self):
        import io
        from http.server import ThreadingHTTPServer
        import threading,urllib.request,urllib.error
        with tempfile.TemporaryDirectory() as tmp:
            app=Application({'database':tmp+'/db','jobs':{},'token':'rd','api_token':'api','rundeck_url':'http://unused'},Mock())
            app.nodes=Mock();app.nodes.get.return_value={'nodes':[]}
            server=ThreadingHTTPServer(('127.0.0.1',0),handler(app));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                base='http://127.0.0.1:'+str(server.server_port)
                for path,body,auth,expected in [('/nodes',None,False,401),('/nodes',None,True,200),('/nodes/ai-agent',None,True,200),('/nodes/ai-agent/refresh',{},True,404),('/nodes',{'command':'reboot'},True,404)]:
                    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Authorization':'Bearer api'} if auth else {})
                    try:
                        with urllib.request.urlopen(req) as f:status=f.status
                    except urllib.error.HTTPError as e:status=e.code
                    self.assertEqual(status,expected)
                app.client.start.assert_not_called()
            finally:server.shutdown();server.server_close();thread.join()
