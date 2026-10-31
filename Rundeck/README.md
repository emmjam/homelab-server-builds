# Rundeck Automation

This directory holds the Rundeck job definitions and scripts managed through Git. Rundeck remains the controlled execution service; Rufus should discover and invoke only the documented pipeline jobs through the Rundeck API.

## Directory and job groups

Job group names intentionally mirror their repository directories:

- `pipelines/` contains end-to-end workflow jobs. Pipeline jobs call reusable job UUIDs and pass options through job references.
- `jobs/` contains reusable operations.
- `scripts/` contains the flat set of helper scripts executed by Rundeck and scripts deployed to TNAS.

A definition is stored as one YAML file named `${job.name}-${job.id}.yaml` directly inside `jobs/` or `pipelines/`; the matching Rundeck group is `jobs` or `pipelines`. Keep an existing job UUID stable. New jobs need a stable UUID, a useful description, validated parameters, least-privilege execution, clear logging, and meaningful failure exit codes. Pipeline definitions should reference jobs by UUID and must not duplicate their work.

## Existing HomeLab jobs

The current HomeLab project has eight versioned jobs: three workflows and five reusable operations. Definitions preserve the live UUIDs. The TNAS deployment job uses the flat Git source paths while retaining its existing TNAS destination paths and SSH key reference.

The reusable Proxmox scripts remain deployed to `/opt/homelab-server-builds/scripts/` on TNAS; the guest baseline remains deployed to `/opt/homelab-server-builds/debian-baseline.sh`. Rundeck-side helper scripts run from the Rundeck checkout at `/opt/homelab-server-builds/Rundeck/scripts/`; job scriptfile paths point directly to files in that directory.

## Recommended Git synchronization

Use Rundeck's built-in **Git SCM Import** integration for the `HomeLab` project, with this repository and the approved `main` branch. Git Import makes the repository authoritative and avoids accidentally exporting unrelated live jobs back into Git.

Recommended configuration:

- Import format: YAML.
- File path template: `Rundeck/${job.group}/${job.name}-${job.id}.${config.format}` with repository root as the SCM base directory.
- Match regular expression: `Rundeck/(jobs|pipelines)/.*\.yaml`.
- UUID behavior: preserve UUIDs.
- Scope: configure this integration on the `HomeLab` project only.

Before the first import, export or back up the current HomeLab project and review the proposed updates. The YAML files preserve the existing job UUIDs and place reusable jobs and workflows in the `jobs` and `pipelines` groups. Do not configure an exporter against the same branch. Review deletions carefully: removing a tracked YAML file can cause the matching imported Rundeck job to be removed. The path filter keeps jobs outside these repository directories out of scope.

For initial adoption, configure import and review the available changes in Rundeck before applying them. Afterward, use the SCM import status and diff actions to review Git changes before importing; avoid automatic imports that bypass review. Keep unrelated projects and jobs outside this project integration.

Rundeck also supports direct YAML upload and API import, but these require an operator to choose duplicate handling each time. Git SCM Import is the better ongoing synchronization method because it tracks changes and scopes them to selected files. See the [Rundeck Git SCM documentation](https://docs.rundeck.com/docs/manual/projects/scm/git.html) and [job import API reference](https://docs.rundeck.com/docs/api/).

## Rufus integration

Rufus should use a narrowly scoped Rundeck API token and invoke approved workflows by UUID. It can discover pipeline descriptions and required options through Rundeck's project/job APIs, submit only those validated options, poll execution status, and retrieve execution logs. Keep API credentials in Rundeck Key Storage or another secret store; never put them in job YAML or scripts. Do not expose arbitrary shell execution or an unrestricted run-script endpoint to Rufus.

## TNAS execution and privilege boundary

The current jobs preserve the successful Rundeck-to-TNAS SSH flow, the existing service-account key path, deployed script locations, and `sudo -n` execution behavior. This reorganization does not alter TNAS host configuration or credentials.

The repository does not yet implement the planned restricted temporary-script mechanism on TNAS. That remains outstanding: a fixed temporary script path, controlled ownership and permissions, one narrowly scoped NOPASSWD sudoers rule, reliable exit-status capture, and cleanup on success or failure. The actual TNAS sudoers configuration must be inspected before designing that change. Separately, `debian-baseline.sh` still configures `rundeck ALL=(ALL) NOPASSWD: ALL` inside Debian guests; that existing behavior is preserved here and should be reviewed as a distinct least-privilege change.
