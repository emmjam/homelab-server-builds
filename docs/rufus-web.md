# Rufus Web

## Status and scope

**Current design: trusted-LAN HTTP with browser username/password login.** This
specification supersedes the SSH-tunnel/single-use-code access design.
**Implemented, deployed and automated acceptance passed**, 2 November 2026,
execution [203](http://192.168.0.51:4440/project/HomeLab/execution/show/203).
Actual laptop/phone browser acceptance is separate and remains not performed.

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
  requires at least 3 characters; cap submitted passwords at 1,024 UTF-8 bytes
  and reject oversize input before expensive hashing.
- Return the same generic failure for unknown, disabled and invalid accounts.
  After rate checks, perform a dummy scrypt verification for unknown accounts to
  reduce account-enumeration timing differences. Never reveal stored hashes.

The selected scrypt parameters follow the [OWASP password-storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
Existing SHA-256 digests remain suitable for random session identifiers, **not
passwords**.

## Guessing protection

For the initial trusted-LAN deployment, use a bounded in-memory source-IP counter:
after 20 failed logins within 15 minutes, reject further attempts until that
window expires. Return HTTP 429 with Retry-After. Keep one in-flight scrypt
verification, generic failures and dummy verification for unknown accounts.
Counters reset on Web restart. Persistent/account lockouts and administrative
unlocking are deferred; sessions and conversation history remain persistent.

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

Require an unpredictable session-bound synchroniser CSRF token on every
state-changing request, including login, logout,
message submission and approval/rejection. The login form uses a short-lived
pre-authentication session and hidden CSRF field; it grants no data access. Rotate
session and CSRF values after login. The authenticated page supplies its CSRF token
for requests; it is distinct from the HttpOnly session cookie and API credential.
Do not require Origin to be present: browsers may omit it or send `null`. Reject
explicit foreign origins, and retain the small configured Host allow-list.
Use `Referrer-Policy: same-origin`. No CORS access is granted.

`POST /logout` revokes the current session in SQLite and clears its cookie. GET
requests must not perform login/logout or create approvals. Preserve no-store
responses, restrictive CSP, frame protection and text-only model-output rendering.
No permissive CORS or unauthenticated data-forwarding route.

## Administrator-controlled accounts and Ansible ownership

Keep account definitions in a root-owned, `rufus-web`-readable configuration file
under `/opt/rufus-web/config` (0640, protected parent directories). Entries contain
stable ID, normalised username, enabled state, credential version and encoded
salted scrypt hash. The Web account cannot edit account definitions or application
code. Sessions belong in its writable data directory (0700).

Ansible remains the configuration authority:

- An administrator-only utility accepts new/reset passwords through a hidden
  prompt, generates a fresh salt/hash and writes only the encoded hash into the
  authorised protected, ignored deployment secret source. No password/hash in
  command arguments or logs. Do not change the established controller secrets
  file's ownership, permissions or transfer process.
- Ansible installs account definitions with `no_log`, preserving unchanged hashes
  across runs. It must not generate new random passwords/salts on every deployment
  or copy unrelated source secrets into Web. No default or embedded credentials.
- Account creation, password changes/resets, disable/removal and account-wide session
  revocation are administrator-only operations, performed through the existing
  administrative deployment route. No Web sudo, SSH keys or Rundeck credentials.
- Reloading changed account definitions invalidates sessions for changed credential
  versions/disabled accounts. Unchanged accounts/sessions are not reset by an
  idempotent deployment. Missing/malformed accounts configuration fails closed.

The initial account `ian` is enabled with the administrator-supplied password.
Passwords/hashes are not documented in Git or reports. Account hashes are transferred
separately into `/var/lib/rundeck/rufus-web-accounts.json` (0600, owned by Rundeck).
The broad existing secrets transfer was not used: `/tmp/secrets.txt` and its
ownership/permissions/process remain unchanged.

### Access from laptop and phone

Connect to the trusted home LAN/Wi-Fi and open **http://rufus.lan:8788**.
If that client cannot resolve the LAN hostname, use **http://192.168.0.52:8788**
(the verified deployment address; future address changes require reconciliation).
Sign in as **ian**, using the password entered through the hidden-password utility.
No SSH, tunnel, certificate or client installation is required for normal access.
Use separate browser sessions on each device; they share the Rufus archive.

### Administrator operations

From a checkout on an authorised administrator machine:

```bash
python3 scripts/rufus-web-admin.py set-password ian --secrets-file /path/to/ignored/secrets.txt --transfer
```

The hidden prompt accepts at least **3 characters**. `--transfer` sends only the
salted account records over existing verified SSH, never other source credentials,
and preserves the established secrets file. Use `--ssh-config /dev/null` if needed
by that machine's existing SSH setup. The same utility supports `disable`, `enable`
and `remove`. Then apply `Ansible/playbooks/rufus-web.yml` through the existing
controller deployment route; it installs the managed accounts atomically.

To revoke all sessions for an account, run on the trusted controller:

```bash
cd /opt/homelab-server-builds
sudo -u rundeck ansible-playbook -i Ansible/inventory/ai2.ini Ansible/playbooks/rufus-web-admin.yml -e web_admin_action=revoke -e web_admin_username=ian
```

This is an administrative operation, not a browser endpoint. Individual-session
administration is deferred. Password changes/disable/removal revoke sessions
through the managed credential version or account state on every request.

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
account behaviour; in-memory source throttling and reset on restart; eight-hour
expiry; session fixation/replay prevention; CSRF/Origin/Host checks; logout and
administrator revocation/reset/disable; idempotent Ansible deployment; LAN access
and non-LAN denial; absence of API credentials in browser assets/responses; chat
multi-turn completion/reopened history; existing AI2/AI3 regressions and zero
Rundeck executions during ordinary conversation. Do not recreate the retired AI2
fixture or start node/worker management.

## Automated HTTP/session acceptance

Report this separately as **automated HTTP/security tests**, not browser or
multi-device testing. Browser automation is not required to run or complete this
suite. Use independent HTTP clients with separate cookie jars (or isolated
browser contexts if already available); never share a session between simulated
clients. Run against an isolated test service/database for destructive account,
lockout and expiry scenarios; do not add production test-control endpoints.

| Area | Required automated assertions |
|---|---|
| Authentication | Valid login, wrong password, unknown/disabled account and malformed input; generic failures; unique salts and correct hash verification; no plaintext/API credentials in assets, responses or logs. |
| Independent sessions | Clients A/B log in independently; distinct session IDs, correct cookie flags, no session fixation, absolute eight-hour expiry, persistence across restart without extending expiry. |
| CSRF and origins | Login, logout, message and approval/rejection mutations reject absent, wrong or another session's CSRF token; foreign Origin and unapproved Host are rejected; absent/null Origin works only with valid CSRF. Valid authenticated requests work. |
| Guessing protection | Source threshold across usernames, unknown-account attempts, window expiry, Retry-After, bounded hashing and deliberate reset on restart. Client-supplied forwarding headers cannot bypass limits. |
| Logout/revocation | Logging out A invalidates replay of A's old cookie while B remains valid; administrator session revocation, password reset/change, account disable/removal invalidate all affected sessions; other accounts remain unaffected. |
| Existing behaviour | Conversation creation, follow-up, listing/reopened history, error/progress responses, exact approval/rejection and changed/expired/replayed proposal rejection; AI2 mocks/AI3 regressions; zero Rundeck executions for ordinary chat. |
| Network | API remains loopback-only; Web is reachable from the trusted LAN and denied outside it; no bearer credential reaches either HTTP client. |

Use a controlled clock in the isolated test harness for expiry/window boundaries,
not hours of waiting or production clock changes. Separate clients on one host
prove session isolation, **not** separate-device or separate-source-IP behaviour.
Exercise source-IP policy with controlled peer addresses in the harness or real
approved test sources, never by trusting forged X-Forwarded-For headers.

Emit compact per-area PASS/FAIL with detailed logs retained locally. Include the
commit, environment and actual checks executed. Existing code-login tests do not
count as evidence for the revised password design. Revised suite status:
**PASS**, as detailed below.

## Manual laptop-and-phone checklist — after deployment

Use the trusted home Wi-Fi/LAN on both devices, not mobile data or an untrusted
guest network. Record date, laptop browser, phone browser and PASS/FAIL per item.
All items are currently **not performed**.

1. Open `http://rufus.lan:8788` on the laptop and phone, without SSH tunnels.
   Confirm the login page fits each screen and accepts the administrator-issued
   username/password. Use the LAN IP if local hostname resolution is unavailable;
   record which address was used.
2. On the laptop, start a conversation, send a normal question and a follow-up.
   Confirm progress appears, the final replies are readable, and input/scrolling
   work. On the phone, reopen that conversation and confirm the same saved history.
3. Send a follow-up from the phone. Refresh/reopen on the laptop and confirm the
   reply remains. Check phone portrait/landscape layout and the on-screen keyboard.
4. Sign out on the laptop, then refresh: login must be required. The phone's
   independent session must remain usable. Sign back in on the laptop and confirm
   history is still present. Also confirm sign-out is reachable on the phone.
5. If an independently approved, genuine infrastructure proposal is available,
   check that its exact change, risks, parameters and expiry are readable on both
   devices. Reject it and confirm the rejected state persists. Do not create a
   production fault or approve a repair merely to test buttons; approval execution
   is covered by isolated automated tests unless a real operation is approved.

A report must distinguish automated results, laptop browser results and phone
browser results. Do not label two-device browser acceptance PASS until both real
devices have completed the checklist; leave unavailable checks PENDING.

Historical deployment evidence: execution 199 passed the existing automated
suites, loopback isolation and AI3 restart acceptance; correction 201 passed
web-focused deployment/security checks. Those executions concern the superseded
code-login/loopback design. Ordinary HTTP chat later exposed output exhaustion;
that inference investigation is separate and is not resolved by this document.


## Automated completion record — 2 November 2026

- Implementation deployed through execution **203**, source `32bfd95`.
- All six shared validation groups passed: **119 tests** (DNS 5, LXC 26, Rufus 71,
  Rundeck 13, VM 4), plus shell syntax. Existing AI2 regressions passed with mocks;
  no disposable fixture or live repair was recreated.
- Two additional administrator-source/transfer tests passed after the helper was
  finalised in `ada742c`: **121 automated tests in total**. Updated chat JavaScript
  also passed syntax compilation; this is not a browser interaction test.
- Real AI3 multi-turn local inference and history/context across a Rufus restart
  passed. Real LAN HTTP login used independent cookie jars, completed the garden
  robot/Willow exchange and reopened identical saved history in another session.
- Login CSRF/Origin rejection and logout isolation passed; isolated HTTP tests cover
  session expiry/replay, hashing, throttling, restart persistence, administrator
  revocation/reset/disable/removal and exact approval/rejection forwarding.
- Ordinary conversations generated **zero Rundeck executions**. The temporary live
  acceptance account was removed; only `ian` remains enabled. A repeated Web
  deployment reported **changed=0**.
- Live listeners: guest LAN IPv4 TCP **8788**, API **127.0.0.1:8787**. The persistent
  dedicated nftables policy allows the trusted IPv4 subnet/loopback and drops other
  IPv4/IPv6 sources to Web. Account separation and protected file modes passed.
- Laptop-side HTTP requests reached the LAN username/password page, while direct
  TCP access to API 8787 was refused. No SSH tunnel was used. A physical off-LAN
  probe/router-port-forward audit was not performed; denial is verified from the
  installed firewall policy, and no router/external exposure was configured.
- Controller logs: `/tmp/rufus-web-final-94q9b4er.log` and
  `/tmp/homelab-validation-iz5f2k4g`. Browser automation was not required or run.

The output-exhaustion cause was reproduced: the retained Qwen template opens a
thinking block despite `think=false`; the exact failed request consumed all
**512 tokens** (`done_reason=length`) without closing that block. A chat-only empty
thinking prefill completed within the same budget (**293 tokens**, stop). It is
now explicitly managed in inference.json by the Rufus-only client tasks in
`Ansible/playbooks/ai-inference.yml`. The installed Qwen3 4B model/runtime, 4096
context, 512 chat limit, timeouts and structured AI2 256-token path are unchanged.
Truncated output still fails safely rather than being recorded as a successful
assistant reply. No conversation-store or approval-state-machine changes were made.

Limitations: HTTP uses the approved trusted-LAN boundary rather than transport
encryption; sessions share one operator archive; responses/context remain bounded.
The manual checklist above is still pending on both actual devices. No node
management, worker allocation, reverse proxy, TLS requirement or new guest was added.

## Trusted-LAN simplification (2 November 2026)

The initial mandatory Origin check could reject otherwise valid browser POSTs
before session/CSRF validation. The previous `no-referrer` response policy can
produce opaque (`null`) origins on some browser request paths. Existing logs do
not contain the affected browsers' headers, so that specific wire value has not
been captured. Relative frontend URLs and `credentials: same-origin` are retained.
The correction accepts absent/null Origin only subject to the existing login or
session CSRF check; explicit foreign Origin still fails. Host restrictions, LAN
firewall, loopback bearer API, scrypt, HttpOnly/SameSite cookies, eight-hour
server-side sessions, logout and approval restrictions remain. Persistent login
lockouts and individual-session administration are deferred. Account-wide
revocation/reset remains available without adding a session-management UI.

Message request IDs use UUIDv4 generated with `crypto.getRandomValues`, which
works on trusted-LAN HTTP. The secure-context-only `crypto.randomUUID` is not
required. This preserves the existing API request format and idempotency.

Verification: backend fix `d058632` passed the complete automated acceptance
script (controller log `/tmp/rufus-web-final-dk5xfr24.log`): 121 tests plus shell
syntax, AI2 mocks, live local multi-turn chat, history/context across Rufus restart,
independent HTTP sessions, CSRF rejection, absent/null Origin with valid CSRF,
reopened history and logout isolation. Ordinary chat generated zero Rundeck
executions. Temporary acceptance identity was removed; repeat deployment changed
zero resources. LAN binding/firewall and loopback-only bearer API passed.

HTTP JavaScript fix `d2e7215` passed syntax and UUID format/uniqueness checks with
`randomUUID` unavailable. Ansible deployment succeeded and the served asset was
byte-for-byte equal to committed source, with the corrected referrer policy
(controller log `/tmp/rufus-web-http-fix-S2Zfco.log`). No actual laptop/phone
browser test is claimed. Reload `http://rufus.lan:8788/` on both devices, sign in,
start/follow up/reopen a conversation and check logout independently. Use the
existing approval checklist without creating a live fault for testing.
