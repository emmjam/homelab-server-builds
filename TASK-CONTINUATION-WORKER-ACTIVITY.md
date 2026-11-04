# Rufus worker activity and individual cancellation — active task

## Complete actionable requirements
Extend the Rufus VS Code working indicator into a live activity/control panel for
the entire managed pool: TNAS/Proxmox coordination, HP primary inference, Dell
secondary inference/general work, two Mac Pros long-running work, future workers.
For every machine show name, actual online/offline/unknown freshness, working vs
idle, assigned task and request/job identity, CPU/RAM/GPU where measured, measurable
progress and task elapsed time. Distinguish available idle, busy, waking/starting,
inference, background work, cancelling, failed/unreachable; online alone is not busy.

Stop beside active workers must cancel the selected assignment's actual execution,
leave unrelated assignments running, support whole-parent cancellation when asked,
and independently confirm stopped work. Never equate a hidden panel/disconnected
HTTP client with confirmed cancellation. No shutdown/suspend without explicit request.

Every job and worker assignment needs a unique ID and durable relationships to
parent requests, jobs and worker tasks. Route cancellation to the correct execution;
prevent cancelled retries/rescheduling/further stages, preserve other completed
results and report partial completion. Cancelling one contributor must not kill others.

Reuse existing worker discovery/capabilities and Rufus backend architecture. Backend
owns discovery, allocation, monitoring, cancellation/resource scheduling. The VS Code
extension is only authenticated API presentation/control. Inspect missing backend
capabilities and implement actual orchestration/API support; no simulated frontend
activity/cancellation. Test concurrent workers, assignment/parent cancellation,
isolation, worker failure/disconnect, partial completion, no cancelled rescheduling
and truthful status. Document lifecycle with Mermaid. Preserve auth/approval/security.

## Constraints and existing state
Read AGENTS.md and PROJECT_CONTEXT.md. Preserve all unrelated dirty work and the
separate deferred VS Code continuation. Existing no-commit/no-push instruction
remains; no Git mutation unless user authorises. No arbitrary shell/job IDs from
clients/model; no worker SSH keys in Rufus, no inferred approvals, no power actions
merely for visibility or cancellation, no production faults for tests. Record nullable
progress/resources and source freshness rather than invent values.

## Findings / progress
Initial inspection: `Rufus/nodes.py` exposes read-only discovery snapshots. Existing
worker power jobs are separate. PROJECT_CONTEXT.md explicitly states distributed
allocation/scheduling are not implemented; capability reports are not assignments.
Current conversations use a local ThreadPoolExecutor and direct HP Ollama HTTP;
background execution goes through an approved fixed Rundeck catalogue. There is
no inspected durable per-worker task registry or cancellation implementation yet.
No implementation changes or tests performed in this new task yet.

## Ordered next work
1. Inspect discovery schema, request/workflow lifecycle, Rundeck/API ACLs, client
   polling and deployment; establish actual execution/cancellation possibilities.
2. Resolve supported task types/execution transport where not defined, without
   inventing application workloads or broadening security silently.
3. Implement backend durable request/job/assignment state, real executor integration,
   cancellation/verification/restart/failure fencing and resource/capability admission.
4. Add existing-auth API/Web routes and thin VS Code panel/individual/parent controls.
5. Add focused concurrency/cancellation/failure/partial-result tests and diagrams.
6. Run relevant checks and isolated real execution acceptance; deployment/live changes
   only through existing managed automation. Update docs/BACKLOG/evidence/checkpoint.
7. Retain this file until the entire agreed task is tested and verified.

## Exact next action
Read actual execution/discovery/client code; identify what can really be stopped
and how confirmation is obtained. Do not represent current discovery-only nodes as
assigned workers or cancellation-capable until that support exists.
