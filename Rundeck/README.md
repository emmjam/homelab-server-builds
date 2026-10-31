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

## Automatic Git synchronization

The `HomeLab - Update GitHub Checkout` job pulls `main`, imports every YAML definition in `Rundeck/jobs/` and `Rundeck/pipelines/`, then removes live jobs in the managed `jobs` and `pipelines` groups whose UUIDs are no longer present in those directories. New job files are added on the next refresh, edits update the matching UUID, and deleting a YAML file removes that job from Rundeck. Jobs in other groups and other projects are outside this reconciliation scope.

The refresh job needs the GitHub read token and a Rundeck API token in HomeLab Key Storage. The API token must have permission to import and delete jobs in the HomeLab project. Store it at `keys/project/HomeLab/rundeck_api_token`; do not place credentials in Git. All managed job YAML files must use matching `id` and `uuid` values and belong to the `jobs` or `pipelines` group. Both directories must remain present so the refresh can distinguish an intentionally empty job set from a missing checkout layout.

The importer uses Rundeck's [job import API](https://docs.rundeck.com/docs/api/#importing-jobs) with UUID preservation and update behavior. Review YAML changes in Git before merging them to `main`, because deleting a definition now deletes its corresponding live job on the next refresh.

## Rufus integration

Rufus should use a narrowly scoped Rundeck API token and invoke approved workflows by UUID. It can discover pipeline descriptions and required options through Rundeck's project/job APIs, submit only those validated options, poll execution status, and retrieve execution logs. Keep API credentials in Rundeck Key Storage or another secret store; never put them in job YAML or scripts. Do not expose arbitrary shell execution or an unrestricted run-script endpoint to Rufus.

## TNAS execution and privilege boundary

The current jobs preserve the successful Rundeck-to-TNAS SSH flow, the existing service-account key path, deployed script locations, and `sudo -n` execution behavior. This reorganization does not alter TNAS host configuration or credentials.

The repository does not yet implement the planned restricted temporary-script mechanism on TNAS. That remains outstanding: a fixed temporary script path, controlled ownership and permissions, one narrowly scoped NOPASSWD sudoers rule, reliable exit-status capture, and cleanup on success or failure. The actual TNAS sudoers configuration must be inspected before designing that change. Separately, `debian-baseline.sh` still configures `rundeck ALL=(ALL) NOPASSWD: ALL` inside Debian guests; that existing behavior is preserved here and should be reviewed as a distinct least-privilege change.
