# Rufus VS Code client — VSCODE-01/02/03

## Contract and architecture

`RufusVSCode/` is a dependency-free desktop webview extension. It uses the
existing trusted-LAN Rufus Web origin and normal username/password login. No
bearer API exposure, new port, authentication model, network rule, SSH grant or
Rundeck ACL change is introduced. The core Rufus service, conversation database,
operation policy and one-use exact approval workflow are unchanged. The local
0.2.0 revision adds separate repository context and token-aware model-window accounting.

The original 0.1.0 server change extended the authenticated/CSRF-protected web gateway’s
fixed allowlist: GET `/api/jobs`, POST `/api/executions`, and GET
`/api/executions/{positive integer}`. These delegate to the existing Rufus API,
which rejects unapproved operations, sensitive direct submissions and unknown
execution IDs. There is no arbitrary upstream URL/command proxy. The browser
client can use the same routes subject to its existing account/session checks.

Login takes place in the extension host through the existing prelogin CSRF form,
303 login response and authenticated page CSRF token. Passwords are never saved.
Only the session cookie and CSRF value are stored in VS Code SecretStorage, keyed
by server origin. Account expiry/revocation, login throttling and logout remain
server-enforced. No password/session/token enters the webview, settings or logs.
HTTP retains the existing approved trusted-LAN confidentiality limits.
`rufus.serverUrl` has application scope; a repository cannot override it through
workspace settings. HTTP redirects never forward credentials. Failed POSTs are
never automatically retried.

The webview has a restrictive CSP: no networking, images, remote scripts, inline
scripts, workspace resource access, HTML from model output or command links.
Local static assets are the sole resource root. Messages, proposals, context and
logs use `textContent`. Its protocol offers only explicit client actions, never
raw URLs, filesystem paths, shell commands or arbitrary VS Code commands.

## Features and limits

- Backend-persisted conversations can be listed, reopened and continued. Panel
  restoration remembers the selected ID; history remains authoritative in Rufus.
- The backend supports saved progress/result polling, not token streaming.
  Every 2.5 seconds the panel updates messages, progress/evidence events, approval
  states and up to ten known execution statuses/logs. Overlapping refreshes are
  suppressed and the timer stops when the panel is disposed. Closing the panel
  does not cancel server work. Complete replies are displayed once persisted.
- Conversation history occupies the scrollable main area, with distinct You/Rufus
  messages. A multiline composer stays below it; Enter sends, Shift+Enter adds a
  line. Saved conversation selection/new chat stay in the compact header; sign-in,
  sign-out, refresh and approved operations are in the ⋯ menu. Progress is near
  the composer, operation events/logs are collapsed, and explicit pending approval
  cards remain visible. Existing backend polling is retained; no fake streaming.
- Context starts empty. Explicitly choose a selection, active file excerpt or
  relative file/language/unsaved-edit metadata. Large files use a cursor-centred
  line window, then a UTF-8-safe prefix; the preview marks omissions. The complete
  attachment is bounded by backend capability metadata (32 KiB resource ceiling) and is removable before Send. Trusted
  local workspace and credential-file/key/token restrictions remain. No automatic
  scan, Git command or upload occurs. Selected context is persisted separately
  from the actual user message and available in a collapsed history disclosure.
- Only backend-approved operations are discovered. Direct operations require a
  native confirmation and are still validated by Rufus. Sensitive operations
  must use the existing conversational workflow; a direct attempt returns 403.
- Approval/rejection cards show exact parameters, change, risks, proposal hash
  and expiry. The extension fetches current state and requests a native modal
  confirmation, then forwards the exact conversation/action/hash/decision.
  Backend checks remain authoritative for changed, expired and replayed approval.
- Existing diagnostic, repair and verification execution IDs are extracted from
  persisted backend events/actions. Submitted IDs and their bounded logs are
  also viewable. No new deployment operation is invented; only existing approved
  operations can appear. Power jobs added by Task 3 remain outside Rufus’s
  application allowlist unless a separate backend change approves them.

## Message and context budgeting (0.2.0)

The old 2,048-character combined limit originated in `Workflow.message` and
`Store.message`, was copied into the extension/textarea, and was compounded by
`clean`'s default truncation and an 8,192-byte HTTP envelope. It was a storage/
intake guard, **not** the model's 2,048-token generation allowance. The old history
budget was another approximate 6,000-character guard.

`Rufus/budget.py` owns context selection and wire checks. Its injectable
`Utf8Estimator.count(text)` charges one estimated capacity unit per UTF-8 byte.
This is a conservative estimate for the current Qwen text backend, **not measured
tokens or a universal guarantee for other models**. No tokenizer package, asset or
network download is required. Replace the estimator independently of selection.

Four budgets are independent: `incoming_message_tokens` (4,096 estimated units,
further capped by remaining window), `repository_context_tokens` (1,536),
`history_context_tokens` (2,048, also at most six complete exchanges), and the
8,192-token overall window. The overall check reserves 2,048 output tokens,
512 framing units, system text, per-message overhead and 1,024 workflow headroom.
The effective incoming limit is advertised by the backend; UTF-8 multibyte text
uses capacity faster. Input is preserved whole, with existing credential redaction.
Oversized input is rejected before storage; the composer retains the draft.

The newest complete conversational exchange is preserved if it fits; next a
repository head/tail excerpt is fitted up to the configurable 1,536-token
repository budget, then older whole exchanges are added newest-first (at most six,
configurable). Oldest history is dropped first; failed/interrupted requests and
previous repository attachments are not replayed automatically. Repository input
may be shortened or omitted, always before cutting current text; the user message
is never length-truncated. Archives remain intact. `context_budget` activity records
accounting mode, reserved input/output, context inclusion and history count. The
preview shows the attachment sent to Rufus; backend omissions are recorded in
activity. Set `repository_context_tokens` to zero to disable model repository input.

Structured routing and repair explanations now use the same configured model
window, retaining their separate 256-token output allowance. They preserve the
**complete** current request, budget their exact system text, JSON schema,
diagnostic evidence and workflow data, and may drop oldest routing history hints.
Attached repository text never participates in operational routing. Every actual
inference request is checked again after optional thinking prefill is appended,
including schema and any tool fields. If fixed workflow content cannot fit, it
fails clearly without silently cutting the request or granting an operation.
No classifier output grants approval; backend policy and exact one-use approvals
remain authoritative.

The HTTP envelope is independently capped at 128 KiB for security/resource
protection and JSON escaping. SQLite intake uses that resource ceiling rather
than a character/model budget; repository intake/preview has a separate 32 KiB
resource ceiling. These byte ceilings are **not token counts**. Clients discover
model allowances, accounting mode and resource ceilings through authenticated
`GET /conversations` `limits` metadata. VS Code does not tokenise or duplicate
model/repository budgets. It checks advertised resource ceilings and displays
backend errors; only the backend makes authoritative model-fit decisions.

The new backend accepts old messages without `repository_context`. Its additive
SQLite migration preserves conversation/action IDs and approval states. Older
backends reject the new field clearly; context attachment requires capability
metadata. Deploy the application/gateway and the tagged inference-client tasks
through their existing playbooks before installing 0.2.0; **no deployment was
performed at that initial checkpoint**; the resumed deployment record below
supersedes that status. The whole inference playbook also includes HP
adoption/acceptance: do not run that merely to update the Rufus client config.

Estimation can reject text that a model tokenizer would accept. Template headroom
is approximate; no live comparison with Ollama `prompt_eval_count` was performed.
Changing models requires reviewing the estimator and reservations. Ollama errors,
malformed/non-final responses and output exhaustion fail without storing a
successful answer. Reply storage retains its existing 8,192-character ceiling.

Limit errors retain the compatible `error` string and add `code`, `budget`,
`limit`, `unit` and (where counted) `estimated`; intake overflow returns HTTP 413.
Asynchronous workflow errors appear in persisted error events with a safe code.
No partial inference response is presented as a successful final reply.

## Installation, configuration and build

See [the extension README](../RufusVSCode/README.md) for installation and use.
Build a package with:

```bash
python3 scripts/package-rufus-vscode.py --output /tmp/rufus-chat-0.2.0.vsix
```

Install using **Install from VSIX…**, then run **Rufus: Open Chat**. Default
server: `http://rufus.lan:8788`. Use the existing account credentials. No bearer
API token is needed. Session state is independent of browser sessions and both
clients share the operator archive. Remote/non-file workspace context attachment
is not implemented; ordinary chat does not require a trusted/open workspace.

The deterministic packager includes only seven explicit runtime/documentation
files plus VSIX metadata; tests, caches, development files and credentials cannot
be accidentally swept into the archive. The extension has no npm dependencies.
A VSIX is delivered locally; Marketplace publication is not part of this task.

## Automated verification (original 0.1.0 evidence below)

Non-disruptive client validation (Node 20+):

```bash
python3 scripts/validate-rufus-vscode.py --output /tmp/rufus-chat-0.2.0.vsix
```

If Node is supplied by this laptop’s existing VS Code installation:

```bash
python3 scripts/validate-rufus-vscode.py --node /snap/code/current/usr/share/code/code --electron-node --output /tmp/rufus-chat-0.2.0.vsix
```

This runs six Node tests with isolated HTTP servers. One exercises the actual
Rufus API, Web, scrypt/session auth and SQLite code end-to-end, with inference
and Rundeck mocked: ordinary chat/history, restored session, zero ordinary-chat
jobs, operation logs, direct sensitive-operation denial, changed-hash rejection,
explicit approval, independent verification, rejection and replay denial. Other
checks cover transport/route restrictions, no redirect/POST retry, expiry,
context controls, native confirmation, no secrets in webview messages and
continued progress polling. Native VS Code APIs are mocked for controller tests.
JavaScript syntax and repeatable VSIX integrity/allowlist checks are included.

The package was installed successfully by VS Code’s real CLI into disposable
`/tmp` profile/extensions directories. This proves packaging/install acceptance,
not interactive webview usability. Detailed client log:
`/tmp/rufus-vscode-validation-5x03kejy` on the development laptop.

Controller final validation is one script invoked through one SSH call:
`sudo python3 scripts/rufus-vscode-final.py` from an authorised source bundle on
Rundeck. It runs the complete Rufus regression suite, deploys through the existing
`rufus-web.yml` playbook, tests live account login, conversation/job reads,
existing execution 157 logs, CSRF, sensitive direct-operation rejection and
logout. Its temporary account is restored out of the managed source in `finally`
and Ansible reapplies the original account definitions. Only salted hashes are
written; generated plaintext stays in process memory. It submits no live job,
repair, ordinary inference or worker power operation. Detailed logs remain on
Rundeck. The final controller result is recorded below.

## Manual checks — remaining

Do not describe automated mocks or CLI installation as interactive testing.
Still pending in the user’s normal VS Code profile:

1. Install VSIX, open panel, sign in, create a conversation, send/follow up, close/
   reopen the panel and reload VS Code. Check the same archive in the browser.
2. Check readable layout, keyboard focus, narrow pane, high contrast and long
   messages/logs. Confirm progress updates appear while waiting for a reply.
3. Attach a selection/file, review/remove its preview, and confirm only explicit
   context arrives. Check refusal of untrusted/credential files, visible excerpt omissions and clear
   over-budget message errors without losing the composer text.
4. View approved operations and an existing execution. For an independently
   justified backend proposal, inspect its exact details and reject it. Do not
   create a fault or approve a production repair just to test buttons.
5. Sign out, re-sign in and check history. Exercise expired/revoked sessions if
   convenient; isolated automated tests already cover expiry and revocation.

No new infrastructure fault, disposable live repair fixture, Mac operation,
model download, CI/GitHub Actions workflow or unrelated deployment is required.

## Completion evidence — 3 November 2026

VSCODE-01/02/03 are complete for implementation, packaging and automated
acceptance. **Six client tests and all 91 Rufus regressions passed.** JavaScript
syntax checks, repeatable archive integrity/file allowlist checks and Git diff
whitespace checks passed. The real VS Code CLI accepted the VSIX in disposable
profile/extensions directories; the normal user profile was not modified during that automated validation.

Final controller log: `/tmp/rufus-vscode-final-_h5xlses.log`. Deployment via the
existing Ansible web playbook passed. A real temporary Web account passed login,
conversation/job reads, existing execution 157 status/logs, direct APT-cache
restart denial (403), missing-CSRF denial, arbitrary-command route denial and
logout/session invalidation. The original managed accounts were restored
byte-for-byte in `finally` and redeployed; the temporary account was removed.
The deployed gateway was byte-for-byte equal to source and both Rufus services
were active. No real Rundeck execution, inference request or worker operation
was submitted. No API authentication, policy, ACL, network or worker configuration
was changed.

Package: `rufus-chat-0.1.0.vsix`, built locally using the checked-in deterministic
packager. The reusable client and controller validation scripts retain their
detailed logs locally and fail non-zero on failed checks. The source, tests,
packager, deployment gateway change and documentation are version controlled;
no binary, test credentials or temporary account file is added to Git.

At the original automated completion, interactive normal-profile checks were
**NOT PERFORMED**. Subsequent user-reported baseline results are recorded below.
The mock VS Code controller tests and CLI installation do not establish layout,
keyboard/accessibility behaviour or real extension-host/webview interaction.
Those limits do not change the independently passing backend security checks.

## Layout and budgeting revision — local, 3 November 2026

The user subsequently confirmed login/saved conversations, creating and continuing
the Willow conversation, switching away/back and closing/reopening the baseline
0.1.0 panel with replies retained. These are user-reported interactive results,
not automated evidence. Reload VS Code, shared browser history, progress, context,
operations/logs, logout/independent sessions and justified-proposal rejection were
not confirmed. The user then requested this layout/budget correction.

At the initial automated checkpoint, version 0.2.0 was a local source/package
revision; backend deployment and extension installation were not performed. The
resumed deployment record below supersedes that initial status. The
revised layout needs the manual checks above at narrow/wide widths, with keyboard,
high contrast and long output. Do not treat DOM/controller mocks as visual or
normal-profile acceptance. Reject only an independently justified proposal; never
manufacture a fault or approve a repair to exercise the interface.

Verified local results on 3 November 2026:

- `python3 -m unittest discover -s tests/rufus -v`: **106 tests passed**.
  Covers exact byte/window boundaries, Unicode, independent message/history/
  repository budgets, whole-exchange trimming, current-message preservation,
  SQLite migration/replay and inference error/incomplete-response handling.
  Existing authentication, persistence, workflow and approval regressions passed.
- `python3 scripts/validate-rufus-vscode.py --node
  /snap/code/current/usr/share/code/code --electron-node`: **7 tests passed**,
  plus three JavaScript syntax checks, package integrity and byte-for-byte
  reproducibility. Isolated Web/Auth/API/SQLite acceptance includes structured
  HTTP 413 propagation, no storage on rejection, chat/history and exact approvals.
  Inference and Rundeck are mocked; no live repairs or inference were performed.
- Changed Ansible YAML parsed successfully with `yaml.safe_load`; this is not
  an Ansible execution or deployment check. `git diff --check` passed.
- Package: `/tmp/rufus-chat-0.2.0.vsix`.

The composer stays below a separately scrolling transcript. The attachment area
and composer height are bounded, activity is collapsible, and distinct message
styles replace the old form layout. No character counter or `maxlength` claims
model capacity. DOM/controller tests cover draft retention after errors,
Enter/Shift+Enter, safe text rendering, busy state and attachment removal.

At this initial checkpoint, deployment, installation and manual/real-model checks
were outstanding. The resumed record below reports the subsequent verified state.


## Resumed deployment and installation — 3 November 2026

The backend application, byte-budget configuration and Web gateway were deployed
with the existing scoped Ansible playbooks from an isolated working-source bundle
on Rundeck. No commit or push was made, and the managed Git checkout was preserved.
The source baseline is `13d68487c063f1303575270ccb2256da4412e7f8` plus uncommitted
working changes; this is **not** evidence of a Git-published implementation.

The runner is `scripts/run-rufus-vscode-deployment.py`; the controller uses
`scripts/rufus-vscode-deploy.py` and the live client uses
`scripts/rufus-vscode-live.js`. Source SHA-256 values are stored in its
`DEPLOYMENT-SOURCE.json`. A protected SQLite/application/configuration backup was
created on Rufus before applying changes. All 14 backend/gateway/static file hashes
matched source, both services were active, budget settings matched and no recent
service error lines were present. No working host/network/policy configuration was
redesigned. No worker wake or repair was required.

Local installation of `/tmp/rufus-chat-0.2.0.vsix` succeeded using the real VS Code
CLI. Installed runtime files matched the source-verified VSIX; `package.json`
contained only the expected additional VS Code `__metadata` field. Package SHA-256:
`e60a2e04a147ac026b62418ccd18f8c39b23c4529813d3bc7013403ac933a9fa`.

A real VS Code 1.144.0 extension-host run against the installed payload passed
activation, `rufus.open` registration, opening the Rufus webview tab, closing it
and reopening it. The disposable test profile used
`scripts/rufus-vscode-host-test.js`; the host exited with code 0. This is real
host lifecycle acceptance, **not visual or normal-profile acceptance**. The UI
automation inventory exposed no desktop surfaces, so actual composer/history,
narrow/wide sizing, high contrast and keyboard layout checks await user observation.
Use **Ctrl+Shift+P → Rufus: Open Chat** after reloading the normal VS Code window;
the command opens an editor tab, rather than registering a sidebar view.

The combined deployment/live transport script passed:

- Three messages completed through the actual extension transport, Web/API and
  Ollama. The 2,790-character input was retained whole; explicit file context
  returned the fictional garden name, and a later un-attached follow-up recalled it.
  A restored client session read the same persisted replies. Progress was observed.
- Oversized messages and repository input returned structured HTTP 413 and were
  not stored. Sensitive direct execution, missing CSRF, arbitrary commands and a
  forged approval were denied. Logout revoked the session.
- An actual Ollama request with a one-token test-only output budget returned
  `done_reason=length`, `eval_count=1`; the deployed inference client rejected it
  as `inference_incomplete`. Managed generation settings were unchanged.
- The original account source was restored byte-for-byte with ownership/mode
  preserved and redeployed in cleanup. Final services were active, no message
  remained processing and the execution count stayed at 11: no infrastructure
  operation was submitted.

[Detailed evidence](evidence/rufus-vscode-0.2.0/README.md) includes the source
manifest, controller deployment log, live-client results and real-host lifecycle
markers. The initial 106 backend/7 client tests were not unnecessarily repeated;
no production application/extension source was changed during this deployment.

**Remaining:** actual normal-profile visual/keyboard/resizing acceptance. No real
sensitive proposal was created merely to test rejection; genuine-proposal rejection
remains untested live, while existing automated approval regressions passed.
`TASK-CONTINUATION.md` remains intact with the exact next action. The task is not
fully accepted until the required interactive checks are completed.


User disposition, 3 November 2026: “it will do for now”. The deployed/installed
revision is accepted for current use. Detailed visual, keyboard/resizing and
genuine-proposal rejection checks are deferred, not claimed as passed. No further
implementation or testing is requested now; the continuation file is retained.
