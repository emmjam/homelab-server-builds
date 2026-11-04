#!/usr/bin/env python3
"""Non-disruptive client checks; never deploys or invokes live homelab operations."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--node', default=shutil.which('node'))
    parser.add_argument('--electron-node', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('/tmp/rufus-chat-0.2.0.vsix'))
    args = parser.parse_args()
    if not args.node:
        parser.error('Install/use Node 20+ or pass a VS Code Electron executable with --node and --electron-node')
    environment = dict(os.environ)
    if args.electron_node:
        environment['ELECTRON_RUN_AS_NODE'] = '1'
    logs = Path(tempfile.mkdtemp(prefix='rufus-vscode-validation-'))
    def run(name, command):
        with (logs / (name + '.log')).open('w') as output:
            result = subprocess.run(command, cwd=ROOT, env=environment, stdout=output,
                                    stderr=subprocess.STDOUT, timeout=180)
        print(json.dumps({'check':name,'status':'PASS' if not result.returncode else 'FAIL','log':str(logs/(name+'.log'))}),flush=True)
        if result.returncode:
            raise RuntimeError('Check failed: '+name)
    run('client-tests', [args.node,'--test',*map(str,sorted((ROOT/'RufusVSCode/test').glob('*.test.js')))])
    for path in [*sorted((ROOT/'RufusVSCode').glob('*.js')),*sorted((ROOT/'RufusVSCode/media').glob('*.js'))]:
        run('syntax-'+path.stem,[args.node,'--check',str(path)])
    run('package',[sys.executable,'scripts/package-rufus-vscode.py','--output',str(args.output)])
    second=logs/'repeat.vsix'
    run('package-repeat',[sys.executable,'scripts/package-rufus-vscode.py','--output',str(second)])
    assert args.output.read_bytes()==second.read_bytes(), 'Package is not reproducible'
    with zipfile.ZipFile(args.output) as archive:
        assert archive.testzip() is None
        manifest=ET.fromstring(archive.read('extension.vsixmanifest'))
        assert manifest.tag.endswith('PackageManifest')
        metadata=json.loads(archive.read('extension/package.json'))
        assert 'extension/'+metadata['main'].removeprefix('./') in archive.namelist()
        assert set(archive.namelist())=={'[Content_Types].xml','extension.vsixmanifest',*('extension/'+p for p in
            ['package.json','client.js','extension.js','README.md','media/index.html','media/panel.js','media/panel.css'])}
    print(json.dumps({'check':'package-integrity-and-reproducibility','status':'PASS','package':str(args.output),'logs':str(logs)}))


if __name__=='__main__':
    main()
