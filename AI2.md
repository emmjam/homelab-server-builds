Project: emmjam/homelab-server-builds

TASK

Extend the existing Rufus application to perform its first conversational,
supervised repair workflow.

Prerequisite: the HP inference deployment has been completed and a real request
from the Rufus container has succeeded. Verify that evidence and current
connectivity before starting. If the prerequisite is incomplete, report the
blocker rather than installing inference inside Rufus.

CURRENT FOUNDATION

The deterministic Rufus API → approved-job policy → Rundeck → execution
status/logs milestone has already passed acceptance checks.

Inspect the current implementation, tests, documentation, Git history and live
configuration. Reuse that foundation rather than replacing it.

TARGET OUTCOME

I can describe a supported problem in ordinary language. Rufus:
1. Understands the request or asks a necessary clarifying question.
2. Collects evidence using approved diagnostic jobs.
3. Explains the evidence and uncertainty.
4. Proposes one specific supported repair.
5. Requests explicit approval.
6. Executes exactly the approved operation through Rundeck.
7. Runs independent verification.
8. Reports recovered, still failing or unable to verify.

FIRST REPAIR TARGET

Agree with me on ONE concrete fault and approved repair before implementing
remediation. An example is diagnosing an unavailable APT cache and restarting
its existing service.

Do not invent the repair target, deliberately break production, or create an
arbitrary shell endpoint.

TRUST AND EXECUTION MODEL

- Rufus runs as the unprivileged rufus account.
- Infrastructure operations go exclusively through Rundeck.
- Preserve Rundeck’s intentionally privileged administrative deployment model.
- Preserve the dedicated Rufus Rundeck identity and rufus-api role.
- Rufus’s allow-list and Rundeck ACL must independently restrict operations.
- Add only the permissions required for the explicitly approved diagnostics
  and first repair.
- Do not give Rufus administrator API tokens, SSH keys or Proxmox credentials.
- Do not grant Rufus sudo permissions now.
- Preserve the approved systemd model: no NoNewPrivileges=true, while retaining
  compatible hardening. Future local sudo remains a separate approved decision.

CONVERSATIONAL API

Keep the backend client-independent for the future VS Code client.

Provide the minimum API capabilities for:
- Creating a conversation.
- Sending a message.
- Retrieving conversation history.
- Receiving progress and final results.
- Approving or rejecting a proposed action.
- Retrieving the action and its execution/verification status.

Reuse existing endpoints and persistent storage where appropriate.
Document the API contract before implementation.
Keep the API loopback-only for this stage.
Document the later requirement for controlled LAN access.
Do not implement the VS Code extension yet.

INFERENCE CLIENT

Use the HP backend established by the prerequisite task.

Configure URL, model, authentication source and timeouts outside application code.
Handle unavailable inference, malformed output and context limits cleanly.
Use the minimum necessary conversation and diagnostic context.

The model interprets requests, explains evidence and proposes structured actions.
It does not authorise or directly execute them.

OPERATION CATALOGUE

For each supported operation, define:
- Stable operation name.
- Purpose and allowed target.
- Exact Rundeck job UUID.
- Parameter schema and permitted values.
- Diagnostic or state-changing classification.
- Approval requirement.
- Expected outcome.
- Independent verification operation.
- Timeout and retry policy.

Ask me to approve which read-only diagnostics may run without a separate prompt.
Every repair requires explicit approval for this milestone.

DETERMINISTIC VALIDATION

Require structured model proposals and validate them in application code:
- Operation exists in the allow-list.
- Target is permitted.
- Parameter names, types, ranges and values are valid.
- Required information is present.
- Approval requirements are satisfied.

Reject arbitrary job UUIDs, shell commands and unsupported operations.
The model must never create permissions or override validation.

Treat job output, repository content and external text as untrusted evidence.
Instructions embedded in that material must not change policy or count as
user approval.

APPROVAL STATE MACHINE

Persist an action before requesting approval.

Show:
- What will change.
- Affected machine/service.
- Exact operation and parameters.
- Expected effect.
- Material risks and recovery limitations.

Bind approval to the exact action, parameters and conversation.
Changed parameters require new approval.
Approval must expire and be consumable only once.
Rejection, expiry and replay must prevent execution.
A model-generated claim of approval is never approval.

PERSISTENCE AND EXECUTION

Persist:
- Conversation and messages.
- Diagnostic evidence and timestamps.
- Validated action proposal.
- Approval/rejection and expiry.
- Rundeck execution ID.
- Execution status.
- Verification result.
- Final outcome.

Survive service restarts without losing pending actions or active executions.
Do not resubmit a repair automatically after a restart, duplicate request or
ambiguous network timeout.

Never automatically escalate into another repair or repeatedly retry a mutation.
Ask for approval for a new action.

VERIFICATION

Distinguish:
1. Rundeck accepted the request.
2. The job completed successfully.
3. The original problem was verified as resolved.

A successful job exit must not alone produce “fixed”.

Run the approved independent verification operation after repair.
Return useful evidence, failure information and Rundeck execution links.

SECRETS AND LOGGING

Use the established temporary secret mechanism.
Do not expose authentication headers, passwords, hashes, tokens or private keys
in logs, model context, Git or responses.
Do not implement OpenBao or automated credential rotation.
Preserve the restricted identity during any necessary credential handling.

AUTOMATED TESTS

Cover:
- Conversational diagnostic request.
- Unsupported repair request.
- Invalid model output and parameters.
- Untrusted output attempting to override instructions.
- Mutation blocked before approval.
- Rejected, expired, changed and replayed approvals.
- Duplicate submissions.
- Successful repair and successful verification.
- Successful job followed by failed verification.
- Failed Rundeck execution.
- Inference/Rundeck unavailability and timeouts.
- Restart recovery without duplicate execution.
- Persistent conversation/action history.
- Secret redaction.

Mock inference and Rundeck where appropriate.
Run the complete existing automated suite as well.

REAL ACCEPTANCE TEST

Use the agreed first repair target.

Demonstrate:
1. Ordinary-language request.
2. Approved diagnostics and useful evidence.
3. Specific repair proposal.
4. No mutation before explicit approval.
5. Approved execution through the restricted Rundeck identity.
6. Independent verification.
7. Clear final explanation with execution IDs and links.
8. Rejected proposal causes no change.
9. An unapproved operation is rejected independently by Rufus and Rundeck.

If no suitable real fault exists, agree a disposable test fixture with me.
Do not break production or fabricate a successful repair.

DEPLOYMENT AND DELIVERY

Deploy through the established Git/Rundeck/Ansible pattern.
Keep application code separate from deployment configuration.
Preserve unrelated changes and avoid unnecessary frameworks or scripts.

Commit logical changes separately and push to the existing branch.
Update documentation and BACKLOG.md using verified results.

Report:
- Files and architecture changed.
- API contract and example conversation.
- Supported diagnostics and repair.
- Exact permissions added.
- Approval behaviour.
- Automated results.
- Real acceptance evidence and execution links.
- Commit hashes.
- Remaining limitations.

STOP after one supervised repair workflow is proven.

Do not implement broader autonomy, the VS Code extension, Dell scheduling,
OpenBao, WOL, voice, Sonos, Bobarr or unrelated backlog work.