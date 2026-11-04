# Rufus Chat for VS Code

Thin client for the existing trusted-LAN Rufus Web account. Open the command
palette and run **Rufus: Open Chat**. Sign in with the same username/password
used at `http://rufus.lan:8788`. Passwords are prompted with VS Code’s hidden
input and are never saved. The revocable eight-hour session and CSRF token stay
in VS Code SecretStorage, outside the webview. Sign out revokes that session.
The bearer API and infrastructure credentials remain on the server.

`rufus.serverUrl` is an application-level setting, defaulting to the existing
Rufus Web origin. Workspace settings cannot silently redirect credentials.
The existing trusted-LAN HTTP policy applies: traffic is not encrypted. Use
only the approved LAN, or an already configured HTTPS origin. No tunnel,
new port, account, authentication scheme or firewall change is introduced.

## Install

Install the packaged `.vsix` using **Extensions → … → Install from VSIX…**,
then reload VS Code. Or run `code --install-extension /path/to/rufus-chat-0.2.0.vsix`.
The desktop extension runs on the UI side; VS Code’s desktop host supplies Node.
No npm install, runtime dependencies, language model API key or Marketplace
publication is needed. VS Code 1.96 or later is required.

The 0.2.0 backend/gateway needs the conservative UTF-8 estimator, separate repository-context intake, model-window
budgeting and a larger bounded request envelope as well as the original additive `/jobs` and `/executions` allowlist update from
this deliverable; conversation and approval routes are unchanged. Deployment
and completion evidence: [VS Code integration](../docs/rufus-vscode.md).

## Use

- Choose or create a conversation in the compact header. Sign-in, sign-out, refresh
  and approved operations are in the ⋯ menu. History is the main scroll area,
  with a bottom multiline composer: Enter sends, Shift+Enter adds a line. History stays in the existing Rufus SQLite
  store and is shared with your existing browser archive. Only selected IDs and
  up to ten recent execution IDs are saved locally, separated by server origin.
- Progress/events, outcomes and completed replies refresh every 2.5 seconds.
  There is no token-by-token generation stream in the backend. Reopen/refresh to
  recover after a connection failure; POSTs are never automatically retried.
- Attach a selection, active file excerpt or repository/file details explicitly.
  Review the exact preview before sending; remove it to send only your message.
  No workspace crawl, automatic file upload or Git/shell command occurs. Context
  uses the backend-advertised resource ceiling; omissions are marked in preview.
  The backend reserves the full message and generation allowance, then fits
  context and whole recent exchanges within its configured model window. It uses
  a replaceable conservative UTF-8 byte estimator, with separate message,
  repository, history and overall budgets. Messages
  exceeding the backend budget are rejected clearly, never silently truncated.
  The backend can shorten the attachment further; see context-budget activity.
  Credential filenames and recognised private keys/tokens are refused. This is
  a guard, not a guarantee that arbitrary source contains no secrets: review it.
  Untrusted workspaces cannot attach context. Nothing is attached by default.
- Infrastructure requests use Rufus’s current classifier and catalogue. Review
  every proposal’s change, target, parameters, risks, hash and expiry. Approve
  or reject through the visible approval card and VS Code’s explicit native confirmation. The
  existing backend alone validates expiry, hash, one-use state and permissions.
- **Approved operations…** discovers only Rufus-approved jobs. Explicitly confirm
  an operation before submission. Sensitive operations are rejected on this
  direct path and must use the conversational proposal/approval workflow.
  This panel does not expand the existing operation catalogue or grant Task 3
  power operations to the Rufus application policy.
- Diagnostic, repair, verification and submitted execution IDs appear with
  backend status and bounded logs in the collapsed Operations and activity area. Only Rufus-recorded execution IDs discovered
  through this client’s conversations or submissions are queried. There is no
  arbitrary Rundeck URL, job UUID, shell, SSH, deployment or cancellation endpoint.

On a timeout or unknown submission outcome, refresh saved history and check
Rundeck before manually resubmitting. Closing the panel does not cancel backend
work. Missing models/sleeping inference hosts are reported by Rufus; the client
does not wake nodes, deploy models or repair infrastructure automatically.

## Build and tests

`python3 scripts/package-rufus-vscode.py --output /tmp/rufus-chat-0.2.0.vsix`
creates a deterministic, dependency-free VSIX with an explicit runtime-file
allowlist. Tests and development files are excluded. JavaScript tests use Node’s
built-in test runner; `scripts/validate-rufus-vscode.py` performs client tests,
syntax and reproducible packaging checks. See the linked completion record for
the separate controller regression/deployment/live HTTP script.
