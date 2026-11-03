# Rufus VS Code client — VSCODE-01/02/03

## Contract and architecture

`RufusVSCode/` is a dependency-free desktop webview extension. It uses the
existing trusted-LAN Rufus Web origin and normal username/password login. No
bearer API exposure, new port, authentication model, network rule, SSH grant or
Rundeck ACL change is introduced. The core Rufus service, conversation database,
operation policy, classifier and one-use exact approval workflow are unchanged.

The only server change is the existing authenticated/CSRF-protected web gateway’s
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
- Context starts empty. A user explicitly chooses current selection, a small
  active file, or relative file/language/unsaved-edit metadata. The exact preview
  can be removed before Send. Only trusted local workspace files are eligible;
  no automatic tree scan, Git command or background upload occurs. A fragment is
  bounded to 1000 characters and the complete prompt to the API’s 2048-character
  limit, with no silent truncation. Credential filenames and recognisable key/
  token material are refused; operator review remains essential for arbitrary
  source. Attached context becomes part of the existing persisted message.
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

## Installation, configuration and build

See [the extension README](../RufusVSCode/README.md) for installation and use.
Build a package with:

```bash
python3 scripts/package-rufus-vscode.py --output /tmp/rufus-chat-0.1.0.vsix
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

## Automated verification

Non-disruptive client validation (Node 20+):

```bash
python3 scripts/validate-rufus-vscode.py --output /tmp/rufus-chat-0.1.0.vsix
```

If Node is supplied by this laptop’s existing VS Code installation:

```bash
python3 scripts/validate-rufus-vscode.py --node /snap/code/current/usr/share/code/code --electron-node --output /tmp/rufus-chat-0.1.0.vsix
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

## Manual checks — not performed

Do not describe automated mocks or CLI installation as interactive testing.
Still pending in the user’s normal VS Code profile:

1. Install VSIX, open panel, sign in, create a conversation, send/follow up, close/
   reopen the panel and reload VS Code. Check the same archive in the browser.
2. Check readable layout, keyboard focus, narrow pane, high contrast and long
   messages/logs. Confirm progress updates appear while waiting for a reply.
3. Attach a selection/file, review/remove its preview, and confirm only explicit
   context arrives. Check refusal of untrusted/credential files and oversize text.
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
profile/extensions directories; the normal user profile was not modified.

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

Interactive normal-profile VS Code checks listed above are **NOT PERFORMED**.
The mock VS Code controller tests and CLI installation do not establish layout,
keyboard/accessibility behaviour or real extension-host/webview interaction.
Those limits do not change the independently passing backend security checks.
