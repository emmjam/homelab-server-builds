"""Fixed snapshot destination. No arguments, commands, or caller-selected paths."""
import json
import os
from pathlib import Path
import sys
import tempfile
DEST=Path('/var/lib/rufus-discovery/status/nodes.json')
def publish(raw,destination=DEST):
    if len(raw)>1048576:raise ValueError('Snapshot too large')
    value=json.loads(raw)
    if value.get('schema_version')!=1 or not isinstance(value.get('nodes'),list) or len(value['nodes'])>100:raise ValueError('Invalid snapshot')
    fd,name=tempfile.mkstemp(dir=destination.parent,prefix='.nodes-')
    try:
        with os.fdopen(fd,'w') as f:
            os.fchmod(f.fileno(),0o640);json.dump(value,f,separators=(',',':'));f.flush();os.fsync(f.fileno())
        os.replace(name,destination)
    finally:
        if os.path.exists(name):os.unlink(name)
if __name__=='__main__':
    if len(sys.argv)!=1:raise SystemExit('No arguments accepted')
    publish(sys.stdin.read(1048577));print('Node snapshot published')
