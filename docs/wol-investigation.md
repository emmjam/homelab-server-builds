# HP Wake-on-LAN investigation — 2 November 2026

Status: **resolved**. The user confirmed HP/Dell long-sleep recovery fixed on
2 November 2026. The observations below are historical; the fix mechanism was
not supplied in this update and has not been independently re-tested here.

## Verified results

The HP is `ai-agent.lan`, Debian 13.7, with Intel I219-LM (`e1000e`) on
`eno1`, MAC `10:62:e5:0d:17:a4`. Current NIC settings report `Wake-on: g`,
sysfs wakeup is enabled, and `/etc/systemd/network/10-wol-ai-agent.link`
persistently selects `WakeOnLan=magic`. Suspend uses deep/S3.

[Wake execution 166](http://192.168.0.51:4440/project/HomeLab/execution/show/166)
sent its magic packet at 09:09:06 but failed hostname-based SSH verification.
Both the controller and laptop observed NXDOMAIN for the HP hostname.

The HP's previous boot journal shows:

- Suspend entry: 31 October, 17:06:41.
- Resume from S3: 2 November, 09:08:53; Ethernet link up at 09:08:56.
- No logged DHCP renewal between resume and shutdown. The last DHCP ACK was
  31 October, 16:54:49; the lease duration was one hour.
- Power-button press at 09:10:26 caused an orderly shutdown.
- Following boot, a new DHCP ACK at 09:11:00 restored `192.168.0.118` and
  hostname resolution.

The resume timestamp precedes execution 166's packet timestamp. These logs do
not establish which event woke the HP. They do establish that it had resumed
while the job was reporting failed SSH availability. Do not equate that job's
failure with proof that its packet failed to wake the hardware.

## Approved controlled test

The user explicitly approved a brief suspend-and-wake test:

- [Suspend 167](http://192.168.0.51:4440/project/HomeLab/execution/show/167):
  requested 09:12:31; SSH unavailability verified at 09:12:46.
- [Wake 168](http://192.168.0.51:4440/project/HomeLab/execution/show/168):
  packet sent 09:12:50; hostname-based SSH verified at 09:12:54.
- HP journal independently records suspend at 09:12:31 and resume at 09:12:50.

This proves short-suspend WOL and hostname-based SSH recovery. It does not
reproduce a sleep longer than the DHCP lease.

## Resolution

HP/Dell long-sleep recovery is fixed (user-confirmed 2 November 2026).
The earlier diagnosis is retained above as historical evidence. No further
long-sleep investigation is outstanding. Post-reboot persistence verification
remains a separate backlog item (RD-05).
