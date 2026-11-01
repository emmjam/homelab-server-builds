# Rundeck Automation

This directory holds the Rundeck job definitions and scripts managed through Git. Rundeck remains the controlled execution service. Rufus can discover and invoke any job, pipeline, or other operation made available through the Rundeck API; presence in Rundeck is the approval boundary.

## Directory and job groups

Job group names intentionally mirror their repository directories:

- `pipelines/` contains end-to-end workflow jobs. Pipeline jobs call reusable job UUIDs and pass options through job references.
- `jobs/` contains reusable operations.
- `scripts/` contains the flat set of helper scripts executed by Rundeck and scripts deployed to TNAS.

A definition is stored as one YAML file named `${job.name}-${job.id}.yaml` directly inside `jobs/` or `pipelines/`; the matching Rundeck group is `jobs` or `pipelines`. Keep an existing job UUID stable. New jobs need a stable UUID, a useful description, validated parameters, least-privilege execution, clear logging, and meaningful failure exit codes. Pipeline definitions should reference jobs by UUID and must not duplicate their work.

## Existing HomeLab jobs

The current HomeLab project has eleven versioned jobs: three workflows and eight reusable operations. Definitions preserve the live UUIDs. The TNAS deployment job uses the flat Git source paths while retaining its existing TNAS destination paths and SSH key reference. `Proxmox - Delete VM` accepts an exact VM name or numeric ID, refuses all VMs marked as templates, and immediately stops running guests with `qm stop` before purging their disks.

`HomeLab - AI Host Power` accepts only `ai-agent` or `ai-worker` and `wake` or `sleep`. Wake sends a magic packet to the selected host's fixed MAC and verifies SSH becomes available. Sleep requires the Rundeck SSH identity on the selected host, checks that deep suspend-to-RAM is selected, requests `systemctl --no-block suspend`, and verifies SSH becomes unavailable. The AI-mgmnt VM can invoke this controlled job; it does not expose arbitrary host commands.

The reusable Proxmox scripts remain deployed to `/opt/homelab-server-builds/scripts/` on TNAS; the guest baseline remains deployed to `/opt/homelab-server-builds/debian-baseline.sh`. Rundeck-side helper scripts run from the Rundeck checkout at `/opt/homelab-server-builds/Rundeck/scripts/`; job scriptfile paths point directly to files in that directory.

## Automatic Git synchronization

The `HomeLab - Update GitHub Checkout` job pulls `main`, imports every YAML definition in `Rundeck/jobs/` and `Rundeck/pipelines/`, then removes live jobs in the managed `jobs` and `pipelines` groups whose UUIDs are no longer present in those directories. New job files are added on the next refresh, edits update the matching UUID, and deleting a YAML file removes that job from Rundeck. Jobs in other groups and other projects are outside this reconciliation scope.

The refresh job needs the GitHub read token and a Rundeck API token in HomeLab Key Storage. The API token must have permission to import and delete jobs in the HomeLab project. Store it at `keys/project/HomeLab/rundeck_api_token`; do not place credentials in Git. All managed job YAML files must use matching `id` and `uuid` values and belong to the `jobs` or `pipelines` group. Both directories must remain present so the refresh can distinguish an intentionally empty job set from a missing checkout layout.

The `Proxmox - Manage VM` pipeline runs its dispatcher on the Rundeck `localhost` node and starts the existing child jobs through the Rundeck API. It reads the API token from `keys/project/HomeLab/rundeck_api_token` in Key Storage; the token must be allowed to run and poll these jobs.

The importer uses Rundeck's [job import API](https://docs.rundeck.com/docs/api/#importing-jobs) with UUID preservation and update behavior. Review YAML changes in Git before merging them to `main`, because deleting a definition now deletes its corresponding live job on the next refresh.

## Rufus integration

Rufus should use a narrowly scoped Rundeck API token to invoke any available jobs, pipelines, or other controlled Rundeck operations. It can discover operation descriptions and required options through Rundeck's project/job APIs, submit valid options, poll execution status, and retrieve execution logs. The presence of an operation in Rundeck is the approval boundary. Keep API credentials in Rundeck Key Storage or another secret store; never put credentials in job YAML or scripts. Keep Rufus actions mediated by Rundeck rather than exposing a separate arbitrary shell or unrestricted run-script endpoint.

## TNAS execution and privilege boundary

The current jobs preserve the successful Rundeck-to-TNAS SSH flow, the existing service-account key path, deployed script locations, and `sudo -n` execution behavior. This reorganization does not alter TNAS host configuration or credentials.

The repository does not yet implement the planned restricted temporary-script mechanism on TNAS. That remains outstanding: a fixed temporary script path, controlled ownership and permissions, one narrowly scoped NOPASSWD sudoers rule, reliable exit-status capture, and cleanup on success or failure. The actual TNAS sudoers configuration must be inspected before designing that change. Separately, `debian-baseline.sh` still configures `rundeck ALL=(ALL) NOPASSWD: ALL` inside Debian guests; that existing behavior is preserved here and should be reviewed as a distinct least-privilege change.
