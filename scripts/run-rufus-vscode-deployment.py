#!/usr/bin/env python3
"""Stage uncommitted working source without Git mutation; run one final SSH script.

The temporary Web credential is passed from SSH stdout to Node stdin in memory,
never echoed or written to evidence. Existing accounts are restored by the remote
script on success, client failure or EOF. No infrastructure jobs are submitted.
"""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SSH=['ssh','-F','/dev/null','-o','HostKeyAlias=rundeck','-o','StrictHostKeyChecking=yes',
     '-o','BatchMode=yes','-o','ConnectTimeout=10']
DEST='ian@rundeck.lan'


def main():
    work=Path(tempfile.mkdtemp(prefix='rufus-vscode-deployment-'))
    def report(value):
        line=json.dumps(value);print(line,flush=True)
        with (work/'acceptance.jsonl').open('a') as log:log.write(line+'\n')
    names=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT).decode().split('\0')
    names=sorted(set(name for name in names if name and (ROOT/name).is_file()))
    manifest={'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'files':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}}
    (work/'DEPLOYMENT-SOURCE.json').write_text(json.dumps(manifest,indent=2)+'\n')
    archive=work/'source.tgz'
    with tarfile.open(archive,'w:gz') as bundle:
        for name in names:bundle.add(ROOT/name,arcname=name,recursive=False)
        bundle.add(work/'DEPLOYMENT-SOURCE.json',arcname='DEPLOYMENT-SOURCE.json')
    remote=subprocess.check_output(SSH+[DEST,'mktemp -d /tmp/rufus-vscode-source.XXXXXXXX'],text=True).strip()
    assert remote.startswith('/tmp/rufus-vscode-source.') and '/' not in remote[len('/tmp/'):]
    subprocess.run(['scp',*SSH[1:],str(archive),DEST+':'+remote+'/source.tgz'],check=True)
    command='tar -xzf '+shlex.quote(remote+'/source.tgz')+' -C '+shlex.quote(remote)+' && sudo -n python3 '+shlex.quote(remote+'/scripts/rufus-vscode-deploy.py')
    report({'check':'staged-working-snapshot','source':remote,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'local_evidence':str(work)})
    process=subprocess.Popen(SSH+[DEST,command],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
    client_status=None;remote_pass=False
    try:
        for line in process.stdout:
            event=json.loads(line)
            if event.get('check')=='auth':
                client=subprocess.Popen(['/snap/code/current/usr/share/code/code',str(ROOT/'scripts/rufus-vscode-live.js')],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                    env={**os.environ,'ELECTRON_RUN_AS_NODE':'1'})
                client.stdin.write(json.dumps(event)+'\n');client.stdin.close()
                for diagnostic in client.stdout:
                    print(diagnostic.rstrip(),flush=True)
                    with (work/'client.jsonl').open('a') as log:log.write(diagnostic)
                client_status=client.wait(timeout=1200)
                process.stdin.write(json.dumps({'status':'PASS' if client_status==0 else 'FAIL'})+'\n');process.stdin.flush()
            else:
                report(event)
                if event.get('check')=='PASS':remote_pass=True
        code=process.wait(timeout=120)
        assert code==0 and client_status==0 and remote_pass,'Deployment/acceptance failed; retain continuation and inspect '+str(work)
        report({'check':'combined-deployment-and-live-transport-PASS','evidence':str(work)})
    finally:
        process.stdin.close()
        # Let remote finally restore the managed accounts if local acceptance failed.
        try:process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            report({'check':'cleanup-unresolved','source':remote,'instruction':'Inspect remote process/accounts before any retry; do not assume cleanup.'})

if __name__=='__main__':main()
