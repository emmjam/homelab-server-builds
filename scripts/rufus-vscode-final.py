#!/usr/bin/env python3
"""One controller call: gateway regressions, Ansible deployment and live read-only HTTP acceptance.

Uses a temporary account through the existing managed account source; finally
restores that source/deployment. No worker contact, inference or Rundeck jobs.
"""
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0,str(ROOT/'RufusWeb'))
    sys.path.insert(0,str(ROOT/'tests/rufus'))
    from auth import password_hash
    from test_web import HTTPClient
    with tempfile.NamedTemporaryFile(mode='w',prefix='rufus-vscode-final-',suffix='.log',delete=False) as log:
        print('LOG '+log.name,flush=True)
        def command(args):
            subprocess.run(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
        def deploy():
            command(['ansible-playbook','-i','Ansible/inventory/ai2.ini','Ansible/playbooks/rufus-web.yml'])
        command([sys.executable,'-m','unittest','discover','-s','tests/rufus','-v'])
        print('PASS Rufus/web/approval/discovery regressions',flush=True)
        source=Path('/var/lib/rundeck/rufus-web-accounts.json')
        original=source.read_bytes()
        account='vscode-acceptance-'+secrets.token_hex(4)
        password=secrets.token_urlsafe(32)
        records=json.loads(original)
        records.append({'id':account,'username':account,'enabled':True,'version':'1','password_hash':password_hash(password)})
        try:
            # In-place writes preserve the existing account source metadata.
            source.write_text(json.dumps(records))
            deploy()
            print('PASS existing Ansible web deployment',flush=True)
            client=HTTPClient('http://rufus.lan:8788')
            status,_,_=client.login(account,password)
            assert status==200,'Live temporary account login failed'
            for endpoint in ['/api/conversations','/api/jobs','/api/executions/157']:
                status,payload,_=client.call(endpoint)
                assert status==200,(endpoint,status)
                log.write(endpoint+' HTTP '+str(status)+'\n')
                # Validate JSON without emitting conversation contents or credentials.
                assert isinstance(json.loads(payload),dict)
            assert client.call('/api/executions',{'operation':'apt-cache-restart','options':{}})[0]==403
            assert client.call('/api/executions',{},csrf=False)[0]==403
            assert client.call('/api/commands',{})[0]==404
            assert client.call('/logout',{})[0]==200
            assert client.call('/api/jobs')[0]==401
            print('PASS live login, conversations/jobs/recorded logs, direct mutation denial, CSRF and logout',flush=True)
        finally:
            source.write_bytes(original)
            deploy()
            assert source.read_bytes()==original
            print('PASS original accounts restored; temporary identity removed',flush=True)
        ssh=['sudo','-u','rundeck','ssh','-i','/var/lib/rundeck/.ssh/target_ed25519','-o','BatchMode=yes',
             '-o','HostKeyAlias=rufus','-o','UserKnownHostsFile=/var/lib/rundeck/.ssh/managed_debian_known_hosts',
             '-o','StrictHostKeyChecking=yes','rundeck@rufus.lan']
        deployed=subprocess.check_output(ssh+['sudo','-n','cat','/opt/rufus-web/app/web.py'])
        assert deployed==(ROOT/'RufusWeb/web.py').read_bytes()
        command(ssh+['sudo','-n','systemctl','is-active','rufus','rufus-web'])
        print('PASS deployed gateway matches source; both services active; no live jobs or inference submitted',flush=True)


if __name__=='__main__':
    main()
