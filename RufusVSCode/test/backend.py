"""Isolated actual API/web/auth/SQLite with mocked inference/Rundeck; no live nodes."""
import json
from pathlib import Path
import sys
import threading
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/rufus'))
from test_workflow import WorkflowTests
from app import handler as api_handler
sys.path.insert(0, str(ROOT / 'RufusWeb'))
from web import handler, Client
from auth import Auth, password_hash

case = WorkflowTests()
case.setUp()
approve = case.propose()
case.conversation = case.flow.store.create()['id']
case.client.output.side_effect = lambda execution: [{'message':json.dumps(case.evidence(False)),'level':'INFO'}]
case.model.chat.side_effect = [json.dumps({'intent':'repair','target':'fixture','explanation':'Cache unavailable'}),
    json.dumps({'operation':'fixture-restart','target':'fixture','parameters':{},'summary':'Restore the fixture'})]
reject = case.propose()
case.client.output.side_effect = lambda execution: [{'message':json.dumps(case.evidence(True)),'level':'INFO'}]
case.model.chat.side_effect = lambda messages, schema=None: json.dumps({'intent':'chat','target':'unknown','explanation':'Ordinary chat'}) if schema else 'Willow is remembered. <script>Never execute this</script>'
case.client.job.side_effect = lambda ident: {'id':ident,'name':'Approved fixture operation'}
api = ThreadingHTTPServer(('127.0.0.1',0),api_handler(case.app))
threading.Thread(target=api.serve_forever,daemon=True).start()
source = Path(case.temp.name)
(source/'token').write_text(case.config['api_token'])
(source/'accounts').write_text(json.dumps([{'id':'test-operator','username':'test','enabled':True,'version':'1','password_hash':password_hash('test-only-password')}]))
config={'api_url':'http://127.0.0.1:'+str(api.server_port),'api_token_file':str(source/'token'),
    'database':str(source/'web.sqlite'),'accounts_file':str(source/'accounts'),'allowed_origins':[]}
web = ThreadingHTTPServer(('127.0.0.1',0),handler(config,Auth(config),Client(config)))
url='http://127.0.0.1:'+str(web.server_port)
config['allowed_origins']=[url]
threading.Thread(target=web.serve_forever,daemon=True).start()
print(json.dumps({'url':url,'approve':approve,'reject':reject}),flush=True)
try:
    for line in sys.stdin:
        if line.strip()=='stats':print(json.dumps({'executions':len(case.executions)}),flush=True)
        elif line.strip()=='stop':break
finally:
    web.shutdown();web.server_close();api.shutdown();api.server_close();case.doCleanups()
