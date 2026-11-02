# Rufus Web

## Status and scope

**Current design: trusted-LAN HTTP with browser username/password login.** This
specification supersedes the SSH-tunnel/single-use-code access design. The revised
network and password-authentication design is documented, **not implemented or
accepted**. The deployed implementation still uses loopback Web and SSH-issued
codes; its successful deployment checks do not establish completion of this design.

Rufus Web remains a separate client on the **existing Rufus LXC on TNAS**, running
as `rufus-web` under `rufus-web.service`. No new VM, LXC or Docker container.
Rufus retains its own account, SQLite conversations, API authentication and
AI2 approval/Rundeck restrictions. No browser-automation integration is required.

## Binding, firewall and optional HTTPS

Browser → `http://rufus.lan:8788` (or the verified guest LAN IP) → Rufus Web →
`http://127.0.0.1:8787` Rufus API. Normal access requires no SSH tunnel.

- Bind Web to the guest's verified LAN IPv4 on TCP 8788, not `0.0.0.0`.
- Keep the API strictly on `127.0.0.1:8787`.
- Use an Ansible-managed dedicated nftables table: allow loopback and
  `192.168.0.0/24` to TCP 8788; drop other IPv4 and all IPv6 traffic to this port.
  Do not flush unrelated rules or alter SSH/other service access. Require the
  firewall service before Web starts accepting connections; persist it at boot.
- No router port forwarding, UPnP or public endpoint. The existing guest and
  network stay intact; no changes to DHCP, DNS or node power management.
- Manage bind address, trusted CIDR, public base URL and exact allowed origins
  centrally through Ansible. Reject unexpected Host values. Do not derive trust
  from arbitrary client-supplied Host/forwarding headers.

HTTP is the approved initial transport; certificates are not a prerequisite.
Passwords, cookies and conversation data are not encrypted on the LAN. HttpOnly,
SameSite and CSRF protection cannot prevent interception; this arrangement relies
on the trusted home LAN. Use a distinct Rufus password, not another service's.

Later HTTPS may terminate at a managed reverse proxy in front of the same Web
application. Configure the HTTPS public origin and `Secure` cookies then, without
moving the API or changing conversation/approval behaviour. Ignore forwarded
headers unless a specific trusted proxy is configured. No TLS terminator or
certificate generation is part of the initial implementation.

## Browser login and password storage

`GET /` presents a username/password form for unauthenticated browsers. `POST
/login` verifies credentials server-side; authenticated browsers receive the chat
interface. These are application accounts, not Linux/service account passwords.
No self-registration, forgotten-password endpoint or public account-management API.

Use Python's existing `hashlib.scrypt` to avoid adding an authentication framework:

- Unique cryptographically random salt of at least 16 bytes for every password.
- Initial parameters `N=131072` (2^17), `r=8`, `p=1`; derive 32 bytes. Configure
  sufficient explicit scrypt memory allowance and at most one concurrent password
  derivation, bounding memory use. Verify availability/cost on the existing guest
  before acceptance; fail closed rather than silently downgrade parameters.
- Store a versioned encoding containing algorithm, parameters, salt and derived
  hash. Compare derived values with `hmac.compare_digest`.
- Never persist plaintext passwords, encrypt them reversibly, put them in Git,
  logs, command arguments, browser storage or URLs. Passwords exist only in the
  submitted form and server memory while checking them.
- Accept long passphrases without silent truncation. Administrator creation/reset
  requires at least 15 characters; cap submitted passwords at 1,024 UTF-8 bytes
  and reject oversize input before expensive hashing.
- Return the same generic failure for unknown, disabled and invalid accounts.
  After rate checks, perform a dummy scrypt verification for unknown accounts to
  reduce account-enumeration timing differences. Never reveal stored hashes.

The selected scrypt parameters follow the [OWASP password-storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
Existing SHA-256 digests remain suitable for random session identifiers, **not
passwords**.

## Guessing protection

Persist rate-limit state in Web's separate protected SQLite database so restarts
cannot reset protection. Enforce counters atomically before costly verification:

- Account/name: after 5 failed attempts within 15 minutes, block that account/name
  for 15 minutes, regardless of source IP.
- Source IP: after 20 failures within 15 minutes across account names, block that
  source for 15 minutes. Unknown account names count too.
- Enforce one in-flight password derivation. Return a bounded busy response rather
  than start unbounded hashing threads or sleep while holding database locks.
- Throttled requests return a generic HTTP 429 and `Retry-After`, without revealing
  whether the account exists. No permanent automatic account lockout. A success
  clears the relevant account failure counter, not the source's accumulated abuse.
- Use the actual TCP peer address for initial direct LAN access; ignore spoofable
  `X-Forwarded-For`. Expire old limiter entries and bound record/input growth.
- Administrators can clear a temporary lockout. Log authentication outcomes and
  throttling without passwords, hashes, session/CSRF tokens or request bodies.

Thresholds/windows/concurrency are Ansible-managed settings. This implements
[account and source login throttling](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
while limiting accidental or hostile permanent lockouts.

## Sessions, CSRF and logout

On successful authentication, rotate any pre-login identifier and issue a fresh
256-bit random session identifier. Store only its digest, stable account ID,
credential version and absolute expiry server-side. Cookie attributes:

- `HttpOnly; SameSite=Strict; Path=/; Max-Age=28800`.
- Eight-hour absolute lifetime, with no automatic extension on activity.
- No Domain attribute, API bearer token, user-supplied session ID, URL token or
  browser local/session storage. `Secure` is off for approved HTTP and on for HTTPS.

Check server-side expiry, account enabled state and credential version on every
request. Existing sessions can survive service restart within their original
expiry. Disabling/deleting an account or changing/resetting its password revokes
all its sessions. An administrator can revoke sessions without resetting a password.
Migration to this design invalidates existing code-issued sessions and removes
code issuance/login support; do not retain a second authentication backdoor.

Require **both** an explicitly allowed same-origin Origin and an unpredictable
synchroniser CSRF token on every state-changing request, including login, logout,
message submission and approval/rejection. The login form uses a short-lived
pre-authentication session and hidden CSRF field; it grants no data access. Rotate
session and CSRF values after login. The authenticated page supplies its CSRF token
for requests; it is distinct from the HttpOnly session cookie and API credential.

`POST /logout` revokes the current session in SQLite and clears its cookie. GET
requests must not perform login/logout or create approvals. Preserve no-store
responses, restrictive CSP, frame protection and text-only model-output rendering.
No permissive CORS or unauthenticated data-forwarding route.

## Administrator-controlled accounts and Ansible ownership

Keep account definitions in a root-owned, `rufus-web`-readable configuration file
under `/opt/rufus-web/config` (0640, protected parent directories). Entries contain
stable ID, normalised username, enabled state, credential version and encoded
salted scrypt hash. The Web account cannot edit account definitions or application
code. Sessions/rate limits belong in its writable data directory (0700).

Ansible remains the configuration authority:

- An administrator-only utility accepts new/reset passwords through a hidden
  prompt, generates a fresh salt/hash and writes only the encoded hash into the
  authorised protected, ignored deployment secret source. No password/hash in
  command arguments or logs. Do not change the established controller secrets
  file's ownership, permissions or transfer process.
- Ansible installs account definitions with `no_log`, preserving unchanged hashes
  across runs. It must not generate new random passwords/salts on every deployment
  or copy unrelated source secrets into Web. No default or embedded credentials.
- Account creation, password changes/resets, disable/removal, unlocking and session
  revocation are administrator-only operations, performed through the existing
  administrative deployment route. No Web sudo, SSH keys or Rundeck credentials.
- Reloading changed account definitions invalidates sessions for changed credential
  versions/disabled accounts. Unchanged accounts/sessions are not reset by an
  idempotent deployment. Missing/malformed accounts configuration fails closed.

No accounts or passwords have been created for the revised design. Initial account
identity and password provisioning remain an administrator setup step.

## Existing chat and security boundaries

Only the Web backend reads `/opt/rufus-web/config/api-token`. The Rufus API bearer
credential never enters JavaScript, cookies, URLs, browser storage, model context
or responses. Web forwards only approved conversation/action routes, not arbitrary
URLs, jobs or `/executions`. The API continues to require its existing bearer.

Reuse conversation creation/list/history/messages and exact action decisions.
Keep the existing AI2 operation validation, explicit approval, expiry/replay checks,
rejection and independent verification. Login is not infrastructure approval.
Do not alter AI3 processing/persistence for the authentication change.

Authorised accounts currently share one Rufus operator view and conversation
archive; per-user conversation isolation or role delegation is not implemented.
No client machine is exclusive or hardcoded. Other authorised desktops/mobile
browsers can use the same trusted-LAN Web login. A future VS Code client can use
an appropriately secured client/API path; none is implemented by this task.

## Implementation and acceptance plan

Update the existing Web backend/login page, Ansible web playbook, service/firewall
configuration and focused tests. Retire SSH-code helpers/instructions and update
HTTP acceptance to browser credentials, without changing Rufus's bearer boundary.
Run one scripted final acceptance with compact results; browser automation is
optional and is not an acceptance prerequisite.

Verify salted hashes and wrong-password rejection; no plaintext storage; unknown
account behaviour; account/IP throttling and restart persistence; eight-hour
expiry; session fixation/replay prevention; CSRF/Origin/Host checks; logout and
administrator revocation/reset/disable; idempotent Ansible deployment; LAN access
and non-LAN denial; absence of API credentials in browser assets/responses; chat
multi-turn completion/reopened history; existing AI2/AI3 regressions and zero
Rundeck executions during ordinary conversation. Do not recreate the retired AI2
fixture or start node/worker management.

Historical deployment evidence: execution 199 passed the existing automated
suites, loopback isolation and AI3 restart acceptance; correction 201 passed
web-focused deployment/security checks. Those executions concern the superseded
code-login/loopback design. Ordinary HTTP chat later exposed output exhaustion;
that inference investigation is separate and is not resolved by this document.
