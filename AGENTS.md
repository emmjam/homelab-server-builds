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
