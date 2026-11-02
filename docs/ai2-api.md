# AI2 conversational API contract

Contract drafted before implementation, 2 November 2026. User approved the
APT-cache target, listed read-only diagnostics and an isolated disposable fixture.
Every repair still requires an exact action approval. Publication and deployment
were separately explicitly approved.

All endpoints remain on Rufus loopback (`127.0.0.1:8787`) and require the existing
bearer credential. Existing `/health`, `/jobs`, `/executions` and execution-status
routes remain supported. Future LAN/VS Code transport is a separate task.

## Conversations and progress

| Method | Route | Request/result |
|---|---|---|
| POST | `/conversations` | Empty object creates a durable conversation; returns its ID |
| GET | `/conversations/ID` | Messages, timestamped progress/evidence and linked actions |
| POST | `/conversations/ID/messages` | `request_id` and `content`; persist once and return HTTP 202 with message ID/status |
| GET | `/actions/ID` | Exact immutable proposal, approval state, execution, verification and final outcome |
| POST | `/actions/ID/decision` | `conversation_id`, `proposal_hash`, and `decision` (`approve` or `reject`) |

IDs are opaque server-generated UUIDs. Message request IDs are client-generated
UUIDs, unique within a conversation. Retrying the same ID/content returns the
original message; changing its content returns conflict. A conversation accepts
one active request at a time. Message text and model/diagnostic context are bounded.
Polling provides persisted progress and final results without keeping an HTTP
request open for model generation or Rundeck execution. No streaming framework is
needed for this milestone.

## Proposal and approval

An action is persisted before it is returned for approval. It includes:

- Conversation and request identity.
- Stable operation, permitted target, exact options and Rundeck job UUID.
- Exact change, expected effect, material risks and recovery limitations.
- Diagnostic evidence/execution IDs and timestamps.
- Expiry and a digest binding all immutable execution/approval fields.
- Status, repair execution ID, independent verification ID and final outcome.

Approval is accepted only for that action, conversation, hash and unexpired state.
The state transition is atomic and one-use. Rejection, expiry, replay, changed
parameters or changed catalogue policy prevents submission. Model output, job
logs and repository text never count as approval. Direct `/executions` requests
must reject every operation marked as requiring approval, preventing an alternate
route around the conversation state machine.

Persist a submission reservation before each external POST. Never retry an
ambiguous POST. If submission outcome cannot be recorded or is unknown after a
restart, report that uncertainty and require manual reconciliation. Resume
monitoring known execution IDs; never automatically resubmit a repair. Pending
approvals and active executions survive restart. Interrupted inference may be
reported as interrupted rather than regenerated automatically.

A successful repair job produces an executed state, not a recovered claim.
Independent verification must complete and its evidence must establish the
original fault is resolved. Outcomes distinguish `recovered`, `still_failing`,
`unable_to_verify`, `failed`, `submission_unknown`, `rejected` and `expired`.

## Trust and operation catalogue

The model interprets bounded user/evidence context and proposes structured data.
Application validation and independent Rundeck ACLs enforce operations, targets,
parameter names/types/ranges and approval policy. No arbitrary UUID, shell command,
infrastructure SSH credential, sudo permission or dynamic tool authorisation is
accepted. Catalogue changes are deliberate Git/Ansible/Rundeck changes.

Every catalogue entry must specify classification, permitted target and options,
exact job UUID, whether diagnostics are pre-approved, expected outcome, verification
operation and timeout/retry policy. Mutations have no automatic retries. Diagnostic
output is untrusted data, bounded and redacted before persistence/model context.
Secrets and upstream exception bodies must not appear in API errors or model input.

## Approved first workflow

Target: `apt-cache.lan`, service `apt-cacher-ng`. Read-only diagnostics: host
availability, service state, cache-filesystem free space and HTTP response.
Repair: restart only that existing service, after explicit approval. Verification
uses a separately invoked read-only operation and HTTP evidence. Inspect host
availability before diagnosing configuration; do not change SSH/network settings
because a host is unavailable.

The production cache is currently active. Real failure acceptance therefore needs
an agreed isolated disposable fixture, never an artificial production outage.
The fixture must use distinct fixed operation/target identities and must not
silently redirect a production proposal to a test system.

## Implementation status — 2 November 2026

The conversational API, inference orchestration, persistent approvals, fixed
operation catalogue and independent restricted ACL are deployed. Latest deployment:
[183](http://192.168.0.51:4440/project/HomeLab/execution/show/183), source `3277356`.
HP was awakened through Rundeck execution 175. No production service was changed.

Final scripted validation passed all six groups; controller logs:
`/tmp/homelab-validation-51fbsm0p`. The controller required the missing `jq`
dependency and validation runs as the checkout owner, `rundeck`.
Live checks passed Rufus operation denial, direct mutation bypass denial and
independent Rundeck denial. Fixture diagnostic execution 184 confirmed a stopped
fixture and failed HTTP probe with sufficient disk space. Rejecting action
`25a1066a-27ad-4bb1-ac88-d14fdaecec07` created no repair execution.

Real inference exposed target and intent classification errors. Explicit fixture
requests now constrain the validated target schema; explicit repair/restart
requests permit proposal, clarification or unsupported responses. Model responses
still cannot approve or execute an operation. A regression check rejects model
selection of production for an explicit fixture request.

Acceptance remains incomplete until the user approves a concrete fresh action,
the restricted repair runs and independent verification establishes recovery.

## Deployment permissions

Rundeck's service identity can administer the existing remote guests, but has no
passwordless sudo on the controller itself. Preserve that boundary. After Git
checkout/job sync, install the versioned restricted ACL using the existing Ian
administrative context on Rundeck:

```bash
cd /opt/homelab-server-builds
sudo env ANSIBLE_ROLES_PATH="$PWD/Ansible/roles" ansible-playbook \
  -i Ansible/inventory/ai2.ini --limit rundeck_controller \
  --tags ai2_configuration Ansible/playbooks/ai2.yml
```

Then **HomeLab - Deploy Rufus AI2** (`34053c09-7207-4ac4-a89f-24fd1c595976`)
refreshes Git and deploys only the Rufus application and APT-cache fixture through
Ansible. It cannot approve or execute a repair. No controller sudo grants are
added. The catalogue and `policy.json` record every exact permitted operation,
job UUID, target, empty option schema, classification, approval policy and timeout.
The existing health check plus six fixed diagnostic/restart/verification job
UUIDs are the only jobs permitted to the `rufus-api` role.


## Real acceptance client

`scripts/ai2-acceptance.py` is deployed under `/opt/rufus/app`. Run as the
unprivileged service user. Its `propose`, `reject`, `status` and `boundaries`
stages never approve repairs. `approve` requires explicit action ID and hash
arguments supplied only after the user approves that concrete proposal. State
persists in `/opt/rufus/data/ai2-acceptance.json`; no credentials are printed.
The fixture is a separate apt-cacher-ng instance on `apt-cache.lan`, loopback
port 13142, with separate configuration, cache, logs and systemd unit; it is
disabled at boot. Production port 3142 and its service remain untouched by
fixture operations. Both targets have distinct stable operations and job UUIDs.
