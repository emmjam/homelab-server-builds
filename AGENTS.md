# Repository development instructions

Read `PROJECT_CONTEXT.md` for architecture, operational boundaries and standing
user directives before infrastructure work. Preserve unrelated working changes.
Use British English. Never commit secrets.

## Testing and validation directive

Known, repeatable checks → automated test suite in the pipeline.
Unexpected troubleshooting → AI-directed one-off checks.

The objective is to minimise unnecessary Codex token/usage consumption.
When a check is deterministic and expected to be repeated, particularly build,
provisioning, deployment, configuration and post-build validation, implement it
in the relevant automated suite, build playbook or pipeline instead of having
Codex execute and reason through each check individually.

Prefer:
1. One automated validation stage/script performing applicable routine checks locally.
2. Compact structured PASS/WARN/FAIL output.
3. Detailed diagnostics retained locally and inspected only for failures.
4. Codex reasoning over the summary and failures, rather than each successful test.

Individual commands are appropriate for unexpected faults, investigations,
development of new tests and genuinely one-off diagnostics. Repeated manual
verification is a signal to incorporate that check into automated validation.
Do not add tests merely to increase coverage: require useful validation and
keep execution and output efficient.

Run `python3 scripts/validate.py` for repository checks; see
`docs/validation.md` for dependencies, logs and limits. Run focused checks while
investigating failures. Keep live guest checks inside the relevant approved
Rundeck/Ansible pipeline; local tests do not prove live deployment acceptance.

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
