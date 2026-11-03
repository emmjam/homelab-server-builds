# Efficient validation

Run from the repository root:

```bash
python3 scripts/validate.py
```

Requirements: Python 3, Bash, Git and PyYAML (`python3-yaml` on Debian).
Tests use isolated fixtures and mock services, not live infrastructure. No credentials or deployment access are needed.

The runner syntax-checks tracked shell scripts and discovers each test directory
separately (these directories are not Python packages). All suites run even if
one fails. Each stage has JSON PASS/FAIL output and a log path; the final JSON
summary reports counts and returns a non-zero exit code for any failure.
A command timeout is a failure. Read only failing logs during routine work.
Logs and `summary.json` remain in a unique local `/tmp/homelab-validation-*`
directory until removed or temporary storage is cleaned.

## Review of existing checks

- DNS, LXC, VM, Rundeck secrets and Rufus tests previously required separate
  invocations. The runner discovers all of them and captures verbose success
  output locally. New test directories are discovered automatically.
- Repeated `bash -n` checks now form a single shell syntax stage.
- The VM template rebuild already batches candidate guest validation before
  promotion. Keep those checks in that pipeline; do not repeat each successful
  command through Codex.
- Ansible syntax checks require the relevant inventory, roles, collections and
  controller environment. Keep them in the corresponding deployment workflow;
  this local runner does not claim Ansible syntax or live acceptance validation.
- Remaining LXC acceptance work (rebuild/backup, cross-clone identity, deletion
  and VM regression) should become a repeatable disposable-guest validation
  stage when that lifecycle work is completed. It is not performed by this runner.

For future deployment changes, place deterministic service, configuration,
network, identity and post-boot checks in the relevant Ansible/Rundeck validation
stage. Summarise PASS/WARN/FAIL and retain details locally; a required failed check
must fail the stage. WARN denotes an explicitly optional or unavailable check,
never successful acceptance. Use one-off diagnostics for unexpected failures,
then automate them if they become routine. Do not add coverage-only tests.


## Documentation diagrams

Documentation update, 3 November 2026, based on source baseline `3ed0d03`:
HLD in `PROJECT_CONTEXT.md`; Web authentication; conversation/approval flows;
passive discovery; worker power; Rundeck Git/deployment; and the agreed VS Code
responsibility boundary in `BACKLOG.md`. Entry-point links are in the root and
Rufus READMEs. Existing structure and dated acceptance records are retained.

Diagrams were checked against `Rufus/app.py`, `workflow.py`, `conversations.py`,
`policy.json`, `catalogue.json`, the Web service/authentication code, discovery
collector/publisher, worker power script, Rundeck ACL/job definitions and the
corresponding Ansible deployment configuration. The worker power ACL grant is
separate from the application catalogue; automatic allocation, hosted fallback
and OpenBao remain planned. VS Code acceptance is maintained separately.

Validation: **PASS**, eight Mermaid blocks parsed with Mermaid **11.12.0** in
strict mode; balanced Markdown fences, relative document links/heading anchors,
and `git diff --check` passed in one local documentation validation script.
Every diagram has a prose equivalent; labels and nearby text distinguish current
implementation from requirements/backlog and retain infrastructure authorisation
boundaries. Parser validation does not claim visual acceptance in every Markdown
renderer. Detailed local validation log: `/tmp/homelab-diagrams-validation.log`.

This change does not alter runtime/configuration or deploy services. Application
regressions, live infrastructure acceptance and worker power tests were not rerun:
they would not validate these documentation-only changes. No SSH, WOL, production
repair, CI workflow or manual device test was required or performed. Existing
application/VS Code working changes are excluded from the documentation commit.
