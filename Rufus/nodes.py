"""Read-only node-status view. Queries cannot schedule work or execute commands."""
import copy
import json
from pathlib import Path
import time
class NodeStatusError(Exception):
    def __init__(self,message,status=503):super().__init__(message);self.status=status
class Nodes:
    def __init__(self,path='/var/lib/rufus-discovery/status/nodes.json',clock=time.time):self.path=Path(path);self.clock=clock
    def get(self,node=None):
        try:
            raw=self.path.read_bytes()
            if len(raw)>1048576:raise ValueError()
            snapshot=json.loads(raw)
            if snapshot['schema_version']!=1 or not 60<=snapshot['stale_seconds']<=86400:raise ValueError()
            records=copy.deepcopy(snapshot['nodes']);now=self.clock()
            for record in records:
                observation=record['observation']
                # Source probe age plus local receipt age tolerates cross-host clock skew.
                age=(now-snapshot.get('received_at',snapshot['collected_at'])
                     +snapshot['collected_at']-observation['checked_at'])
                record['stale']=age<0 or age>snapshot['stale_seconds']
                record['age_seconds']=max(0,round(age,1))
                if record['stale']:
                    record['last_observation']=dict(observation)
                    record['observation']={'state':'stale','checked_at':observation['checked_at'],'awake':None,'ssh_available':None,
                        'health':None,'metrics':None,'workloads':{w:{'state':'unknown','reason':'Status expired'} for w in record['supported_workloads']}}
            if node is not None:
                found=next((r for r in records if r['id']==node),None)
                if found is None:raise NodeStatusError('Unknown compute node',404)
                return found
            return {'collected_at':snapshot['collected_at'],'received_at':snapshot.get('received_at'),
                    'source_clock_offset_seconds':snapshot.get('source_clock_offset_seconds'),
                    'stale_seconds':snapshot['stale_seconds'],'nodes':records}
        except (OSError,ValueError,KeyError,TypeError):raise NodeStatusError('Node discovery snapshot unavailable or invalid') from None
