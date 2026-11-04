# Seerr media stack on native TOS — continuation

## Authorised objective and constraints (4 November 2026)
Begin the Bobarr replacement in this existing repository while the TNAS four-disk
TRAID synchronisation continues. Design around Seerr for discovery/requests,
Sonarr/Radarr, Prowlarr and Transmission. Target native TerraMaster TOS Docker
Compose, never Proxmox or Docker in a VM. Verify actual service dependencies,
including whether Redis is necessary. Cover NordVPN download isolation and
fail-closed behaviour, persistent configuration, consistent paths/permissions,
startup/health, updates/backups and Plex integration. Independently assess
OpenClaw on TOS for orchestration and Mac Pro WOL instead of Rufus; it must not
be a dependency of media delivery. Produce concise design and staged plan;
prepare parameterised Compose/configuration templates marked UNVALIDATED on TOS.
Do not invent NAS paths, credentials, addresses, VPN details or installed versions.
No containers, deployment, NAS changes, infrastructure operations, disk/storage
operations or formatting. Preserve branch/history and all existing working edits.
No commit/push requested. Do not alter standing repository directives.

## Initial inspection
Read AGENTS.md, PROJECT_CONTEXT.md and BACKLOG.md. main at 13d6848; extensive
pre-existing Rufus/Ansible/VS Code edits and untracked evidence/scripts exist.
Existing unfinished TASK-CONTINUATION.md and worker-activity continuation preserved.
No Bobarr implementation or Compose files found in repository. MEDIA-01 previously
specified custom Boba and a Debian VM; current explicit request supersedes those
media project choices only. Historical Proxmox/storage documentation is not a
verified description of current TOS/TRAID and must not supply deployment values.

## Verified checkpoint — local preparation complete
Files added: docs/media-tos.md, MediaStack/compose.yaml, MediaStack/.env.example
and this continuation. Existing BACKLOG.md MEDIA-01 section replaced with current
media scope; a scoped media note added to PROJECT_CONTEXT.md. Other existing
working changes and continuation files were not edited by this task. Branch and
HEAD remain main / 13d6848. No Git staging, commit, push, reset or checkout.

Upstream review: Seerr Docker and database documentation establishes SQLite default
and optional PostgreSQL; no Redis dependency for this deployment. Sonarr/Radarr
own imports; Prowlarr manages indexers; Transmission transfers through Gluetun.
Official sources and detailed decisions are linked in docs/media-tos.md.
OpenClaw Docker/nodes are a conditional separate candidate; TOS/WOL unverified.

Checks: PyYAML parsed Compose; local assertions passed for six services, downloader
VPN namespace, healthy startup dependency, no Transmission published ports,
firewall enabled, bind create_host_path=false and exact agreement between required
Compose variables and env example. git diff --check passed. Private .env is ignored;
.env.example is trackable. Docker CLI is unavailable locally, so no Compose parser,
image/tool/healthcheck, TOS or runtime validation was performed. Earlier combined
status command ended 1 because checking that .env.example is not ignored correctly
returned 1; the explicit assertions above passed. No broad unrelated test suite run.

## Outstanding decisions / exact next action
Review docs/media-tos.md and select the later inventory/pilot scope. Current scope
ends at local preparation: do not deploy, start/pull containers, contact NAS or run
infrastructure/storage/power operations without a subsequent instruction.
Before any later pilot obtain confirmation TRAID synchronisation completed/healthy;
record actual TOS/Docker/Compose versions and TUN/firewall support, verified native
paths/filesystem, identities/ACLs, NAS bind address/ports and existing Plex layout.
Choose image digests, VPN protocol/server/service credentials, indexers, quality,
seeding/storage limits and backup destination/retention. Never place secrets here.
Then follow stages 3–6 of docs/media-tos.md: offline actual-parser preflight,
isolated VPN/DNS/IPv4/IPv6 failure tests, permitted end-to-end film/TV request and
import, Plex playback and backup/restore/rollback. These stages are NOT authorised
by this checkpoint. Keep OpenClaw/Mac WOL work independent and preserve Rufus.

## State
Local files only; not committed, pushed, deployed, TOS-validated or live-accepted.
Retain this file until authorised runtime acceptance is complete. No NAS access,
containers, disk operations or infrastructure changes occurred during preparation.
