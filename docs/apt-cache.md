# APT cache

Verified 1 November 2026: VM **112**, hostname **apt-cache**, DHCP address
`192.168.0.116`, 2 cores, 2 GB RAM and **64 GB total disk**. This is a VM;
future conversion to LXC with TNAS-backed storage is backlog item CACHE-01.
Old Apt-Cache VMs 112 and 9001 were deleted by Rundeck executions 152 and 153.
The replacement was created by execution 156 from Debian VM template 9000.

Apply `Ansible/playbooks/apt-cache.yml` from Rundeck using its established
`rundeck` SSH identity, an inventory group named `apt_cache`, and `become: true`.
The cache server itself uses direct repositories so it can bootstrap independently.

Clients use `Acquire::http::Proxy "http://apt-cache:3142";` and
`Acquire::https::Proxy "DIRECT";`. The hostname resolved successfully from the
laptop and Rundeck. Two real Debian Release downloads through that proxy returned
HTTP 200 with matching SHA-256 digests. Template sources and their validators use
this hostname; existing guests and already-built templates are not rewritten by
source changes.

Debian's packaged `/etc/cron.daily/apt-cacher-ng` runs expiration via cron.
Ansible enables cron and sets `ExThreshold: 4` (days); a manual expiration run
completed successfully. This is expired-package cleanup, not a strict disk quota.

`apt-cache-disk-monitor.timer` runs hourly and five minutes after boot. The
monitor logs WARNING at 80% filesystem usage and CRITICAL at 90%, returning
nonzero for critical usage. Output goes to journald; no external notification
service is configured. Check it with:

```bash
systemctl status apt-cache-disk-monitor.timer
journalctl -u apt-cache-disk-monitor.service --no-pager -n 10
sudo /usr/local/sbin/apt-cache-disk-monitor
```

The initial check reported 2% used and 58 GiB free. The playbook verifies port
3142 and the installed expiration job. It installs no Proxmox credentials or
Rundeck administrator token on the cache VM.
