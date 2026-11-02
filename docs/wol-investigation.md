# HP Wake-on-LAN investigation — 2 November 2026

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

## Remaining diagnosis

The evidence points towards expired DHCP/DNS state after long sleep rather
than missing magic-packet enablement. No DHCP-resume fix has yet been applied.
Before choosing a fix, capture a controlled long-sleep or disposable-client
reproduction of lease expiry and inspect the existing ifupdown/dhclient owner.
Any renewal must reuse that owner rather than start a competing DHCP client.
Retain hostnames for normal SSH and report DNS recovery separately from wake.
Do not change BIOS, WOL settings or network configuration on speculation.
