# Repository development instructions

Read `PROJECT_CONTEXT.md` for architecture, operational boundaries and standing
user directives before infrastructure work. Preserve unrelated working changes.
Use British English. Never commit secrets.

## Repository knowledge

The repository must support continued Rufus development without Codex prompt
storage. Keep completion evidence and reusable requirements in the relevant
technical documentation; code and Ansible define implementation/configuration.
Do not retain redundant prompt transcripts or duplicate maintained information.
Use links to authoritative documents instead of copying their contents.

## Testing and validation directive

During builds, run a check only when its output is required by a subsequent
step or to establish that a change affected another component. Use command exit
codes as success indicators; do not issue a second command merely to confirm the
first ran successfully. Put final end-to-end validation in one script and execute
it with one SSH call. Use Rundeck WOL to wake any machines needed. This directive
supersedes earlier instructions to run routine suites during intermediate builds.

Whenever directives change, immediately commit and push those changes, keeping
unrelated work out of the commit (standing user authorisation).

## Host availability / WOL directive

Some homelab compute nodes intentionally sleep or power down when idle and may
be unreachable during normal operation. Before diagnosing SSH, networking,
DNS, service configuration, authentication or similar connection failures to a
managed compute node:

1. Establish whether the target is currently awake and reachable.
2. If it supports Wake-on-LAN and is asleep/offline, treat that as a normal
   availability state rather than a configuration fault.
3. Wake it through the approved WOL mechanism where appropriate, then wait for
   network/SSH availability before continuing.
4. Begin configuration-level troubleshooting only once availability has been
   established. If waking cannot be verified, report availability as unresolved
   rather than assuming a configuration fault.

Do not modify working SSH/network configuration merely because a sleeping or
powered-down target is unreachable. Apply this principle to Rufus's eventual
worker-management and diagnostic logic: establish/wake/wait before diagnostics,
and distinguish unavailable workers from configuration failures.

The existing approved HP/Dell mechanism is the Rundeck **HomeLab - AI Host Power**
job (`7d9a3328-c8df-4e31-bbf6-49a6d9ce5a11`), with the allowlisted host and
`action=wake`. Read its verification result before continuing. A sent magic
packet alone does not prove the host is awake; failed hostname-based verification
alone does not prove hardware wake failed. Preserve these distinctions.

## Rufus Task 1 scope

Prioritise a working chat interface. Follow the agreed requirements; do not add
unsolicited features or redesign authentication, security, networking or
architecture. Use the simplest consistent implementation for unspecified details.
Ask only for genuine blockers or decisions materially affecting security or
architecture, not routine details or optional improvements.
