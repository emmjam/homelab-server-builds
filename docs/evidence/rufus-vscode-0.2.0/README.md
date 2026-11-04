# Rufus VS Code 0.2.0 deployment evidence — 3 November 2026

- `acceptance.jsonl`: controller deployment, source/services/config checks,
  cleanup and final result. No ephemeral credentials are logged.
- `client.jsonl`: actual extension transport against deployed Web/API/Ollama.
- `extension-host-lifecycle.log`: real VS Code host activation/command/open/reopen.
- `DEPLOYMENT-SOURCE.json`: exact working-source SHA-256 manifest and Git baseline.
- `controller.log`: detailed Ansible deployment output (secret tasks use no_log).
- `git-status.txt`: full preserved working-tree file list after this stage.

Backend: `rufus.lan`, Web `http://rufus.lan:8788`. Both services active. The
uncommitted source snapshot was deployed from `/tmp/rufus-vscode-source.sO8l20Jk`
on Rundeck; the managed checkout was untouched. Archive SHA-256:
`69763b06560a2be741dfb89e7e790b0a7313b6161711f43d2da1ed6bbfac8ca9`.
Protected backup on Rufus: `/var/backups/rufus-vscode-20261103T203239Z`.

All three live chat messages completed; the first was 2,790 characters. Explicit
file context and history recall passed. Progress, HTTP 413/no stored oversized
input, direct-sensitive-operation/CSRF/arbitrary-command/forged-approval denial,
session restoration and logout revocation passed. A separate one-token Ollama
call stopped with `done_reason=length` and was rejected as `inference_incomplete`.
This changed only that diagnostic call, not the managed generation settings.
The original managed accounts were restored and redeployed; no new infrastructure
execution was recorded (11 before/after), and no message remained processing.

VSIX SHA-256:
`e60a2e04a147ac026b62418ccd18f8c39b23c4529813d3bc7013403ac933a9fa`.
Normal local installation succeeded; the installed payload matched the VSIX
except for VS Code's expected manifest metadata. Real VS Code 1.144.0 host
activation, command registration and webview reopening passed in a disposable
profile using the installed payload. Native host logs also contain an upstream
Node DEP0169 warning; it did not fail the lifecycle test.

No desktop UI surface was exposed to automation. Normal-profile visual/layout/
keyboard/resizing acceptance is **unperformed**, with a user observation request
pending. No real sensitive-operation proposal was manufactured; real-proposal
rejection remains untested live. Existing automated approval regressions passed
at the earlier checkpoint (106 Rufus tests and 7 VS Code tests); these unchanged
suites were not repeated merely to reconfirm them. Keep TASK-CONTINUATION.md.
No implementation commit or push was made.
