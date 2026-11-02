# Rufus Web

A separate browser client, hosted on the **existing Rufus LXC on TNAS**.
No additional VM, LXC or Docker container. Python standard library and static
HTML/CSS/JavaScript only. `rufus-web.service` runs as unprivileged `rufus-web`;
`rufus.service` retains its existing identity and approval/Rundeck boundary.

## Access architecture

Authorised browser → loopback SSH forward → Rufus Web (`127.0.0.1:8788`) →
Rufus API (`127.0.0.1:8787`). Neither listener is exposed to the LAN.

The API bearer credential is in `/opt/rufus-web/config/api-token`, root-owned,
readable only by the web service group. It never enters browser code, URLs,
storage or cookies. Web has no Rundeck credentials, SSH keys or sudo grant and
cannot read Rufus's credential file. It forwards only conversation and action
routes, never arbitrary URLs, jobs or `/executions`.

An SSH-authorised administrator issues a 3-minute single-use login code. Login
exchanges it for an 8-hour HttpOnly, SameSite=Strict session cookie. Only digests
are stored in the separate web SQLite database; sessions survive web restarts.
POST requests require an exact same-origin Origin header; Host validation blocks
DNS rebinding. No CORS, external scripts, HTML rendering of model output or browser
storage. Responses are no-store, frame-blocked and covered by a restrictive CSP.
HTTP cookies deliberately omit Secure for loopback HTTP over SSH; a future HTTPS
gateway must use Secure cookies and explicitly configured trusted origins.

All authorised sessions currently act as the same Rufus operator and can view the
shared conversation archive. This is not a multi-tenant authorisation system.
Client hardware/IP is not allowlisted. Other authorised computers can use their
own SSH identity and chosen local port. Future mobile access needs an approved
VPN/HTTPS access gateway; a VS Code client needs its own secured access path.
Neither is implemented here, and neither requires moving the API off loopback.

## Open from any authorised SSH client

From the repository, run:

```bash
python3 scripts/rufus-web.py --target YOUR_SSH_USER@rufus.lan
```

Use the existing SSH administrator credentials. The command requests a one-use
code through `sudo -u rufus-web` (your existing sudo password may be required),
prints it in the terminal, starts a local-only SSH forward and opens
`http://127.0.0.1:8877`. Paste the code into the sign-in form. Leave the command
running; Ctrl+C closes the tunnel. Sign out revokes the browser session.

The optional helper is not a server dependency. Manual equivalent:

```bash
ssh -t YOUR_SSH_USER@rufus.lan 'sudo -u rufus-web python3 /opt/rufus-web/app/web.py --login-code'
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8877:127.0.0.1:8788 YOUR_SSH_USER@rufus.lan
```

Existing verified host keys are required. Never bypass a host-key mismatch.
Helper options `--known-hosts`, `--host-key-alias`, `--ssh-config`, `--local-port`
and `--no-browser` accommodate each client's established SSH setup. A stale key
for an older Rufus container must be reconciled against a trusted administrative
source; the helper never edits known_hosts or disables checking.

## Behaviour and maintained configuration

New and previous conversations, follow-up messages, assistant replies, progress,
errors and exact-action approval/rejection use the existing API. The sole API
addition is authenticated `GET /conversations`: the most recent 100 conversations,
with a title from their first user message. Full conversation history remains in
Rufus SQLite. No browser-side archive or bearer token is needed.

Approval cards display the immutable operation, target, parameters, job UUID,
proposal hash, expiry, expected effect and risks. Both decision buttons require
confirmation and submit the original action/conversation/hash. Changed, expired,
replayed or rejected actions retain AI2's deterministic restrictions.

`Ansible/playbooks/rufus-web.yml` owns the account, root-owned application/static
files, protected directories, API-only secret and service. API URL, port and
allowed web hosts are centrally configured. The generic laptop helper is optional.
Deploy with **HomeLab - Deploy and Validate Rufus Web**; the final script runs
existing automated suites, deploys on the current guest, verifies loopback/account
isolation and reruns the existing AI3 conversation/restart acceptance. AI2's retired
fixture is not recreated: its approval/rejection and independent verification
paths run with mocks in the existing regression suite.

Status: implementation awaiting final acceptance. Browser interaction requires
an available browser connection; HTTP acceptance is recorded separately from
visual/browser verification.
