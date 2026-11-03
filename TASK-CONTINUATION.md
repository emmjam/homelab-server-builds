# Rufus context budgeting and VS Code 0.2.0 — continuation

Updated: 3 November 2026. **Task unfinished: deployment and acceptance pending.**
Repository: `/home/ian/Projects/homelab-server-builds`, branch `main`.
Read this file first on resumption, then `AGENTS.md` and `PROJECT_CONTEXT.md`.
Do not delete this file until the entire task, including deployment and acceptance,
is tested and verified. Update its checkpoint after each significant stage.

## Current authorisation and exact next action

The current instruction is documentation only. **Do not deploy as part of this
change.** Record the permanent directive and this file in a separate commit and
push them under the standing directive; exclude all pending implementation files.

When the user resumes the deployment task: first run `git status --short --branch`
and `git diff --stat` in this repository, compare the pending files against this
checkpoint, and inspect the existing deployment/acceptance scripts listed below.
Then prepare the narrow managed deployment and combined acceptance script. Do not
run the old final script assuming it deploys/tests all 0.2.0 components: it does not.

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
- Preserve unrelated changes and active infrastructure. No new accounts/auth scheme,
  firewall/network redesign, model download, Mac changes or GitHub Actions workflow.
  Do not manufacture a production fault or approve a repair solely to test the UI.
- If HP is needed and unavailable, use the approved Rundeck HomeLab - AI Host Power
  job `7d9a3328-c8df-4e31-bbf6-49a6d9ce5a11`, allowlisted host and `action=wake`,
  and verify availability before troubleshooting configuration. Never substitute an
  IP silently when a known hostname fails. Do not wake other nodes unnecessarily.
- Put final end-to-end validation in one script and execute it with one SSH call.
  Avoid unnecessary repetition of passing tests unless code/state changes justify it.

## Last verified checkpoint and completed steps

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

## Ordered remaining implementation, deployment and acceptance work

1. Reconcile the working tree with this checkpoint; inspect changed code and current
   deployment configuration. Preserve other work. Address any actual review findings.
2. Prepare a single final controller script for **all** 0.2.0 components. Existing
   `scripts/rufus-vscode-final.py` deploys only Web and checks read-only HTTP/auth;
   it does not deploy the revised backend/inference config or test live ordinary
   inference. Extend/reuse carefully, with failure-safe cleanup and safe logging.
3. Before any Git-fetched deployment, commit/push the reviewed implementation and
   tests/docs separately from the directive commit. Verify the exact remote revision
   and managed controller checkout; do not overwrite local or controller changes.
4. Deploy the Rufus application, Web gateway and inference-client/config changes
   through existing managed routes. Inspect playbooks first: avoid the full HP
   adoption/model/acceptance path just to update the Rufus client. Applicable files:
   `Ansible/playbooks/rufus.yml`, `rufus-web.yml`, `ai-inference.yml`;
   inventories `Ansible/inventory/ai2.ini`, `ai-inference.ini`.
   Existing scoped client route uses `--limit rufus_inference --tags rufus_inference_client`
   with the inference inventory. Confirm scope and module/config completeness before
   execution. Existing controller checkout is `/opt/homelab-server-builds`.
5. Execute combined final end-to-end validation via one SSH call on the authorised
   controller. Verify deployed source/config revision, both Rufus services, new
   capabilities, persisted history/migration, safe structured oversized-message
   rejection/no stored request, context omissions and current-message preservation.
   Run ordinary live chat and follow-up with HP inference and verify full final
   answers. Compare actual Ollama prompt usage with estimates when available;
   document calibration limits. Establish unavailable/incomplete failure behaviour
   non-disruptively; never break production to induce a failure. Preserve independent
   auth/CSRF/approval checks and inspect existing execution logs without new repairs.
6. If reusing temporary Web-account acceptance, preserve the existing managed account
   source at `/var/lib/rundeck/rufus-web-accounts.json`; restore it and its deployment
   in `finally`, verify restoration and remove the temporary identity. Keep plaintext
   credentials in memory and never commit credentials. Revalidate any historical
   execution ID (the old script uses 157) before relying on its availability.
7. Install the matching `/tmp/rufus-chat-0.2.0.vsix` in the intended VS Code profile
   using Install from VSIX, then reload and run **Rufus: Open Chat**. Default server
   `http://rufus.lan:8788`; use the existing Web account, never the API bearer token.
   Rebuild only if source changed or artifact disappeared; do not claim install from
   successful packaging or from historical 0.1.0 CLI evidence.
8. Perform actual interactive acceptance in the normal VS Code profile:
   - Login, create/send/follow up, switch conversations, close/reopen, reload VS Code;
     confirm shared history in browser. Confirm progress while waiting for inference.
   - Narrow/wide panes, high contrast, keyboard focus, Enter/Shift+Enter, long replies
     and logs; composer stays usable while transcript scrolls. Inspect real layout.
   - Explicit selection/file attachment preview/removal; credential/untrusted-file
     refusal, visible excerpt omissions and oversized-message error with draft intact.
   - View approved operations and existing execution/logs. Inspect and reject only an
     independently justified proposal; never manufacture a fault or approve a real
     repair to exercise buttons. Record unavailable acceptance cases as outstanding.
   - Logout/re-login, history retention and independent browser/extension sessions;
     expiry/revocation where practical. Do not call mocks interactive verification.
9. Correct actual findings and run affected checks only. Update this file after each
   stage with exact revisions, execution IDs, commands, logs/results and next action.
10. Update maintained docs/BACKLOG with local/pushed/deployed/live/manual evidence and
    remaining limitations. Report all changed files, details and tests. Only after
    every required stage is complete and verified, transfer lasting evidence to docs
    and delete this continuation file. Unperformed deployment or acceptance means
    this file must remain and the overall task must not be marked complete.

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
streaming. Remote/non-file context attachment is unsupported. Automated mocks do
not verify live Ollama behaviour, normal-profile layout or accessibility. Deployment,
installation and live/manual acceptance are all outstanding.
