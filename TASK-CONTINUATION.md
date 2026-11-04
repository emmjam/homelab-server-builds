# Rufus context budgeting and VS Code 0.2.0 — continuation

Updated: 3 November 2026. **Accepted for current use; detailed acceptance checks deferred by the user.**
Repository: `/home/ian/Projects/homelab-server-builds`, branch `main`.
Read this file first on resumption, then `AGENTS.md` and `PROJECT_CONTEXT.md`.
Do not delete this file until the entire task, including deployment and acceptance,
is tested and verified. Update its checkpoint after each significant stage.

## Current authorisation and exact next action

The user now authorises backend deployment, local VS Code 0.2.0 installation,
live integration/visual acceptance and necessary narrow corrections. **Do not
commit or push** without a new instruction. This supersedes the earlier
documentation-only instruction and the commit-before-deployment step below.
Use a checksummed isolated working-source bundle on Rundeck with the existing
Ansible playbooks; do not overwrite the managed Git checkout or publish changes.

Current stage: backend deployment, live transport and local installation verified.
Resume check on 3 November 2026: repository changes preserved; UI inventory still
returns no apps/browsers and native window discovery is unavailable. No deployment,
installation or passing test was repeated. The subsequent provisional user
acceptance below supersedes the request for an immediate normal-profile check.
**Do not rerun deployment or repeat passing tests merely to reconfirm them.**

User checkpoint, 3 November 2026: “it will do for now”. Record this as
provisional acceptance for current use, not proof that every visual, keyboard,
resizing or genuine-proposal rejection check passed. Further work is deferred.

Exact next action: no further changes or testing now. On a future request to
resume, review this checkpoint and ask which deferred check or reported issue the
user wants addressed; do not automatically repeat deployment/tests or request the
same visual confirmation. Preserve this file while detailed acceptance remains
unfinished. Do not commit or push without a new instruction.

Verified resumed checkpoint (3 November 2026):
- Combined runner completed with exit 0 and PASS; exec session 83300 is finished.
- Working snapshot: `/tmp/rufus-vscode-source.sO8l20Jk` on Rundeck; archive SHA256
  `69763b06560a2be741dfb89e7e790b0a7313b6161711f43d2da1ed6bbfac8ca9`.
- Local temporary evidence: `/tmp/rufus-vscode-deployment-iydkbu8s/`.
  Controller log: `/tmp/rufus-vscode-deploy-ssn9ufs_.log`.
  **Durable evidence:** `docs/evidence/rufus-vscode-0.2.0/` (manifest, controller
  log, client results, host lifecycle markers and explanatory README).
- Protected backup on Rufus: `/var/backups/rufus-vscode-20261103T203239Z`.
- Scoped application/inference/Web Ansible deployment completed. All 14 deployed
  module/static hashes matched source; budget config verified; both services active;
  recent service error lines zero. No managed Git checkout change was made.
- Live extension transport: authenticated new budget capabilities; structured message
  and repository HTTP 413 rejections with no storage; complete 2,790-character message;
  explicit file context answer; follow-up history recall; progress on all three
  messages; persisted replies readable through a restored client session.
- Conversation `7e0aee89-bcae-42a6-b83c-7beac944d57e` retains the three benign test
  exchanges. Direct sensitive execution, missing CSRF, arbitrary commands and forged
  approval were denied; logout revocation passed.
- Real Ollama test-only one-token generation returned `done_reason=length`,
  `eval_count=1`, and the deployed client rejected it with `inference_incomplete`.
  Managed inference configuration was not reduced or disrupted.
- Original managed accounts restored byte-for-byte with metadata unchanged and
  redeployed. Final services active; zero processing messages; execution count stayed
  11 before/after, so no infrastructure operations were executed.
- Normal local VS Code 0.2.0 install succeeded. Installed runtime files match VSIX;
  only expected VS Code `__metadata` differs in package.json. VSIX SHA256:
  `e60a2e04a147ac026b62418ccd18f8c39b23c4529813d3bc7013403ac933a9fa`.
- Real VS Code 1.144.0 host activation, `rufus.open` command and webview
  open/close/reopen passed in a disposable profile against the installed payload.
  Original log: `/tmp/rufus-vscode-real-host-profile/logs/20261103T203400/window1/renderer.log`.
  The host exited 0. This is not visual or normal-profile acceptance.
- No production backend/extension source needed correction during this deployment;
  earlier 106 backend and 7 client test results remain the implementation checkpoint.
- No commit/push performed; deployed working-source implementation remains uncommitted.

Remaining: actual normal-profile interactive/visual checks; genuine sensitive-proposal
rejection only when independently justified (no real proposal was manufactured).
Do not delete this file or claim full task acceptance while these required checks
remain unperformed. Keep automated denial/approval proof separate from live proposal
rejection and keep host lifecycle proof separate from visual acceptance.

## Original objectives and requirements

Continue the Rufus context-budgeting and VS Code integration work:

1. Introduce an isolated, replaceable context-budget estimation abstraction.
2. Use conservative UTF-8 byte estimation; introduce no tokenizer dependency.
3. Separate incoming-message, repository/file-context, recent-history and overall
   inference-request budgets.
4. Never silently discard or truncate the current user message to fit context.
5. Apply sensible context-trimming priorities.
6. Return structured meaningful errors for unsupported request sizes.
7. Handle Ollama failures and incomplete responses honestly.
8. Add automated boundary, oversized-message, trimming and failure tests.
9. Update relevant documentation and `BACKLOG.md`, including limitations.
10. Complete VS Code integration, correcting the chat layout and removing
    misleading character-limit messaging.

Preserve authentication, conversation persistence, streaming/progress and approval
architecture. Avoid unnecessary dependencies or architectural changes. Run relevant
validation and report files changed, implementation, tests/results, limitations
and outstanding work. Never claim completion without verification; deployment and
acceptance remain part of the unfinished task.

## Agreed implementation and operational constraints

- `Rufus/budget.py`: injectable `Utf8Estimator.count(text)`, one estimated capacity
  unit per UTF-8 byte. No tokenizer package, model asset download or npm dependency.
  This is conservative estimation, not measured model tokenisation or a universal
  guarantee for other models; model/template changes require review.
- Configured overall window 8,192 tokens; chat output reservation 2,048, structured
  output 256; framing 512 and workflow headroom 1,024 estimated units.
- Separate incoming ceiling 4,096 estimated units, additionally capped by remaining
  capacity; repository ceiling 1,536; history ceiling 2,048 and six whole exchanges.
  HTTP intake envelope 128 KiB; repository intake 32 KiB. Resource bytes and model
  capacities are separate. Effective allowances are advertised by the backend.
- Preserve current message first (existing credential redaction still applies),
  then newest complete exchange if it fits, repository head/tail excerpt, and older
  complete exchanges newest-first. Archives remain intact. Record omissions/usage.
  Structured routing excludes repository attachments and trims oldest history hints
  before failing; final inference wire checks include schema, tools and prefill.
- Limit errors carry an `error` string plus structured code/budget/limit/unit and,
  where counted, estimated usage. HTTP 413 must pass through Web to VS Code.
- Reject Ollama errors, malformed/non-final responses and length-exhausted output,
  including valid-looking structured JSON. Never store partial output as success.
- Preserve loopback bearer API, Web sessions/CSRF, SecretStorage, SQLite conversation
  and approval identities, exact one-use approvals, independent verification and
  restricted Rundeck policy. Progress is existing polling, not token streaming.
- Deploy through the existing Git → Rundeck → Ansible path. Use hostnames for
  SSH/SCP, existing verified host keys and least privilege. Inspect current state
  and `sudo -n -l` before operations. Never expose secrets or modify the ownership,
  permissions or transfer process of Rundeck `/tmp/secrets.txt`.
- Preserve unrelated changes and active infrastructure. No Docker, new accounts/auth scheme,
  firewall/network redesign, model download, Mac changes or GitHub Actions workflow.
  Do not manufacture a production fault or approve a repair solely to test the UI.
- If HP is needed and unavailable, use the approved Rundeck HomeLab - AI Host Power
  job `7d9a3328-c8df-4e31-bbf6-49a6d9ce5a11`, allowlisted host and `action=wake`,
  and verify availability before troubleshooting configuration. Never substitute an
  IP silently when a known hostname fails. Do not wake other nodes unnecessarily.
- Put final end-to-end validation in one script and execute it with one SSH call.
  Avoid unnecessary repetition of passing tests unless code/state changes justify it.

## Initial local implementation checkpoint (deployment status superseded above)

Local implementation and automated acceptance passed on 3 November 2026:

- Added byte estimator and four independent budgets, whole-message preservation,
  excerpt/history selection, advertised capabilities and final wire checks.
- Added additive repository-context SQLite migration and replay checks while
  retaining existing conversation/action state and credential redaction.
- Corrected HTTP 413 propagation through Web and JS client, with no persistence of
  rejected oversized input. The composer retains drafts after rejection.
- Corrected Ollama error/incomplete-response handling.
- Revised 0.2.0 chat UI: separate scrolling transcript and bottom composer, bounded
  attachment/composer height, distinct user/assistant styles, collapsible activity,
  multiline keyboard handling, safe text rendering; removed character limits.
- Removed the pending tokenizer installation/configuration path from Ansible.
- Updated configuration, tests, docs and backlog. No backend/extension deployment,
  live inference, infrastructure operation or worker wake/suspend was performed.
- Implementation is still **uncommitted and unpushed** at this checkpoint. Do not
  infer remote publication or deployment from local tests or the VSIX.
- Built `/tmp/rufus-chat-0.2.0.vsix`; temporary artifacts/logs may disappear.

Tests actually performed (do not rerun merely to reconfirm an unchanged checkpoint):

- `python3 -m unittest discover -s tests/rufus -v`: **106 passed**.
  Log `/tmp/rufus-context-full.log`. Includes auth, persistence, approvals, Unicode,
  exact boundaries, separate budgets, trimming, no silent message loss and failures.
- `python3 scripts/validate-rufus-vscode.py --node /snap/code/current/usr/share/code/code --electron-node`:
  **7 tests passed**, three JS syntax checks passed, VSIX integrity and repeatable
  byte-for-byte packaging passed. Logs `/tmp/rufus-vscode-validation-hvxzq9h9/`.
  Actual isolated Web/Auth/API/SQLite integration; inference/Rundeck and VS Code
  native APIs mocked. Covers structured 413/no storage, chat/history and approvals.
- Changed Ansible YAML parsed with `yaml.safe_load`; not an Ansible execution.
  `git diff --check` passed.
- Initial sandbox run could not bind localhost fixtures. Approval review timed
  out once; permitted retry succeeded. Final passing results above used socket access.

Historical 0.1.0 deployment/CLI install evidence is not 0.2.0 acceptance. User
reported baseline login, saved Willow chat, follow-ups, conversation switching and
panel reopen worked; revised layout and other manual checks remain unverified.

## Ordered remaining acceptance and completion work

1. Continue from the verified resumed checkpoint above. Do not repeat deployment,
   installation or passing live/host tests absent a source change or new failure.
2. Complete the actual normal-profile interactive checklist:
   - Reload VS Code; run `Rufus: Open Chat`; login, create/send/follow up, switch,
     close/reopen and compare the browser archive. Confirm visible progress.
   - Inspect composer/history scrolling, narrow/wide panels, high contrast,
     keyboard focus, Enter/Shift+Enter and long replies/logs in the real interface.
   - Attach/review/remove selection/file context; check visible omissions and
     over-budget draft retention. Automated/backend context tests already passed.
   - Read approved operations/existing logs. Reject only a genuinely justified
     proposal if one exists. Never manufacture a fault or execute an operation for
     approval UI testing. Otherwise keep real-proposal rejection explicitly pending.
   - Check normal-profile logout/re-login and independent browser sessions as needed;
     transport revocation and persisted history are already live-verified.
3. Correct only actual findings and run affected tests. If source changes, rebuild
   the reproducible VSIX, use existing scoped Ansible mechanisms for affected backend
   files, and preserve all source/database/credentials and evidence. Keep secrets out
   of logs. `scripts/run-rufus-vscode-deployment.py` orchestrates a fresh authorised
   deployment if genuinely required; inspect it and live state before rerunning.
4. Update this checkpoint after significant stages and update maintained docs/BACKLOG
   with actual visual/user-reported evidence, remaining limits and precise Git state.
   Do not commit or push without a new user instruction.
5. Only after all required work is complete, tested and verified, transfer lasting
   evidence to maintained docs and delete this continuation file. Until then retain it.

## Relevant files and deployment references

Backend: `Rufus/budget.py`, `app.py`, `conversations.py`, `inference.py`, `workflow.py`;
`RufusWeb/web.py`. Configuration: `Ansible/playbooks/{rufus,rufus-web,ai-inference}.yml`,
`Ansible/vars/rufus-inference.yml`, the inventories above. Runtime homes are
`/opt/rufus` and `/opt/rufus-web`; inference config `/opt/rufus/config/inference.json`;
actual database paths must be read from current managed configuration, not guessed.

Extension: `RufusVSCode/{client.js,extension.js,package.json,README.md}`, `media/`,
`test/`. Tests: `tests/rufus/{test_budget,test_chat,test_inference,test_web,test_workflow}.py`.
Scripts: `scripts/{validate-rufus-vscode,package-rufus-vscode,rufus-vscode-final,rufus-inference-acceptance}.py`.
Maintained evidence: `docs/rufus-vscode.md`, `docs/ai-inference.md`, `docs/ai2-api.md`,
`docs/ai3.md`, `BACKLOG.md`. Supplementary references do not replace the instructions
and acceptance requirements contained in this file.

## Remaining limitations

Conservative byte estimates may reject inputs a tokenizer would accept; framing
headroom is approximate and not calibrated live for this revision. Complete reply
storage retains its 8,192-character ceiling. Progress uses polling rather than token
streaming. Remote/non-file context attachment is unsupported. Live Ollama/transport
and real-host lifecycle acceptance now passed. Normal-profile
layout/accessibility and genuine-proposal rejection remain unverified; see the
current checkpoint above. Byte estimates are not fully calibrated model token counts.
