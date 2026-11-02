"""Fixed Linux read-only probe, sent on stdin; no installation or sudo on nodes."""
import glob
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import time
import urllib.request

def read(path):
    try:return Path(path).read_text().strip()
    except OSError:return ''
def command(args):
    try:return subprocess.run(args,capture_output=True,text=True,timeout=3).stdout.strip()
    except (OSError,subprocess.TimeoutExpired):return ''
def cpu_ticks():
    ticks=list(map(int,read('/proc/stat').splitlines()[0].split()[1:9]))
    return sum(ticks),sum(ticks[3:5])
def models_at(urls):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for url in urls:
        try:
            with opener.open(url+'/api/tags',timeout=3) as response:raw=response.read(65537)
            if len(raw)>65536:raise ValueError('oversize')
            models=json.loads(raw)['models']
            return {'reachable':True,'endpoint':url,'models':[{'name':m['name'],'size':m.get('size'),'digest':m.get('digest')} for m in models[:64]]}
        except (OSError,ValueError,KeyError,TypeError):continue
    return {'reachable':False,'endpoint':None,'models':None}

def probe():
    cpu={};cores=set()
    for block in read('/proc/cpuinfo').split('\n\n'):
        values=dict(line.split(':',1) for line in block.splitlines() if ':' in line)
        values={k.strip():v.strip() for k,v in values.items()}
        if values.get('model name'):cpu['model']=values['model name']
        if 'core id' in values:cores.add((values.get('physical id','0'),values['core id']))
    cpu.update(physical_cores=len(cores) or None,logical_cpus=os.cpu_count())
    mem={}
    for line in read('/proc/meminfo').splitlines():
        parts=line.split()
        if parts[0].rstrip(':') in ('MemTotal','MemAvailable','SwapTotal','SwapFree'):mem[parts[0].rstrip(':')]=int(parts[1])*1024
    before=cpu_ticks();time.sleep(.2);after=cpu_ticks()
    busy=round(100*(1-(after[1]-before[1])/max(1,after[0]-before[0])),1)
    release={}
    for line in read('/etc/os-release').splitlines():
        key,sep,value=line.partition('=')
        if sep:
            try:release[key]=' '.join(shlex.split(value))
            except ValueError:pass
    disks=[]
    for line in read('/proc/mounts').splitlines():
        parts=line.split()
        if len(parts)<4 or parts[2] not in ('ext2','ext3','ext4','xfs','btrfs','zfs'):continue
        mount=parts[1].replace('\\040',' ')
        try:
            v=os.statvfs(mount)
            disks.append({'mount':mount,'filesystem':parts[2],'total_bytes':v.f_blocks*v.f_frsize,
                          'available_bytes':v.f_bavail*v.f_frsize,'read_only':bool(v.f_flag & os.ST_RDONLY)})
        except OSError:continue
        if len(disks)>=64:break
    if not any(d['mount']=='/' for d in disks):
        v=os.statvfs('/');disks.insert(0,{'mount':'/','filesystem':'unknown','total_bytes':v.f_blocks*v.f_frsize,'available_bytes':v.f_bavail*v.f_frsize,'read_only':bool(v.f_flag & os.ST_RDONLY)})
    runtimes=[name for name in ('ollama','llama-server','llama-cli','vllm') if shutil.which(name)]
    service=command(['systemctl','is-active','ollama'])
    ollama={'installed':'ollama' in runtimes,'service_state':service or 'unknown','reachable':False,'models':None}
    if ollama['installed'] or service=='active':
        ollama['installed']=True
        # Nodes may bind either loopback (Dell) or their LAN address (HP).
        # Both requests originate on that node; no listener/firewall is changed.
        ollama.update(models_at(['http://127.0.0.1:11434',OLLAMA_URL]))
    return {'hostname':socket.gethostname().split('.')[0].lower(),
            'hardware':{'cpu':cpu,'ram_bytes':mem.get('MemTotal'),'ram_source':'OS-visible MemTotal, excluding reserved memory','storage':disks},
            'os':{'name':release.get('PRETTY_NAME'),'id':release.get('ID'),'version':release.get('VERSION_ID'),'kernel':os.uname().release},
            'power':{'suspend_to_ram':'mem' in read('/sys/power/state').split(),
                     'sleep_modes':read('/sys/power/mem_sleep') or None,
                     'wol':None,'wake_enabled_devices':[Path(p).parts[-4] for p in glob.glob('/sys/class/net/*/device/power/wakeup') if read(p)=='enabled']},
            'runtimes':{'executables':runtimes,'ollama':ollama,'proxmox':Path('/usr/bin/pveversion').exists()},
            'health':command(['systemctl','is-system-running']) or 'unknown',
            'metrics':{'cpu_busy_percent':busy,'load_averages':list(os.getloadavg()),'memory_available_bytes':mem.get('MemAvailable'),
                       'swap_used_bytes':mem.get('SwapTotal',0)-mem.get('SwapFree',0)}}
if __name__=='__main__':print(json.dumps(probe(),separators=(',',':')))
