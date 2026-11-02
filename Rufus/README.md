# Rufus application

Rufus provides ordinary local-AI conversation and a supervised APT-cache repair
workflow. Model output cannot authorise infrastructure changes; deterministic
validation, exact one-use approval and independent Rundeck ACLs control execution.
Rufus receives no shell endpoint, SSH keys, sudo permissions or Proxmox credentials.

Browser access: [Rufus Web architecture and access instructions](../docs/rufus-web.md).
The separate web service runs on this same guest; the API remains loopback-only.

## Development reference

These documents contain the reusable requirements, implementation details and
completion evidence; no external prompt archive is required:

| Milestone | Authoritative technical documentation and completion record |
|---|---|
| AI1 — HP local inference | [Inference deployment, configuration and acceptance](../docs/ai-inference.md) |
| AI2 — supervised repair | [API contract, approval rules and repair acceptance](../docs/ai2-api.md) |
| AI3 — general conversation | [Dialogue processing, persistence, limits and acceptance](../docs/ai3.md) |

Code, operation catalogues, policies, Ansible and tests define current behaviour.
Read `../AGENTS.md` and `../PROJECT_CONTEXT.md` before infrastructure work; use
[BACKLOG.md](../BACKLOG.md) for remaining work. Historical acceptance results are
labelled by milestone and must not be mistaken for current configuration.

## Deployment and service

Ansible runs on Rundeck and installs modules under `/opt/rufus/app`, configuration
under `/opt/rufus/config`, SQLite under `/opt/rufus/data`, and `rufus.service`.
Use the existing `Ansible/playbooks/rufus.yml`. Application-only deployments use
`--tags rufus_application` against an existing provisioned `rufus` inventory host;
connect as Rundeck with the existing deployment key and sudo. The completed baseline
remains separate. This tag does not change existing SSH keys or sudo rules.

The service runs as `rufus`, starts at boot and restarts after failures. It uses
filesystem and device hardening. `NoNewPrivileges` is deliberately omitted to
permit future explicitly approved local sudo; no sudo permission is granted to
Rufus now. The service has no SSH or Proxmox credentials.

```bash
sudo systemctl start rufus
sudo systemctl stop rufus
sudo systemctl restart rufus
sudo systemctl status rufus
sudo journalctl -u rufus -n 100 --no-pager
```

Ansible also sets the default editor to Vim on a full provisioning run.

## Configuration and credentials

`/opt/rufus/config/config.json` configures Rundeck URL, 10-second HTTP timeout,
loopback port 8787, policy file, credential file and SQLite path. The API binds only
to `127.0.0.1`; run initial requests inside the container. The planned VS Code
Rufus client will later need controlled LAN access with authentication and an
approved transport/access policy. No LAN listener is enabled at this stage.
Every endpoint requires a bearer API token.

The ignored laptop `CRAP/secrets.txt` and controller `/tmp/secrets.txt` hold:

- `RUFUS_RUNDECK_TOKEN`: a dedicated Rundeck token for user `rufus`, role `rufus-api`.
- `RUFUS_API_TOKEN`: separate generated bearer credential for calling Rufus.

Ansible copies **only these two entries** to `/opt/rufus/config/secrets.txt`,
root-owned and readable by the service group (0640). It never copies the source
file or its SSH keys into Rufus. Values are parsed literally, never sourced or
executed, and secret deployment tasks suppress output. Existing Git and SSH
credentials remain unchanged. Do not put credentials on command lines or in Git.

The current dedicated Rundeck token expires **1 November 2027 at 19:16:07 UTC**.
Rotate it before then using Rundeck token management; update the temporary secret
source and rerun the application deployment. Revocation and 401/403 errors are
reported as integration failures. No automatic token renewal is implemented.

The managed `Ansible/playbooks/rundeck.yml` installs
`Rundeck/policies/rufus.aclpolicy` as a system ACL and sets
`rundeck.api.tokens.duration.max=1y`. The exact current job grants and node permissions are defined in
`Rundeck/policies/rufus.aclpolicy`; the API allow-list is `Rufus/policy.json`.
It grants no ad-hoc commands, other jobs, job editing or key storage. The initial
token is issued with **only** `rufus-api`, never the admin role.

## API

All responses are JSON. Supply `Authorization: Bearer <RUFUS_API_TOKEN>`.

| Method | Path | Behaviour |
|---|---|---|
| GET | `/health` | Local service liveness |
| GET | `/jobs` | Discover only approved jobs and their explicit option policy; checks Rundeck connectivity |
| POST | `/executions` | Validate operation/options, submit once, persist execution ID; HTTP 202 |
| GET | `/executions/ID` | Retrieve state and last 100 output lines for a Rufus-recorded execution |
| GET | `/executions/ID?wait=30` | Poll up to 30 seconds, then return terminal or current state |

The original `health-check` and production APT-cache operations in `policy.json`
accept **no options**. Disposable fixture operations were retired after acceptance. Restart operations are blocked
on direct `/executions` calls and require the conversational approval endpoint. Policy entries
can define named string options with `required` and full-match `pattern` fields;
unknown options, invalid types and strings over 256 characters are rejected.
Adding an operation requires deliberate Git policy and Rundeck ACL changes.
Arbitrary job UUIDs and unrecorded execution IDs are rejected.

Request body:

```json
{"operation":"health-check","options":{}}
```

Example request, using a credential already loaded into a local environment:

```python
import json, os, urllib.request
request = urllib.request.Request('http://127.0.0.1:8787/executions',
    data=json.dumps({'operation': 'health-check', 'options': {}}).encode(),
    headers={'Authorization': 'Bearer ' + os.environ['RUFUS_API_TOKEN'],
             'Content-Type': 'application/json'})
with urllib.request.urlopen(request, timeout=15) as response:
    print(json.load(response))
```

Example successful monitored result (illustrative ID/output):

```json
{"status":"succeeded","rundeck_status":"succeeded","execution_id":150,
 "operation":"health-check",
 "job":{"id":"6e0b2f6c-aaa0-4031-ba96-73c86164cb43","name":"Rundeck-Health-Check"},
 "parameters":{},"output":[{"message":"rundeck","level":"INFO","step":"1","node":"localhost"}],
 "failure":null,"monitor_timeout":false}
```

Example failed monitored result (illustrative, covered by mocks):

```json
{"status":"failed","rundeck_status":"failed","execution_id":151,
 "operation":"health-check",
 "job":{"id":"6e0b2f6c-aaa0-4031-ba96-73c86164cb43","name":"Rundeck-Health-Check"},
 "parameters":{},"output":[{"message":"Node execution failed","level":"ERROR","step":"1","node":"localhost"}],
 "failure":"Rundeck execution ended with status failed","monitor_timeout":false}
```

Initial submission reports `queued`; monitoring reports Rundeck's actual state.
A poll deadline leaves execution running and sets `monitor_timeout`; it does not
cancel the job. 504 means Rundeck was unreachable or timed out. 502 means an
upstream authentication, HTTP or response-validation failure. 400/403/404 identify
invalid requests, policy rejection or unknown execution. Output is bounded to
100 lines and 1 MiB per Rundeck response; journald records service events, not
headers, tokens or request parameters. Execution state persists across restarts.
There is no cancellation endpoint. POST is never retried automatically: after an
ambiguous network or persistence failure, inspect Rundeck before submitting again.

## Tests

Run `python3 scripts/validate.py` from the repository root. It retains detailed
logs locally and returns compact PASS/FAIL stage summaries.

Tests use isolated local HTTP mock servers, temporary SQLite databases and dummy
credentials. They cover connection/authentication, HTTP bearer checks, approved
and unapproved operations, parameter validation, success/failure, polling deadline,
network failures, malformed output/responses and execution ownership/persistence.
See the acceptance record below for real results.

Rundeck endpoints and ACL syntax follow the official
[API reference](https://docs.rundeck.com/docs/api/) and
[authorization reference](https://docs.rundeck.com/docs/administration/security/authorization.html).


## Real acceptance record — 1 November 2026

- Current template: LXC 9100. New Rufus: CT 111, hostname `rufus`, DHCP
  `192.168.0.52`, 2 cores, 2 GB RAM, 8 GB disk. Creation
  [150](http://192.168.0.51:4440/project/HomeLab/execution/show/150) succeeded.
  The earlier experimental Rufus is absent from the live inventory; none was
  deleted as part of this application acceptance test.
- Full Rufus provisioning: `ok=23 changed=17 unreachable=0 failed=0 skipped=7`.
  Local Ollama/model installation was skipped, retaining the separate inference plan.
  Application credential deployment: `ok=8 changed=2 unreachable=0 failed=0`.
- Managed token limit and restricted ACL applied successfully; Rundeck restarted
  and its API returned. Identity `rufus` has only role `rufus-api`.
  The replacement token expires 1 November 2027 at 19:16:07 UTC. The superseded
  token, previously expiring 1 December 2026, was revoked after verification.
  Controller and ignored laptop secret entries were synchronised without changing
  either source file's ownership or permissions. No secret values are recorded here.
- Real health-check execution
  [157](http://192.168.0.51:4440/project/HomeLab/execution/show/157) succeeded
  through Rufus: approved discovery, submission, ID tracking, polling and output
  retrieval all passed. Output included `rundeck`, Debian version, uptime and disk
  usage. The recorded result remained available after restarting Rufus.
- Invalid bearer authentication returned 401. Invalid parameters returned 400.
  An unapproved Rufus operation returned 403. The dedicated Rundeck identity
  independently rejected an unapproved VM-deletion job run with 403.
- Service is enabled and active as `rufus`; `ProtectSystem=strict`,
  `PrivateTmp=yes`, `NoNewPrivileges=no`. Listener is only `127.0.0.1:8787`.
  Rufus belongs only to its own group; no sudo was granted. Rundeck's existing
  `NOPASSWD: ALL` inside the guest was verified unchanged.
- Complete automated suite after the real test: **55 tests passed**, covering
  Rufus, secret parsing, LXC lifecycle and VM relocation. Failure reporting and
  unavailable/malformed upstream responses are verified by mocks, not induced
  production failures.

The first operational milestone is complete. LAN transport/VS Code integration,
OpenBao and further automation expansion have not been started by this test.
