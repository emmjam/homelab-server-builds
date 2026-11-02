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
