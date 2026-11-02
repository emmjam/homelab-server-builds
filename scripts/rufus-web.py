#!/usr/bin/env python3
"""Optional generic SSH launcher; no bearer credentials or client-specific identity."""
import argparse
import subprocess
import time
import webbrowser

parser=argparse.ArgumentParser(description='Open Rufus Web through an authorised SSH connection')
parser.add_argument('--target',default='rufus.lan',help='Authorised SSH user@host (standard SSH configuration applies)')
parser.add_argument('--local-port',type=int,default=8877)
parser.add_argument('--ssh-config');parser.add_argument('--known-hosts');parser.add_argument('--host-key-alias')
parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
if not 1024<=args.local_port<=65535:parser.error('Use an unprivileged local port')
ssh=['ssh']
if args.ssh_config:ssh+=['-F',args.ssh_config]
if args.known_hosts:ssh+=['-o','UserKnownHostsFile='+args.known_hosts]
if args.host_key_alias:ssh+=['-o','HostKeyAlias='+args.host_key_alias]
ssh+=['-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes']
# Issuance requires the user's existing SSH/admin authorisation; it grants no
# new sudo permission and never retrieves the API bearer credential.
subprocess.run(ssh+['-t',args.target,'sudo -u rufus-web /usr/bin/python3 /opt/rufus-web/app/web.py --login-code'],check=True)
print('Paste the code into http://127.0.0.1:'+str(args.local_port)+' (expires in 3 minutes).',flush=True)
tunnel=subprocess.Popen(ssh+['-N','-L',f'127.0.0.1:{args.local_port}:127.0.0.1:8788',args.target])
try:
    time.sleep(1)
    if tunnel.poll() is not None:raise SystemExit(tunnel.returncode)
    if not args.no_browser:webbrowser.open('http://127.0.0.1:'+str(args.local_port))
    print('Tunnel active. Press Ctrl+C to disconnect.',flush=True)
    tunnel.wait()
except KeyboardInterrupt:pass
finally:tunnel.terminate();tunnel.wait()
