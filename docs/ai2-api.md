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

- HP availability was established through trusted SSH before diagnostics.
- The existing AI1 acceptance stage was rerun only for the Rufus host: real HP
  inference and safe unavailable-backend reporting passed (`ok=1 changed=0 failed=0`).
  Controller log: `/tmp/ai2-prerequisite-pFqyPp.log`.
- Production `apt-cache.lan` is reachable, `apt-cacher-ng` is active and its cache
  filesystem has 59 GiB available. No fault was introduced or service restarted.
- `Rufus/conversations.py` implements target-independent SQLite conversation,
  message/event and immutable action storage with atomic one-use approval and
  submission reservation. It performs no model, shell, HTTP or infrastructure
  execution. It is not yet wired into the live application or deployed.
- Eight focused persistence/approval tests cover rejection, expiry (including
  before submission), exact hashes/conversations, modified proposals, concurrent
  decisions, duplicate requests and restart uncertainty without resubmission.
- Message/event callers must redact sensitive data before persistence. Redaction,
  operation-catalogue validation, HTTP routes, inference orchestration, execution
  monitoring and full acceptance remain implementation work after target agreement.
- No new Rundeck jobs/ACLs, Rufus API routes or repair operations are live.


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
