# Minimal Rufus application

Deterministic request → approved-job policy → Rundeck → execution status/output.
No LLM, shell endpoint, worker control or infrastructure credentials. Python standard
library only, using the existing `/opt/rufus/venv` and directories. `app.py` owns
HTTP routing, validation and persistent SQLite execution ownership; `rundeck.py`
handles the bounded HTTP integration; `config.py` loads configuration and literal
credentials. `policy.json` contains the approved operations.

## Deployment and service

Ansible runs on Rundeck and installs modules under `/opt/rufus/app`, configuration
under `/opt/rufus/config`, SQLite under `/opt/rufus/data`, and `rufus.service`.
Use the existing `Ansible/playbooks/rufus.yml`. Application-only deployments use
`--tags rufus_application` against an existing provisioned `rufus` inventory host;
connect as Ian with the existing administrator key and sudo. The completed baseline
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

The initial dedicated Rundeck token expires **1 December 2026 at 15:32:50 UTC**.
Rotate it before then using Rundeck token management; update the temporary secret
source and rerun the application deployment. Revocation and 401/403 errors are
reported as integration failures. No automatic token renewal is implemented.

Install the Git-managed `Rundeck/policies/rufus.aclpolicy` as a system ACL through
Rundeck's system ACL API. It grants project visibility, read/run of health check
UUID `6e0b2f6c-aaa0-4031-ba96-73c86164cb43`, and node read/run needed by that job.
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

Only `health-check` is initially approved; it accepts **no options**. Policy entries
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

```bash
python3 -m unittest discover -s tests/rufus -v
python3 -m unittest discover -s tests/rundeck -v
```

Tests use isolated local HTTP mock servers, temporary SQLite databases and dummy
credentials. They cover connection/authentication, HTTP bearer checks, approved
and unapproved operations, parameter validation, success/failure, polling deadline,
network failures, malformed output/responses and execution ownership/persistence.
See the acceptance record below for real results.

Rundeck endpoints and ACL syntax follow the official
[API reference](https://docs.rundeck.com/docs/api/) and
[authorization reference](https://docs.rundeck.com/docs/administration/security/authorization.html).
